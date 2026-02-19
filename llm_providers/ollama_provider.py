"""
Ollama Provider for Local LLM Inference

Handles interactions with Ollama for chat completions, image understanding,
and model management. Requires local Ollama server running at http://localhost:11434
or URL specified via OLLAMA_HOST environment variable.

Author: Luke Steuber
"""

import os
import json
import logging
import requests
import time
import base64
from typing import Dict, List, Any, Optional, Generator, Union, Iterator
from io import BytesIO

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from . import BaseLLMProvider, Message, CompletionResponse, ImageResponse, VisionMessage

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """
    Provider for local Ollama LLM server.

    Supports text completion, streaming, vision models, and model management.
    No API key required - connects to local Ollama server.
    """

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize the Ollama provider.

        Args:
            api_key: Not used for Ollama, but required by BaseLLMProvider signature
            model: Default model name (e.g., 'llama3.2', 'llava'). If not provided,
                   will use first available model.
        """
        # Initialize with dummy API key (not used by Ollama)
        super().__init__(api_key=api_key or "local", model=model)

        # Determine Ollama host from environment or use default
        self.host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
        self.available = False
        self.cached_models = []

        # Check if Ollama server is running
        self.available = self._check_availability()
        if self.available:
            self.cached_models = self._fetch_models()
            logger.info(f"Ollama provider initialized with host: {self.host}")
            logger.info(f"Available models: {', '.join([m['id'] for m in self.cached_models])}")

            # Set default model if not provided
            if not self.model and self.cached_models:
                self.model = self.cached_models[0]['id']
                logger.info(f"Using default model: {self.model}")
        else:
            logger.warning(f"Ollama provider not available at {self.host}")

    def _check_availability(self) -> bool:
        """Check if Ollama server is available."""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama server not available: {str(e)}")
            return False

    def _fetch_models(self) -> List[Dict[str, Any]]:
        """
        Fetch list of available models from Ollama.

        Returns:
            List of model dictionaries with 'id' and 'metadata'
        """
        models = []
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                for model in data.get("models", []):
                    # Get detailed model info
                    details = self._get_model_details(model["name"])
                    model_details = details.get('details', {})

                    # Determine capabilities
                    capabilities = ["text"]
                    families = model_details.get('families', [])
                    if "clip" in families or "vision" in model["name"].lower() or "llava" in model["name"].lower():
                        capabilities.append("vision")

                    model_info = {
                        "id": model["name"],
                        "metadata": {
                            "size": model.get("size", 0),
                            "modified_at": model.get("modified_at", ""),
                            "digest": model.get("digest", ""),
                            "families": families,
                            "parameters": model_details.get('parameter_size', 'unknown'),
                            "capabilities": capabilities,
                            "details": details
                        }
                    }
                    models.append(model_info)
            return models
        except Exception as e:
            logger.error(f"Error fetching models from Ollama: {str(e)}")
            return []

    def _get_model_details(self, model_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific model."""
        try:
            response = requests.post(
                f"{self.host}/api/show",
                json={"name": model_name},
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.debug(f"Could not fetch details for {model_name}: {str(e)}")
            return {}

    def list_models(self) -> List[str]:
        """
        List available models from Ollama.

        Returns:
            List of model names
        """
        if not self.available:
            self.available = self._check_availability()
            if self.available:
                self.cached_models = self._fetch_models()

        return [model['id'] for model in self.cached_models]

    def get_model_metadata(self) -> List[Dict[str, Any]]:
        """
        Get detailed metadata for all available models.

        Returns:
            List of model dictionaries with full metadata
        """
        return self.cached_models

    def _process_image_data(self, image_data: str) -> str:
        """
        Process image data for Ollama.

        Args:
            image_data: Base64 encoded image, optionally with data URL prefix

        Returns:
            Clean base64 encoded image string
        """
        # Remove data URL prefix if present
        if ";" in image_data and "," in image_data:
            image_data = image_data.split(",", 1)[1]

        return image_data

    def _is_vision_model(self, model: str) -> bool:
        """
        Check if the model supports vision/multimodal inputs.

        Args:
            model: Model name to check

        Returns:
            True if model likely supports vision
        """
        # Check cached metadata first
        for cached_model in self.cached_models:
            if cached_model['id'] == model:
                return 'vision' in cached_model['metadata'].get('capabilities', [])

        # Fallback to name-based detection
        vision_indicators = ["vision", "llava", "bakllava", "clip", "image", "multi-modal", "multimodal"]
        model_lower = model.lower()
        return any(indicator in model_lower for indicator in vision_indicators)

    def complete(self, messages: List[Message], **kwargs) -> CompletionResponse:
        """
        Generate a completion from Ollama.

        Args:
            messages: List of Message objects
            **kwargs: Additional parameters:
                - model: Override default model
                - temperature: Float, default 0.7
                - max_tokens: Int, default 4096

        Returns:
            CompletionResponse with the generated text

        Raises:
            RuntimeError: If Ollama server is not available
        """
        if not self.available:
            raise RuntimeError(f"Ollama provider is not available at {self.host}")

        # Get parameters
        model = kwargs.get('model', self.model)
        temperature = kwargs.get('temperature', 0.7)
        max_tokens = kwargs.get('max_tokens', 4096)

        # Convert Message objects to Ollama format
        formatted_messages = []
        system_message = ""

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                formatted_messages.append({
                    "role": "assistant" if msg.role == "assistant" else "user",
                    "content": msg.content
                })

        # Prepare request
        payload = {
            "model": model,
            "messages": formatted_messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            },
            "stream": False
        }

        if system_message:
            payload["system"] = system_message

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                raise RuntimeError(f"Ollama API error ({response.status_code}): {response.text}")

            result = response.json()

            return CompletionResponse(
                content=result.get("message", {}).get("content", ""),
                model=model,
                usage={
                    "input_tokens": result.get("prompt_eval_count", 0),
                    "output_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
                },
                metadata={
                    "created_at": result.get("created_at"),
                    "done": result.get("done", True)
                }
            )

        except Exception as e:
            if hasattr(e, '__module__') and 'requests' in e.__module__:
                raise RuntimeError(f"Ollama request failed: {str(e)}")
            raise

    def stream_complete(self, messages: List[Message], **kwargs) -> Iterator[CompletionResponse]:
        """
        Stream a completion from Ollama.

        Args:
            messages: List of Message objects
            **kwargs: Additional parameters (model, temperature, max_tokens)

        Yields:
            CompletionResponse objects with incremental content

        Raises:
            RuntimeError: If Ollama server is not available
        """
        if not self.available:
            raise RuntimeError(f"Ollama provider is not available at {self.host}")

        # Get parameters
        model = kwargs.get('model', self.model)
        temperature = kwargs.get('temperature', 0.7)
        max_tokens = kwargs.get('max_tokens', 4096)

        # Convert Message objects to Ollama format
        formatted_messages = []
        system_message = ""

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                formatted_messages.append({
                    "role": "assistant" if msg.role == "assistant" else "user",
                    "content": msg.content
                })

        # Prepare request
        payload = {
            "model": model,
            "messages": formatted_messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            },
            "stream": True
        }

        if system_message:
            payload["system"] = system_message

        try:
            with requests.post(
                f"{self.host}/api/chat",
                json=payload,
                stream=True,
                timeout=120
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama API error ({response.status_code}): {response.text}")

                for line in response.iter_lines():
                    if not line:
                        continue

                    try:
                        chunk = json.loads(line)

                        # Extract content from chunk
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield CompletionResponse(
                                content=content,
                                model=model,
                                usage={
                                    "input_tokens": 0,  # Ollama doesn't provide incremental token counts
                                    "output_tokens": 0,
                                    "total_tokens": 0
                                },
                                metadata={
                                    "done": chunk.get("done", False)
                                }
                            )

                        # Final chunk with usage stats
                        if chunk.get("done", False):
                            yield CompletionResponse(
                                content="",
                                model=model,
                                usage={
                                    "input_tokens": chunk.get("prompt_eval_count", 0),
                                    "output_tokens": chunk.get("eval_count", 0),
                                    "total_tokens": chunk.get("prompt_eval_count", 0) + chunk.get("eval_count", 0)
                                },
                                metadata={
                                    "done": True,
                                    "created_at": chunk.get("created_at")
                                }
                            )

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in stream: {line}")
                    except Exception as e:
                        logger.error(f"Error processing stream chunk: {str(e)}")

        except Exception as e:
            if hasattr(e, '__module__') and 'requests' in e.__module__:
                raise RuntimeError(f"Ollama stream request failed: {str(e)}")
            raise

    def analyze_image(self, image: Union[str, bytes], prompt: str = "Describe this image", **kwargs) -> CompletionResponse:
        """
        Analyze an image using Ollama vision model.

        Args:
            image: Base64-encoded image string or raw bytes
            prompt: Question or instruction about the image
            **kwargs: Additional parameters:
                - model: Vision model to use (defaults to first vision model found)
                - temperature: Float, default 0.7
                - max_tokens: Int, default 4096

        Returns:
            CompletionResponse with image analysis

        Raises:
            RuntimeError: If no vision models available or server error
        """
        if not self.available:
            raise RuntimeError(f"Ollama provider is not available at {self.host}")

        # Get vision model
        model = kwargs.get('model', self.model)
        if not self._is_vision_model(model):
            # Try to find a vision model
            vision_models = [m['id'] for m in self.cached_models
                           if 'vision' in m['metadata'].get('capabilities', [])]
            if not vision_models:
                raise RuntimeError("No vision models available in Ollama")
            model = vision_models[0]
            logger.info(f"Switched to vision model: {model}")

        # Process image data
        if isinstance(image, bytes):
            image_data = base64.b64encode(image).decode('utf-8')
        else:
            image_data = self._process_image_data(image)

        # Get parameters
        temperature = kwargs.get('temperature', 0.7)
        max_tokens = kwargs.get('max_tokens', 4096)

        # Prepare request with image
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image", "image": image_data}
                    ]
                }
            ],
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            },
            "stream": False
        }

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                raise RuntimeError(f"Ollama API error ({response.status_code}): {response.text}")

            result = response.json()

            return CompletionResponse(
                content=result.get("message", {}).get("content", ""),
                model=model,
                usage={
                    "input_tokens": result.get("prompt_eval_count", 0),
                    "output_tokens": result.get("eval_count", 0),
                    "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
                },
                metadata={
                    "created_at": result.get("created_at"),
                    "done": result.get("done", True),
                    "vision": True
                }
            )

        except Exception as e:
            if hasattr(e, '__module__') and 'requests' in e.__module__:
                raise RuntimeError(f"Ollama vision request failed: {str(e)}")
            raise

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of the Ollama provider.

        Returns:
            Dict with provider status information
        """
        return {
            "name": "ollama",
            "available": self.available,
            "host": self.host,
            "model_count": len(self.cached_models),
            "models": [m["id"] for m in self.cached_models],
            "default_model": self.model
        }
