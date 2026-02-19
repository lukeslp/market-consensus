"""
Perplexity provider implementation.
"""

from typing import List, Union
from . import BaseLLMProvider, Message, CompletionResponse
import os
import base64


class PerplexityProvider(BaseLLMProvider):
    """Perplexity search-augmented provider using OpenAI-compatible API."""

    DEFAULT_MODEL = "sonar-pro"

    def __init__(self, api_key: str = None, model: str = None):
        api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            raise ValueError("PERPLEXITY_API_KEY is required")

        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model)

        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.perplexity.ai"
            )
        except ImportError:
            raise ImportError("openai package is required. Install with: pip install openai")

    def complete(self, messages: List[Message], **kwargs) -> CompletionResponse:
        """Generate a completion using Perplexity."""
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        response = self.client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=formatted_messages,
            **{k: v for k, v in kwargs.items() if k != "model"}
        )

        return CompletionResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            metadata={
                "id": response.id,
                "finish_reason": response.choices[0].finish_reason,
                "citations": getattr(response, "citations", None)  # Perplexity includes citations
            }
        )

    def stream_complete(self, messages: List[Message], **kwargs):
        """Stream a completion using Perplexity."""
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        stream = self.client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=formatted_messages,
            stream=True,
            **{k: v for k, v in kwargs.items() if k not in ["model", "stream"]}
        )

        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                yield chunk.choices[0].delta.content

    def list_models(self) -> List[str]:
        """List available Perplexity models."""
        # Perplexity doesn't provide a models endpoint, return known models (2025 Sonar API)
        return [
            "sonar-pro",
            "sonar",
            "sonar-reasoning-pro",
            "llama-3.1-sonar-large-128k-online",
            "llama-3.1-sonar-small-128k-online",
        ]

    def analyze_image(self, image: Union[str, bytes], prompt: str = "Describe this image", **kwargs) -> CompletionResponse:
        """
        Analyze an image using Perplexity Sonar Vision.

        Args:
            image: Base64-encoded string or raw bytes
            prompt: Question about the image
            **kwargs: Optional parameters
                - model: Vision model (default: "sonar-pro")
                - max_tokens: Maximum response length

        Returns:
            CompletionResponse with image analysis
        """
        model = kwargs.get("model", "sonar-pro")
        max_tokens = kwargs.get("max_tokens", 1024)

        # Convert bytes to base64 if needed
        if isinstance(image, bytes):
            image_b64 = base64.b64encode(image).decode('utf-8')
        else:
            image_b64 = image

        # Detect media type from base64 header
        media_type = "image/jpeg"
        if image_b64.startswith('/9j/'):
            media_type = "image/jpeg"
        elif image_b64.startswith('iVBOR'):
            media_type = "image/png"
        elif image_b64.startswith('R0lGOD'):
            media_type = "image/gif"
        elif image_b64.startswith('UklGR'):
            media_type = "image/webp"

        # Construct vision message (OpenAI-compatible format)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_b64}"
                        }
                    }
                ]
            }
        ]

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens
        )

        return CompletionResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            metadata={
                "id": response.id,
                "finish_reason": response.choices[0].finish_reason,
                "vision": True,
                "citations": getattr(response, "citations", None)
            }
        )

    async def chat(self, messages=None, system_prompt=None, user_prompt=None, **kwargs) -> CompletionResponse:
        """
        Async alias for complete() to support orchestrator compatibility.
        Orchestrators call await chat(system_prompt=..., user_prompt=...)
        but providers use complete(messages=[...]).
        """
        # Convert orchestrator's system_prompt/user_prompt to messages list
        if messages is None and (system_prompt or user_prompt):
            messages = []
            if system_prompt:
                messages.append(Message(role="system", content=system_prompt))
            if user_prompt:
                messages.append(Message(role="user", content=user_prompt))

        # Run sync complete() in thread pool to make it awaitable
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, self.complete, messages, **kwargs
        )
