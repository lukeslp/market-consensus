"""
Hugging Face provider implementation.
Supports Inference API and Inference Endpoints for various models including Llama.
"""

from typing import List, Union
from . import BaseLLMProvider, Message, CompletionResponse, ImageResponse
import os
import base64


class HuggingFaceProvider(BaseLLMProvider):
    """Hugging Face provider using Inference API."""

    DEFAULT_MODEL = "meta-llama/Llama-3.1-70B-Instruct"

    def __init__(self, api_key: str = None, model: str = None):
        api_key = api_key or os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_API_KEY") or os.getenv("HF_TOKEN")
        if not api_key:
            raise ValueError("HUGGINGFACE_API_KEY, HF_API_KEY, or HF_TOKEN is required")

        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model)

        try:
            from huggingface_hub import InferenceClient
            self.client = InferenceClient(token=api_key)
        except ImportError:
            raise ImportError("huggingface_hub package is required. Install with: pip install huggingface_hub")

    def complete(self, messages: List[Message], **kwargs) -> CompletionResponse:
        """Generate a completion using Hugging Face models."""
        # Convert messages to Hugging Face format
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        model = kwargs.get("model", self.model)
        max_tokens = kwargs.get("max_tokens", 1024)
        temperature = kwargs.get("temperature", 0.7)

        try:
            response = self.client.chat_completion(
                messages=formatted_messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature
            )

            # Extract response
            content = response.choices[0].message.content

            # Extract usage if available
            usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) if hasattr(response, "usage") else 0,
                "completion_tokens": getattr(response.usage, "completion_tokens", 0) if hasattr(response, "usage") else 0,
            }
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

            return CompletionResponse(
                content=content,
                model=model,
                usage=usage,
                metadata={
                    "id": getattr(response, "id", None),
                    "finish_reason": response.choices[0].finish_reason if response.choices else None
                }
            )
        except Exception as e:
            # Handle errors gracefully
            return CompletionResponse(
                content=f"Error: {str(e)}",
                model=model,
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                metadata={"error": str(e)}
            )

    def stream_complete(self, messages: List[Message], **kwargs):
        """Stream a completion using Hugging Face models."""
        # Convert messages to Hugging Face format
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        model = kwargs.get("model", self.model)
        max_tokens = kwargs.get("max_tokens", 1024)
        temperature = kwargs.get("temperature", 0.7)

        stream = self.client.chat_completion(
            messages=formatted_messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True
        )

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def list_models(self) -> List[str]:
        """List popular Hugging Face models for text generation."""
        # Return a curated list of popular models
        # Note: You can also use self.client.list_models() for a full list
        return [
            "meta-llama/Llama-3.1-70B-Instruct",
            "meta-llama/Llama-3.1-8B-Instruct",
            "meta-llama/Llama-3.3-70B-Instruct",
            "meta-llama/Llama-3.2-11B-Vision-Instruct",
            "meta-llama/Llama-3.2-3B-Instruct",
            "meta-llama/Llama-3.2-1B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "Qwen/Qwen2.5-72B-Instruct",
            "Qwen/Qwen2.5-Coder-32B-Instruct",
            "microsoft/Phi-3.5-mini-instruct",
            "HuggingFaceH4/zephyr-7b-beta",
            "google/gemma-2-9b-it",
            "google/gemma-2-27b-it",
        ]

    def generate_image(self, prompt: str, **kwargs) -> ImageResponse:
        """
        Generate an image using Hugging Face text-to-image models.

        Args:
            prompt: Text description of the image
            **kwargs: Optional parameters
                - model: Image generation model (default: "black-forest-labs/FLUX.1-dev")
                - negative_prompt: What to avoid in the image
                - width: Image width (default: 1024)
                - height: Image height (default: 1024)
                - num_inference_steps: Number of denoising steps (default: 30)

        Returns:
            ImageResponse with base64-encoded image
        """
        model = kwargs.get("model", "black-forest-labs/FLUX.1-dev")
        negative_prompt = kwargs.get("negative_prompt", None)
        width = kwargs.get("width", 1024)
        height = kwargs.get("height", 1024)

        try:
            image = self.client.text_to_image(
                prompt=prompt,
                model=model,
                negative_prompt=negative_prompt,
                width=width,
                height=height
            )

            # Convert PIL Image to base64
            import io
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            image_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return ImageResponse(
                image_data=image_b64,
                model=model,
                revised_prompt=None,
                metadata={
                    "width": width,
                    "height": height,
                    "negative_prompt": negative_prompt
                }
            )
        except Exception as e:
            raise Exception(f"Image generation failed: {str(e)}")

    def analyze_image(self, image: Union[str, bytes], prompt: str = "Describe this image", **kwargs) -> CompletionResponse:
        """
        Analyze an image using Hugging Face vision models.

        Args:
            image: Base64-encoded string or raw bytes
            prompt: Question about the image
            **kwargs: Optional parameters
                - model: Vision model (default: "meta-llama/Llama-3.2-11B-Vision-Instruct")

        Returns:
            CompletionResponse with image analysis
        """
        model = kwargs.get("model", "meta-llama/Llama-3.2-11B-Vision-Instruct")
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

        try:
            # Use chat_completion with vision format (OpenAI-compatible)
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

            response = self.client.chat_completion(
                messages=messages,
                model=model,
                max_tokens=max_tokens
            )

            content = response.choices[0].message.content

            # Extract usage if available
            usage = {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0) if hasattr(response, "usage") else 0,
                "completion_tokens": getattr(response.usage, "completion_tokens", 0) if hasattr(response, "usage") else 0,
            }
            usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

            return CompletionResponse(
                content=content,
                model=model,
                usage=usage,
                metadata={"vision": True}
            )
        except Exception as e:
            raise Exception(f"Image analysis failed: {str(e)}")
