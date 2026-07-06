import pytest
from unittest.mock import MagicMock
from google.genai import types

# Mock google.auth.default to prevent DefaultCredentialsError during import/initialization
try:
    import google.auth
    google.auth.default = lambda *args, **kwargs: (MagicMock(), "dummy-project-id")
except Exception:
    pass

@pytest.fixture(autouse=True)
def mock_genai_client(monkeypatch):
    """Fixture to mock google.genai.Client methods to avoid network requests during tests"""
    
    # Mock generate_content_stream returning an async iterator with aclose when awaited
    async def mock_stream(*args, **kwargs):
        class AsyncIterator:
            def __init__(self):
                self.yielded = False
            def __aiter__(self):
                return self
            async def __anext__(self):
                if self.yielded:
                    raise StopAsyncIteration
                self.yielded = True
                candidate = types.Candidate(
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text="Mocked streaming response")],
                    ),
                    finish_reason=types.FinishReason.STOP,
                )
                return types.GenerateContentResponse(
                    candidates=[candidate],
                )
            async def aclose(self):
                pass
        return AsyncIterator()

    # Mock generate_content
    async def mock_generate(*args, **kwargs):
        candidate = types.Candidate(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text="Mocked static response")],
            ),
            finish_reason=types.FinishReason.STOP,
        )
        return types.GenerateContentResponse(
            candidates=[candidate],
        )

    # Patch google.genai.Client class properties/methods
    import google.genai
    google.genai.Client.aio = MagicMock()
    google.genai.Client.aio.models = MagicMock()
    google.genai.Client.aio.models.generate_content_stream = mock_stream
    google.genai.Client.aio.models.generate_content = mock_generate
