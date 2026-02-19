"""
Google Gemini provider implementation.
Supports chat, vision, and Google Search grounding.
"""

from typing import List, Dict, Any, Union, Optional
from dataclasses import dataclass
from . import BaseLLMProvider, Message, CompletionResponse
import os
import base64


@dataclass
class GroundedResponse:
    """Response with Google Search grounding information."""
    content: str
    model: str
    usage: Dict[str, int]
    grounding_sources: List[Dict[str, str]]  # [{title, uri, snippet}]
    search_queries: List[str]  # Queries used to search
    metadata: Optional[Dict[str, Any]] = None


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider."""

    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: str = None, model: str = None):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")

        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model)

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.genai = genai
        except ImportError:
            raise ImportError(
                "google-generativeai package is required. "
                "Install with: pip install google-generativeai"
            )

    def complete(self, messages: List[Message], **kwargs) -> CompletionResponse:
        """Generate a completion using Gemini."""
        model_name = kwargs.get("model", self.model)
        model = self.genai.GenerativeModel(model_name)

        # Convert messages to Gemini format
        # Gemini uses a simpler format: just user/model roles
        gemini_messages = []
        for msg in messages:
            role = "user" if msg.role in ["user", "system"] else "model"
            gemini_messages.append({
                "role": role,
                "parts": [msg.content]
            })

        # Use chat if multiple messages, otherwise generate_content
        if len(gemini_messages) > 1:
            chat = model.start_chat(history=gemini_messages[:-1])
            response = chat.send_message(
                gemini_messages[-1]["parts"][0],
                generation_config=self._get_generation_config(kwargs)
            )
        else:
            response = model.generate_content(
                gemini_messages[0]["parts"][0],
                generation_config=self._get_generation_config(kwargs)
            )

        # Extract token counts
        usage = {
            "prompt_tokens": response.usage_metadata.prompt_token_count,
            "completion_tokens": response.usage_metadata.candidates_token_count,
            "total_tokens": response.usage_metadata.total_token_count,
        }

        return CompletionResponse(
            content=response.text,
            model=model_name,
            usage=usage,
            metadata={
                "finish_reason": response.candidates[0].finish_reason.name if response.candidates else None
            }
        )

    def stream_complete(self, messages: List[Message], **kwargs):
        """Stream a completion using Gemini."""
        model_name = kwargs.get("model", self.model)
        model = self.genai.GenerativeModel(model_name)

        # Convert messages to Gemini format
        gemini_messages = []
        for msg in messages:
            role = "user" if msg.role in ["user", "system"] else "model"
            gemini_messages.append({
                "role": role,
                "parts": [msg.content]
            })

        # Stream response
        if len(gemini_messages) > 1:
            chat = model.start_chat(history=gemini_messages[:-1])
            response = chat.send_message(
                gemini_messages[-1]["parts"][0],
                generation_config=self._get_generation_config(kwargs),
                stream=True
            )
        else:
            response = model.generate_content(
                gemini_messages[0]["parts"][0],
                generation_config=self._get_generation_config(kwargs),
                stream=True
            )

        for chunk in response:
            if chunk.text:
                yield chunk.text

    def list_models(self) -> List[str]:
        """List available Gemini models."""
        try:
            models = self.genai.list_models()
            return [
                model.name.replace("models/", "")
                for model in models
                if "generateContent" in model.supported_generation_methods
            ]
        except Exception:
            # Fallback list of known models (2025)
            return [
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-pro",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ]

    def _get_generation_config(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Gemini-compatible generation config from kwargs."""
        config = {}
        if "temperature" in kwargs:
            config["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            config["max_output_tokens"] = kwargs["max_tokens"]
        if "top_p" in kwargs:
            config["top_p"] = kwargs["top_p"]
        if "top_k" in kwargs:
            config["top_k"] = kwargs["top_k"]
        return config

    def analyze_image(self, image: Union[str, bytes], prompt: str = "Describe this image", **kwargs) -> CompletionResponse:
        """
        Analyze an image using Gemini Vision.

        Args:
            image: Base64-encoded string or raw bytes
            prompt: Question about the image
            **kwargs: Optional parameters
                - model: Vision model (default: "gemini-2.0-flash")
                - max_tokens: Maximum response length

        Returns:
            CompletionResponse with image analysis
        """
        model_name = kwargs.get("model", "gemini-2.0-flash")
        max_tokens = kwargs.get("max_tokens", 1024)

        # Convert bytes to base64 if needed
        if isinstance(image, bytes):
            image_b64 = base64.b64encode(image).decode('utf-8')
        else:
            image_b64 = image

        # Detect media type from base64 header
        mime_type = "image/jpeg"
        if image_b64.startswith('/9j/'):
            mime_type = "image/jpeg"
        elif image_b64.startswith('iVBOR'):
            mime_type = "image/png"
        elif image_b64.startswith('R0lGOD'):
            mime_type = "image/gif"
        elif image_b64.startswith('UklGR'):
            mime_type = "image/webp"

        # Create model and generate content with image
        model = self.genai.GenerativeModel(model_name)

        # Construct parts with text and image
        parts = [
            prompt,
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": image_b64
                }
            }
        ]

        response = model.generate_content(
            parts,
            generation_config={"max_output_tokens": max_tokens}
        )

        # Extract token counts
        usage = {
            "prompt_tokens": response.usage_metadata.prompt_token_count,
            "completion_tokens": response.usage_metadata.candidates_token_count,
            "total_tokens": response.usage_metadata.total_token_count,
        }

        return CompletionResponse(
            content=response.text,
            model=model_name,
            usage=usage,
            metadata={
                "finish_reason": response.candidates[0].finish_reason.name if response.candidates else None,
                "vision": True
            }
        )

    # =========================================================================
    # GOOGLE SEARCH GROUNDING (Real-time web information)
    # =========================================================================

    def search_grounded_complete(
        self,
        messages: List[Message],
        dynamic_threshold: float = 0.3,
        **kwargs
    ) -> GroundedResponse:
        """
        Generate a completion with Google Search grounding for real-time information.

        Uses Google Search to retrieve current information and ground the response
        in factual, up-to-date sources. Ideal for queries about:
        - Current events and news
        - Stock prices and market data
        - Weather and sports scores
        - Recent product releases
        - Any time-sensitive information

        Args:
            messages: List of Message objects
            dynamic_threshold: 0.0-1.0, controls when grounding is triggered
                - Lower = more frequent grounding (more web searches)
                - Higher = less frequent grounding (fewer searches)
                - Default 0.3 provides good balance
            **kwargs: Standard generation parameters (temperature, max_tokens, etc.)

        Returns:
            GroundedResponse with:
                - content: The generated response
                - grounding_sources: List of source citations
                - search_queries: Queries used for grounding

        Example:
            response = provider.search_grounded_complete(
                messages=[Message(role="user", content="What are today's top tech news?")],
                dynamic_threshold=0.2  # More aggressive grounding
            )
            print(response.content)
            for source in response.grounding_sources:
                print(f"  Source: {source['title']} - {source['uri']}")
        """
        from google.generativeai import protos

        model_name = kwargs.get("model", self.model)

        # Configure Google Search grounding tool
        google_search_tool = {
            "google_search_retrieval": {
                "dynamic_retrieval_config": {
                    "mode": "MODE_DYNAMIC",
                    "dynamic_threshold": dynamic_threshold
                }
            }
        }

        # Create model with grounding tool
        model = self.genai.GenerativeModel(
            model_name=model_name,
            tools=[google_search_tool]
        )

        # Convert messages to Gemini format
        gemini_messages = []
        for msg in messages:
            role = "user" if msg.role in ["user", "system"] else "model"
            gemini_messages.append({
                "role": role,
                "parts": [msg.content]
            })

        # Generate with grounding
        if len(gemini_messages) > 1:
            chat = model.start_chat(history=gemini_messages[:-1])
            response = chat.send_message(
                gemini_messages[-1]["parts"][0],
                generation_config=self._get_generation_config(kwargs)
            )
        else:
            response = model.generate_content(
                gemini_messages[0]["parts"][0],
                generation_config=self._get_generation_config(kwargs)
            )

        # Extract grounding metadata
        grounding_sources = []
        search_queries = []

        if response.candidates:
            candidate = response.candidates[0]

            # Extract grounding metadata if available
            if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                gm = candidate.grounding_metadata

                # Get search queries used
                if hasattr(gm, 'web_search_queries') and gm.web_search_queries:
                    search_queries = list(gm.web_search_queries)

                # Get grounding chunks (sources)
                if hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                    for chunk in gm.grounding_chunks:
                        if hasattr(chunk, 'web') and chunk.web:
                            grounding_sources.append({
                                "title": chunk.web.title if hasattr(chunk.web, 'title') else "",
                                "uri": chunk.web.uri if hasattr(chunk.web, 'uri') else "",
                            })

                # Alternative: grounding_supports for inline citations
                if hasattr(gm, 'grounding_supports') and gm.grounding_supports:
                    for support in gm.grounding_supports:
                        if hasattr(support, 'grounding_chunk_indices'):
                            # These reference the grounding_chunks above
                            pass

        # Extract token counts
        usage = {
            "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
            "completion_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
            "total_tokens": response.usage_metadata.total_token_count if response.usage_metadata else 0,
        }

        return GroundedResponse(
            content=response.text,
            model=model_name,
            usage=usage,
            grounding_sources=grounding_sources,
            search_queries=search_queries,
            metadata={
                "finish_reason": candidate.finish_reason.name if response.candidates else None,
                "grounded": len(grounding_sources) > 0,
                "dynamic_threshold": dynamic_threshold
            }
        )

    def code_execution_complete(
        self,
        messages: List[Message],
        **kwargs
    ) -> CompletionResponse:
        """
        Generate a completion with code execution capability.

        Gemini can write and execute Python code to solve problems involving
        calculations, data manipulation, or algorithmic tasks.

        Args:
            messages: List of Message objects
            **kwargs: Standard generation parameters

        Returns:
            CompletionResponse with code execution results in metadata

        Example:
            response = provider.code_execution_complete(
                messages=[Message(role="user", content="Calculate the first 10 Fibonacci numbers")]
            )
            print(response.content)  # Shows code and results
        """
        model_name = kwargs.get("model", self.model)

        # Create model with code execution tool
        model = self.genai.GenerativeModel(
            model_name=model_name,
            tools=["code_execution"]
        )

        # Convert messages to Gemini format
        gemini_messages = []
        for msg in messages:
            role = "user" if msg.role in ["user", "system"] else "model"
            gemini_messages.append({
                "role": role,
                "parts": [msg.content]
            })

        # Generate with code execution
        if len(gemini_messages) > 1:
            chat = model.start_chat(history=gemini_messages[:-1])
            response = chat.send_message(
                gemini_messages[-1]["parts"][0],
                generation_config=self._get_generation_config(kwargs)
            )
        else:
            response = model.generate_content(
                gemini_messages[0]["parts"][0],
                generation_config=self._get_generation_config(kwargs)
            )

        # Extract code execution results from parts
        code_results = []
        text_content = []

        for part in response.parts:
            if hasattr(part, 'text') and part.text:
                text_content.append(part.text)
            if hasattr(part, 'executable_code') and part.executable_code:
                code_results.append({
                    "type": "code",
                    "language": part.executable_code.language.name if hasattr(part.executable_code.language, 'name') else "python",
                    "code": part.executable_code.code
                })
            if hasattr(part, 'code_execution_result') and part.code_execution_result:
                code_results.append({
                    "type": "result",
                    "outcome": part.code_execution_result.outcome.name if hasattr(part.code_execution_result.outcome, 'name') else "success",
                    "output": part.code_execution_result.output
                })

        # Extract token counts
        usage = {
            "prompt_tokens": response.usage_metadata.prompt_token_count if response.usage_metadata else 0,
            "completion_tokens": response.usage_metadata.candidates_token_count if response.usage_metadata else 0,
            "total_tokens": response.usage_metadata.total_token_count if response.usage_metadata else 0,
        }

        return CompletionResponse(
            content="\n".join(text_content) if text_content else response.text,
            model=model_name,
            usage=usage,
            metadata={
                "finish_reason": response.candidates[0].finish_reason.name if response.candidates else None,
                "code_execution": code_results,
                "has_code": len(code_results) > 0
            }
        )
