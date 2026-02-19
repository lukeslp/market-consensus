"""
DigitalOcean Gradient AI Platform provider implementation.

Supports serverless inference with OpenAI-compatible API:
- Chat completions with various models (Llama, Claude, GPT, etc.)
- Streaming responses
- Model listing

API Endpoint: https://inference.do-ai.run/v1
Documentation: https://docs.digitalocean.com/products/gradient-ai-platform/
"""

from typing import List, Optional, Dict, Any, Iterator, Union
from . import BaseLLMProvider, Message, CompletionResponse
import os
import json


class GradientProvider(BaseLLMProvider):
    """
    DigitalOcean Gradient AI Platform provider.

    Uses OpenAI-compatible API for serverless inference across
    multiple foundation models (Meta Llama, Anthropic Claude, OpenAI GPT, etc.)

    Features:
    - Serverless inference (no agent management required)
    - Auto-scaling with pay-per-token pricing
    - Access to commercial and open-source models

    Example:
        >>> from llm_providers import ProviderFactory
        >>> provider = ProviderFactory.get_provider('gradient')
        >>> response = provider.complete([Message(role='user', content='Hello!')])
        >>> print(response.content)
    """

    BASE_URL = "https://inference.do-ai.run/v1"
    DEFAULT_MODEL = "llama3.3-70b-instruct"

    # Known models available on Gradient (as of Jan 2025)
    # Use list_models() for the current list from the API
    KNOWN_MODELS = [
        # Meta Llama models
        "llama3.3-70b-instruct",
        "llama3.2-3b-instruct",
        "llama3.2-1b-instruct",
        "llama3.1-70b-instruct",
        "llama3.1-8b-instruct",
        # OpenAI models (when available)
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        # Anthropic models (when available)
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        # Mistral models
        "mistral-large-latest",
        "mistral-small-latest",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize the Gradient provider.

        Args:
            api_key: Model access key (or GRADIENT_API_KEY / GRADIENT_MODEL_ACCESS_KEY env var)
            model: Default model to use (default: llama3.3-70b-instruct)
            base_url: Override API base URL (default: https://inference.do-ai.run/v1)
        """
        # Try multiple env var names for flexibility
        api_key = (
            api_key
            or os.getenv("GRADIENT_API_KEY")
            or os.getenv("GRADIENT_MODEL_ACCESS_KEY")
            or os.getenv("DO_GRADIENT_API_KEY")
        )

        if not api_key:
            raise ValueError(
                "Gradient API key required. Set GRADIENT_API_KEY environment variable "
                "or pass api_key parameter. Get your key from: "
                "https://cloud.digitalocean.com/gen-ai"
            )

        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model)

        self.base_url = base_url or self.BASE_URL
        self._client = None
        self._use_openai_sdk = True

    @property
    def client(self):
        """Lazy-load the OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
                self._use_openai_sdk = True
            except ImportError:
                # Fall back to requests if OpenAI SDK not installed
                self._use_openai_sdk = False
        return self._client

    def _make_request(
        self,
        endpoint: str,
        method: str = "POST",
        data: Optional[Dict] = None
    ) -> Dict:
        """Make a direct HTTP request (fallback when OpenAI SDK unavailable)."""
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}{endpoint}"

        if method == "GET":
            response = requests.get(url, headers=headers)
        else:
            response = requests.post(url, headers=headers, json=data)

        response.raise_for_status()
        return response.json()

    def complete(
        self,
        messages: List[Message],
        **kwargs
    ) -> CompletionResponse:
        """
        Generate a completion using Gradient serverless inference.

        Args:
            messages: List of Message objects (system, user, assistant)
            **kwargs:
                model: Model ID (default: llama3.3-70b-instruct)
                temperature: 0.0-1.0 (default: 0.7)
                max_tokens: Maximum output tokens (default: 1024)
                top_p: Nucleus sampling parameter

        Returns:
            CompletionResponse with content, model, and usage stats

        Example:
            >>> messages = [
            ...     Message(role='system', content='You are helpful.'),
            ...     Message(role='user', content='What is Python?')
            ... ]
            >>> response = provider.complete(messages, temperature=0.5)
        """
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 1024)

        if self._use_openai_sdk and self.client:
            # Use OpenAI SDK
            response = self.client.chat.completions.create(
                model=model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            return CompletionResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                metadata={
                    "id": response.id,
                    "finish_reason": response.choices[0].finish_reason,
                    "provider": "gradient"
                }
            )
        else:
            # Fallback to direct HTTP
            data = {
                "model": model,
                "messages": formatted_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

            response = self._make_request("/chat/completions", data=data)

            usage = response.get("usage", {})
            choices = response.get("choices", [{}])

            return CompletionResponse(
                content=choices[0].get("message", {}).get("content", ""),
                model=response.get("model", model),
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                metadata={
                    "finish_reason": choices[0].get("finish_reason"),
                    "provider": "gradient"
                }
            )

    def stream_complete(
        self,
        messages: List[Message],
        **kwargs
    ) -> Iterator[str]:
        """
        Stream a completion using Gradient serverless inference.

        Args:
            messages: List of Message objects
            **kwargs: Same as complete()

        Yields:
            String chunks of the response as they arrive

        Example:
            >>> for chunk in provider.stream_complete(messages):
            ...     print(chunk, end='', flush=True)
        """
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 1024)

        if self._use_openai_sdk and self.client:
            # Use OpenAI SDK streaming
            stream = self.client.chat.completions.create(
                model=model,
                messages=formatted_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        else:
            # Fallback: non-streaming (direct HTTP doesn't easily support SSE)
            response = self.complete(
                [Message(role=m["role"], content=m["content"]) for m in formatted_messages],
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            yield response.content

    async def chat(
        self,
        messages: Optional[List[Message]] = None,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        **kwargs
    ) -> CompletionResponse:
        """
        Async chat method for orchestrator compatibility.

        Args:
            messages: Optional list of Message objects
            system_prompt: System message content
            user_prompt: User message content
            **kwargs: Passed to complete()

        Returns:
            CompletionResponse
        """
        if messages is None and (system_prompt or user_prompt):
            messages = []
            if system_prompt:
                messages.append(Message(role="system", content=system_prompt))
            if user_prompt:
                messages.append(Message(role="user", content=user_prompt))

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.complete(messages or [], **kwargs)
        )

    def list_models(self) -> List[str]:
        """
        List available models on Gradient.

        Returns:
            List of model ID strings

        Example:
            >>> models = provider.list_models()
            >>> print(models)
            ['llama3.3-70b-instruct', 'gpt-4o', ...]
        """
        try:
            if self._use_openai_sdk and self.client:
                models = self.client.models.list()
                return [model.id for model in models.data]
            else:
                response = self._make_request("/models", method="GET")
                return [m.get("id") for m in response.get("data", [])]
        except Exception as e:
            # Return known models as fallback
            return self.KNOWN_MODELS.copy()

    def get_model_info(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about a specific model or the current model.

        Args:
            model_id: Model to query (default: current model)

        Returns:
            Dict with model information
        """
        model_id = model_id or self.model
        try:
            if self._use_openai_sdk and self.client:
                model = self.client.models.retrieve(model_id)
                return {
                    "id": model.id,
                    "created": model.created,
                    "owned_by": model.owned_by,
                    "object": model.object
                }
            else:
                return self._make_request(f"/models/{model_id}", method="GET")
        except Exception as e:
            return {
                "id": model_id,
                "error": str(e),
                "available": model_id in self.KNOWN_MODELS
            }


# Convenience function for quick usage
def get_gradient_provider(
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> GradientProvider:
    """
    Get a configured Gradient provider instance.

    Args:
        api_key: Optional API key (uses env var if not provided)
        model: Optional default model

    Returns:
        Configured GradientProvider instance
    """
    return GradientProvider(api_key=api_key, model=model)
