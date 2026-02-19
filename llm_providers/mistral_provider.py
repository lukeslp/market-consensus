"""
Mistral AI provider implementation.
Supports Mistral models and Pixtral vision models.
"""

from typing import List, Union
from . import BaseLLMProvider, Message, CompletionResponse
import os
import json
import base64


class MistralProvider(BaseLLMProvider):
    """Mistral AI provider."""

    DEFAULT_MODEL = "mistral-large-2411"

    def __init__(self, api_key: str = None, model: str = None):
        api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("MISTRAL_API_KEY is required")

        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model)

        self.api_url = "https://api.mistral.ai/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ImportError("requests package is required. Install with: pip install requests")

    def complete(self, messages: List[Message], **kwargs) -> CompletionResponse:
        """Generate a completion using Mistral."""
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": formatted_messages,
            **{k: v for k, v in kwargs.items() if k != "model"}
        }

        response = self.requests.post(
            f"{self.api_url}/chat/completions",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()

        return CompletionResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            usage={
                "prompt_tokens": data["usage"]["prompt_tokens"],
                "completion_tokens": data["usage"]["completion_tokens"],
                "total_tokens": data["usage"]["total_tokens"],
            },
            metadata={
                "id": data["id"],
                "finish_reason": data["choices"][0]["finish_reason"]
            }
        )

    def stream_complete(self, messages: List[Message], **kwargs):
        """Stream a completion using Mistral."""
        formatted_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": formatted_messages,
            "stream": True,
            **{k: v for k, v in kwargs.items() if k not in ["model", "stream"]}
        }

        response = self.requests.post(
            f"{self.api_url}/chat/completions",
            headers=self.headers,
            json=payload,
            stream=True
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                line_text = line.decode('utf-8')
                if line_text.startswith("data: "):
                    line_text = line_text[6:]
                if line_text == "[DONE]":
                    break
                try:
                    data = json.loads(line_text)
                    content = data['choices'][0]['delta'].get('content', '')
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    def list_models(self) -> List[str]:
        """List available Mistral models."""
        try:
            response = self.requests.get(
                f"{self.api_url}/models",
                headers=self.headers
            )
            response.raise_for_status()
            models = response.json().get("data", [])
            return [model["id"] for model in models]
        except Exception:
            # Fallback list of known models (December 2025)
            return [
                "mistral-large-latest",
                "pixtral-large-latest",
                "ministral-3b-latest",
                "ministral-8b-latest",
                "pixtral-12b-2409",
                "open-mixtral-8x22b",
                "codestral-latest",
            ]

    def analyze_image(self, image: Union[str, bytes], prompt: str = "Describe this image", **kwargs) -> CompletionResponse:
        """
        Analyze an image using Pixtral vision models.

        Args:
            image: Base64-encoded string or raw bytes
            prompt: Question about the image
            **kwargs: Optional parameters
                - model: Pixtral model (default: "pixtral-large-latest")
                - max_tokens: Maximum response length

        Returns:
            CompletionResponse with image analysis
        """
        model = kwargs.get("model", "pixtral-large-latest")
        max_tokens = kwargs.get("max_tokens", 1024)

        # Convert bytes to base64 if needed
        if isinstance(image, bytes):
            image_b64 = base64.b64encode(image).decode('utf-8')
        else:
            image_b64 = image

        # Detect media type from base64 header or default to jpeg
        media_type = "image/jpeg"
        if image_b64.startswith('/9j/'):
            media_type = "image/jpeg"
        elif image_b64.startswith('iVBOR'):
            media_type = "image/png"
        elif image_b64.startswith('R0lGOD'):
            media_type = "image/gif"
        elif image_b64.startswith('UklGR'):
            media_type = "image/webp"

        # Build Pixtral vision message format
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": f"data:{media_type};base64,{image_b64}"
                        }
                    ]
                }
            ],
            "max_tokens": max_tokens
        }

        response = self.requests.post(
            f"{self.api_url}/chat/completions",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()

        return CompletionResponse(
            content=data["choices"][0]["message"]["content"],
            model=data["model"],
            usage={
                "prompt_tokens": data["usage"]["prompt_tokens"],
                "completion_tokens": data["usage"]["completion_tokens"],
                "total_tokens": data["usage"]["total_tokens"],
            },
            metadata={
                "id": data["id"],
                "finish_reason": data["choices"][0]["finish_reason"]
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
