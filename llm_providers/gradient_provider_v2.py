"""
DigitalOcean Gradient AI Platform provider (V2) using official gradient SDK.

This provider wraps the official DigitalOcean gradient SDK to provide:
- Standard BaseLLMProvider interface for chat completions
- Access to Knowledge Bases (RAG with citations)
- Access to AI Agents (managed assistants)
- Image generation capabilities

Requires: pip install gradient (official DigitalOcean SDK)
"""

from typing import List, Optional, Dict, Any, Iterator, Union
import os
import asyncio

from . import BaseLLMProvider, Message, CompletionResponse, ImageResponse


class GradientProviderV2(BaseLLMProvider):
    """
    DigitalOcean Gradient AI Platform provider using official SDK.

    Enhanced provider with full SDK features:
    - Serverless inference (chat completions)
    - Knowledge Bases (RAG with citations)
    - AI Agents (managed assistants)
    - Image generation

    Example:
        >>> from llm_providers import ProviderFactory
        >>> provider = ProviderFactory.get_provider('gradient_v2')
        >>> response = provider.complete([Message(role='user', content='Hello!')])
        >>> print(response.content)
        >>>
        >>> # Access knowledge base
        >>> results = provider.query_knowledge_base(kb_id, "What is the return policy?")
        >>>
        >>> # Chat with agent
        >>> response = provider.agent_chat(agent_id, "Help me with my order")
    """

    DEFAULT_MODEL = "llama3.3-70b-instruct"
    BASE_URL = "https://inference.do-ai.run/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        management_token: Optional[str] = None,
    ):
        """
        Initialize the Gradient provider V2.

        Args:
            api_key: Model access key (or GRADIENT_MODEL_ACCESS_KEY env var)
            model: Default model (default: llama3.3-70b-instruct)
            management_token: DigitalOcean API token for management operations
                             (or DIGITALOCEAN_ACCESS_TOKEN env var)
        """
        # Try multiple env var names for flexibility
        api_key = (
            api_key
            or os.getenv("GRADIENT_MODEL_ACCESS_KEY")
            or os.getenv("GRADIENT_API_KEY")
            or os.getenv("DO_GRADIENT_API_KEY")
        )

        if not api_key:
            raise ValueError(
                "Gradient API key required. Set GRADIENT_MODEL_ACCESS_KEY environment variable "
                "or pass api_key parameter. Get your key from: "
                "https://cloud.digitalocean.com/gen-ai"
            )

        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model)

        self._management_token = (
            management_token
            or os.getenv("DIGITALOCEAN_ACCESS_TOKEN")
            or os.getenv("DIGITALOCEAN_TOKEN")
        )
        self._client = None
        self._async_client = None
        self._sdk_available = None

    def _check_sdk(self):
        """Check if official gradient SDK is available."""
        if self._sdk_available is None:
            try:
                from gradient import Gradient
                self._sdk_available = True
            except ImportError:
                self._sdk_available = False
        return self._sdk_available

    @property
    def client(self):
        """Lazy-load the Gradient client from official SDK."""
        if self._client is None:
            if not self._check_sdk():
                raise ImportError(
                    "gradient package not installed. "
                    "Install with: pip install gradient"
                )
            from gradient import Gradient
            self._client = Gradient(
                model_access_key=self.api_key,
                access_token=self._management_token,
            )
        return self._client

    @property
    def async_client(self):
        """Lazy-load the async Gradient client."""
        if self._async_client is None:
            if not self._check_sdk():
                raise ImportError(
                    "gradient package not installed. "
                    "Install with: pip install gradient"
                )
            from gradient import AsyncGradient
            self._async_client = AsyncGradient(
                model_access_key=self.api_key,
                access_token=self._management_token,
            )
        return self._async_client

    def _convert_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        """Convert internal Message objects to SDK format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def complete(
        self,
        messages: List[Message],
        **kwargs
    ) -> CompletionResponse:
        """
        Generate a completion using Gradient serverless inference.

        Args:
            messages: List of Message objects
            **kwargs:
                model: Model ID (default: llama3.3-70b-instruct)
                temperature: 0.0-1.0 (default: 0.7)
                max_tokens: Maximum output tokens (default: 1024)

        Returns:
            CompletionResponse with content, model, and usage stats
        """
        formatted = self._convert_messages(messages)
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 1024)

        response = self.client.chat.completions.create(
            model=model,
            messages=formatted,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        # Extract content from response
        content = ""
        if response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content or ""

        # Extract usage
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        return CompletionResponse(
            content=content,
            model=response.model or model,
            usage=usage,
            metadata={
                "id": response.id,
                "finish_reason": response.choices[0].finish_reason if response.choices else None,
                "provider": "gradient_v2"
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
            String chunks of the response
        """
        formatted = self._convert_messages(messages)
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 1024)

        with self.client.chat.completions.create(
            model=model,
            messages=formatted,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs
        ) as stream:
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

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

        formatted = self._convert_messages(messages or [])
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", 0.7)
        max_tokens = kwargs.pop("max_tokens", 1024)

        response = await self.async_client.chat.completions.create(
            model=model,
            messages=formatted,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        content = ""
        if response.choices and len(response.choices) > 0:
            content = response.choices[0].message.content or ""

        return CompletionResponse(
            content=content,
            model=response.model or model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            metadata={"provider": "gradient_v2"}
        )

    def list_models(self) -> List[str]:
        """
        List available models on Gradient.

        Returns:
            List of model ID strings
        """
        models_response = self.client.models.list()
        return [m.id for m in models_response.data] if models_response.data else []

    # === Advanced Features (Gradient SDK exclusive) ===

    def query_knowledge_base(
        self,
        kb_id: str,
        query: str,
        num_results: int = 5,
        **kwargs
    ):
        """
        Query a Gradient Knowledge Base (RAG).

        Args:
            kb_id: Knowledge base UUID
            query: Search query
            num_results: Number of results to return
            **kwargs: Additional parameters

        Returns:
            RetrievalResponse with results and citations
        """
        return self.client.knowledge_bases.retrieve(
            knowledge_base_id=kb_id,
            query=query,
            top_k=num_results,
            **kwargs
        )

    def list_knowledge_bases(self):
        """List all knowledge bases."""
        return self.client.knowledge_bases.list()

    def agent_chat(
        self,
        agent_id: str,
        messages: Union[str, List[Message]],
        **kwargs
    ):
        """
        Chat with a Gradient AI Agent.

        Args:
            agent_id: Agent UUID
            messages: User message or conversation history
            **kwargs: Additional parameters

        Returns:
            AgentChatResponse with content and citations
        """
        if isinstance(messages, str):
            content = messages
        elif isinstance(messages, list):
            # Use last user message as content
            user_msgs = [m for m in messages if m.role == "user"]
            content = user_msgs[-1].content if user_msgs else ""
        else:
            content = str(messages)

        return self.client.agents.run(
            agent_id=agent_id,
            content=content,
            **kwargs
        )

    def stream_agent_chat(
        self,
        agent_id: str,
        messages: Union[str, List[Message]],
        **kwargs
    ) -> Iterator[str]:
        """
        Stream chat with a Gradient AI Agent.

        Args:
            agent_id: Agent UUID
            messages: User message
            **kwargs: Additional parameters

        Yields:
            String chunks of the response
        """
        if isinstance(messages, str):
            content = messages
        elif isinstance(messages, list):
            user_msgs = [m for m in messages if m.role == "user"]
            content = user_msgs[-1].content if user_msgs else ""
        else:
            content = str(messages)

        with self.client.agents.run(
            agent_id=agent_id,
            content=content,
            stream=True,
            **kwargs
        ) as stream:
            for chunk in stream:
                if hasattr(chunk, 'content') and chunk.content:
                    yield chunk.content

    def list_agents(self):
        """List all agents."""
        return self.client.agents.list()

    def generate_image(
        self,
        prompt: str,
        **kwargs
    ) -> ImageResponse:
        """
        Generate an image using Gradient (if available on your tier).

        Args:
            prompt: Image description
            **kwargs: size, quality, n (number of images)

        Returns:
            ImageResponse with base64-encoded image data
        """
        response = self.client.images.generate(
            prompt=prompt,
            **kwargs
        )

        # Get first image
        image = response.data[0] if response.data else None

        if not image:
            raise ValueError("No image generated")

        return ImageResponse(
            image_data=image.b64_json if hasattr(image, 'b64_json') else str(image),
            model=response.model if hasattr(response, 'model') else "gradient-image",
            revised_prompt=image.revised_prompt if hasattr(image, 'revised_prompt') else None,
            metadata={"provider": "gradient_v2"}
        )

    @property
    def knowledge_bases(self):
        """Direct access to knowledge bases client."""
        return self.client.knowledge_bases

    @property
    def agents(self):
        """Direct access to agents client."""
        return self.client.agents

    @property
    def inference(self):
        """Direct access to inference client."""
        return self.client.inference


# Convenience function
def get_gradient_provider_v2(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    management_token: Optional[str] = None,
) -> GradientProviderV2:
    """
    Get a configured Gradient provider V2 instance.

    Args:
        api_key: Optional API key
        model: Optional default model
        management_token: Optional management token for KB/Agent operations

    Returns:
        Configured GradientProviderV2 instance
    """
    return GradientProviderV2(
        api_key=api_key,
        model=model,
        management_token=management_token
    )
