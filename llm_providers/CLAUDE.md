# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Module: llm_providers

Unified LLM provider abstraction layer supporting 10+ AI providers with a consistent interface.

### Supported Providers

- **OpenAI**: GPT-4, DALL-E, Vision, Embeddings
- **Anthropic**: Claude 3.5, Vision
- **xAI**: Grok-3, Aurora (image generation), Vision
- **Mistral**: Pixtral Large/12B (Vision), Embeddings
- **Cohere**: Chat, Embeddings
- **Google Gemini**: 2.0 Flash/Pro, Vision, Embeddings
- **Perplexity**: Sonar Pro, Vision
- **Groq**: Fast inference
- **HuggingFace**: Stable Diffusion, various vision models, Embeddings
- **Manus**: Agent profiles, Vision
- **ElevenLabs**: Text-to-Speech
- **Ollama**: Local LLM inference (Llama, Llava, etc.), Vision via multimodal models, Embeddings

### Key Classes

#### BaseLLMProvider (Abstract Base)

All providers implement this interface:

```python
class BaseLLMProvider(ABC):
    def complete(self, messages: List[Message], **kwargs) -> CompletionResponse
    def stream_complete(self, messages: List[Message], **kwargs) -> Iterator
    def list_models(self) -> List[str]
    def generate_image(self, prompt: str, **kwargs) -> ImageResponse  # Optional
    def analyze_image(self, image: Union[str, bytes], prompt: str, **kwargs) -> CompletionResponse  # Optional
```

#### ProviderFactory

Singleton factory with lazy loading:

```python
from llm_providers import ProviderFactory

# Get cached singleton instance (reads API key from config)
provider = ProviderFactory.get_provider('xai')

# Create new instance with explicit API key
provider = ProviderFactory.create_provider('xai', api_key='key', model='grok-3')

# Check capabilities
caps = ProviderFactory.get_capabilities('xai')
# Returns: {'chat': True, 'vision': True, 'image_generation': True, ...}
```

#### Data Classes

```python
@dataclass
class Message:
    role: str  # "user", "assistant", "system"
    content: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class CompletionResponse:
    content: str
    model: str
    usage: Dict[str, int]  # {'input_tokens': N, 'output_tokens': M}
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ImageResponse:
    image_data: str  # Base64-encoded
    model: str
    revised_prompt: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class VisionMessage:
    role: str
    text: str
    image_data: Optional[str] = None  # Base64
    image_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

### Usage Examples

#### Basic Chat Completion

```python
from llm_providers import ProviderFactory, Message

provider = ProviderFactory.get_provider('xai')
response = provider.complete(
    messages=[
        Message(role='system', content='You are a helpful assistant'),
        Message(role='user', content='Explain quantum computing')
    ],
    max_tokens=1000,
    temperature=0.7
)
print(response.content)
print(f"Tokens used: {response.usage}")
```

#### Streaming Completion

```python
for chunk in provider.stream_complete(messages=messages):
    print(chunk.content, end='', flush=True)
```

#### Image Generation

```python
provider = ProviderFactory.get_provider('xai')  # or 'openai'
image_response = provider.generate_image(
    prompt="A futuristic cityscape at sunset",
    model="aurora",  # xAI's image model
    size="1024x1024"
)
# Save image
import base64
with open('output.png', 'wb') as f:
    f.write(base64.b64decode(image_response.image_data))
```

#### Vision Analysis

```python
import base64

with open('image.jpg', 'rb') as f:
    img_bytes = f.read()
    img_base64 = base64.b64encode(img_bytes).decode()

provider = ProviderFactory.get_provider('xai')
response = provider.analyze_image(
    image=img_base64,
    prompt="What's in this image? Be detailed."
)
print(response.content)
```

#### Multi-Provider Setup

```python
# Get different providers for different tasks
chat_provider = ProviderFactory.get_provider('xai')
image_provider = ProviderFactory.get_provider('openai')
vision_provider = ProviderFactory.get_provider('anthropic')

# Check what each can do
for name in ['xai', 'anthropic', 'openai']:
    caps = ProviderFactory.get_capabilities(name)
    print(f"{name}: vision={caps['vision']}, image_gen={caps['image_generation']}")
```

#### Using Ollama (Local LLM)

```python
# Ollama requires a local server running at http://localhost:11434
# Install: curl https://ollama.ai/install.sh | sh
# Pull a model: ollama pull llama3.2

from llm_providers import ProviderFactory, Message

# Get Ollama provider (no API key needed)
provider = ProviderFactory.get_provider('ollama')

# Check available models
models = provider.list_models()
print(f"Available models: {models}")

# Chat completion
response = provider.complete(
    messages=[Message(role='user', content='Explain Python in one sentence')],
    model='llama3.2',
    temperature=0.7
)
print(response.content)

# Streaming
for chunk in provider.stream_complete(
    messages=[Message(role='user', content='Count to 5')],
    model='llama3.2'
):
    print(chunk.content, end='', flush=True)

# Vision analysis (requires vision model like llava)
# ollama pull llava
import base64
with open('image.jpg', 'rb') as f:
    img_base64 = base64.b64encode(f.read()).decode()

response = provider.analyze_image(
    image=img_base64,
    prompt="What's in this image?",
    model='llava'
)
print(response.content)

# Custom Ollama host
import os
os.environ['OLLAMA_HOST'] = 'http://my-ollama-server:11434'
provider = ProviderFactory.get_provider('ollama')
```

### Complexity Router

Auto-selects provider based on task complexity (saves costs):

```python
from llm_providers.complexity_router import ComplexityRouter

router = ComplexityRouter(
    providers={
        'simple': ProviderFactory.get_provider('groq'),    # Fast, cheap
        'medium': ProviderFactory.get_provider('xai'),     # Balanced
        'complex': ProviderFactory.get_provider('anthropic')  # Best quality
    }
)

# Router analyzes task and selects appropriate provider
response = router.route_and_complete(
    task="Explain photosynthesis",
    messages=[Message(role='user', content='Explain photosynthesis')]
)
```

### Provider Capabilities Matrix

Use `PROVIDER_CAPABILITIES` constant:

```python
from llm_providers import PROVIDER_CAPABILITIES

# Check before calling
if PROVIDER_CAPABILITIES['xai']['image_generation']:
    provider.generate_image("...")
```

### Importing from Other Projects

```python
# Standard import
from llm_providers import ProviderFactory, Message, CompletionResponse

# Or from parent shared package
import sys
sys.path.insert(0, '/home/coolhand/shared')
from llm_providers import get_provider

provider = get_provider('xai')
```

### API Key Management

API keys loaded via `ConfigManager` from `/home/coolhand/API_KEYS.md`:

```python
# Keys are auto-loaded from:
# 1. /home/coolhand/API_KEYS.md
# 2. .env file
# 3. Environment variables

# Manual override
provider = ProviderFactory.create_provider(
    'xai',
    api_key='explicit-key-here'
)
```

### Testing

```python
import pytest
from llm_providers import ProviderFactory, Message

@pytest.mark.asyncio
async def test_provider():
    provider = ProviderFactory.get_provider('xai')
    response = provider.complete(
        messages=[Message(role='user', content='Hello')]
    )
    assert response.content
    assert response.usage['output_tokens'] > 0
```

### Available Provider Files

- `anthropic_provider.py` - Claude 3.5
- `openai_provider.py` - GPT-4, DALL-E
- `xai_provider.py` - Grok-3, Aurora
- `mistral_provider.py` - Pixtral
- `cohere_provider.py`
- `gemini_provider.py` - Google Gemini
- `perplexity_provider.py`
- `groq_provider.py` - Fast inference
- `huggingface_provider.py` - Various models
- `manus_provider.py` - Agent profiles
- `elevenlabs_provider.py` - TTS
- `ollama_provider.py` - Local Ollama LLM server
- `factory.py` - Provider factory and capabilities
- `complexity_router.py` - Auto-routing by task complexity

### Adding New Providers

1. Create `newprovider_provider.py` implementing `BaseLLMProvider`
2. Add to `factory.py` in `PROVIDER_CAPABILITIES` and provider map
3. Update `__init__.py` imports
4. Add tests to `tests/test_providers.py`

### Dependencies

Core: `requests`, `anthropic`, `openai`

Optional (install per provider):
- `pip install mistralai cohere google-generativeai elevenlabs`
- Or install all: `pip install -e .[all]`

### Advanced Capabilities (January 2026)

#### OpenAI Structured Outputs

```python
from pydantic import BaseModel

class MovieReview(BaseModel):
    title: str
    rating: float
    summary: str

provider = ProviderFactory.get_provider('openai')

# Structured output with Pydantic parsing
response = provider.parse_complete(
    messages=[Message(role='user', content='Review The Matrix')],
    response_format=MovieReview
)
review = response.metadata['parsed']  # MovieReview instance
print(f"{review.title}: {review.rating}/10")

# JSON-only output (guaranteed valid JSON)
response = provider.json_complete(
    messages=[Message(role='user', content='List 3 colors as JSON')]
)
import json
data = json.loads(response.content)
```

#### Anthropic Batch Processing (50% Cost Reduction)

```python
from llm_providers import ProviderFactory, Message, BatchRequest, BatchResponse

provider = ProviderFactory.get_provider('anthropic')

# Create batch of requests
requests = [
    BatchRequest(
        custom_id="summary-1",
        messages=[Message(role="user", content="Summarize: The quick brown fox...")],
        max_tokens=500
    ),
    BatchRequest(
        custom_id="translate-1",
        messages=[Message(role="user", content="Translate to French: Hello world")],
        max_tokens=100
    ),
]

# Submit batch (completes within 24 hours, typically faster)
batch = provider.batch_create(requests)
print(f"Batch ID: {batch.batch_id}, Status: {batch.status}")

# Check status
status = provider.batch_status(batch.batch_id)
print(f"Processing: {status.request_counts['processing']}")
print(f"Succeeded: {status.request_counts['succeeded']}")

# Get results when complete
if status.status == "ended":
    results = provider.batch_results(batch.batch_id)
    for result in results.results:
        print(f"{result['custom_id']}: {result['result']['content'][:100]}...")

# List all batches
batches = provider.batch_list(limit=10)
```

#### Gemini Google Search Grounding

```python
from llm_providers import ProviderFactory, Message, GroundedResponse

provider = ProviderFactory.get_provider('gemini')

# Search-grounded completion for real-time info
response = provider.search_grounded_complete(
    messages=[Message(role="user", content="What are today's top tech news?")],
    dynamic_threshold=0.3  # 0.0-1.0: lower = more search, higher = less
)

print(response.content)
print(f"Sources: {len(response.grounding_sources)}")
for source in response.grounding_sources:
    print(f"  - {source['title']}: {source['uri']}")
print(f"Search queries used: {response.search_queries}")

# Code execution
response = provider.code_execution_complete(
    messages=[Message(role="user", content="Calculate the first 10 Fibonacci numbers")]
)
print(response.content)
for result in response.metadata.get('code_execution', []):
    if result['type'] == 'code':
        print(f"Code: {result['code']}")
    elif result['type'] == 'result':
        print(f"Output: {result['output']}")
```

### Notes

- All providers normalize to standard `Message` and `CompletionResponse` formats
- Vision and image generation methods raise `NotImplementedError` if unsupported
- Factory uses singleton pattern - same instance returned for same provider name
- Streaming returns generator/iterator of response chunks
- Usage tracking included in all responses for cost monitoring
- **Batch processing** (Anthropic) offers 50% cost reduction for async bulk work
- **Structured outputs** (OpenAI) guarantee response matches Pydantic schema
- **Search grounding** (Gemini) provides real-time web information with citations
