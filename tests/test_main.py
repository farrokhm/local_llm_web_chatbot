import pytest
import pytest_asyncio
import os
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock, AsyncMock

# Make sure the app can be imported
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from main import app, save_history_to_file, reset_history


# Fixture to manage the chatlog.json file for tests
@pytest.fixture(autouse=True)
def manage_chatlog():
    """Ensure a clean state for chatlog.json before and after each test."""
    reset_history()
    save_history_to_file()
    yield
    if os.path.exists("chatlog.json"):
        os.remove("chatlog.json")


# Fixture for the async test client
@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Provide an async client for making requests to the app."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_history_initial(client: AsyncClient):
    """Test that the initial history contains only the system prompt."""
    response = await client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert "history" in data
    assert len(data["history"]) == 1
    assert data["history"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_reset_endpoint(client: AsyncClient, mocker):
    """Test that the reset endpoint clears history and restores the system prompt."""
    # Mock the 'post' method of the client instance that will be created inside the app
    mock_post = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: {"message": {"role": "assistant", "content": "test"}},
        )
    )
    mock_client_instance = MagicMock(post=mock_post)

    # Patch the AsyncClient class in the 'main' module to return a context manager
    # that yields our mocked client instance.
    mocker.patch(
        "main.httpx.AsyncClient",
        return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_client_instance)),
    )

    # First, add something to the history. This will use the mock.
    await client.post("/api/chat", json={"message": "test message", "stream": False})

    # Now, reset it. This endpoint doesn't use httpx, so the mock is irrelevant here.
    reset_response = await client.post("/api/reset")
    assert reset_response.status_code == 200
    assert reset_response.json() == {"message": "Chat history has been reset."}

    # Check if history is back to the initial state
    history_response = await client.get("/api/history")
    data = history_response.json()
    assert len(data["history"]) == 1
    assert data["history"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_chat_non_streaming(client: AsyncClient, mocker):
    """Test the non-streaming chat endpoint, mocking the Ollama API."""
    mock_post = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: {"message": {"role": "assistant", "content": "Hello there!"}},
        )
    )
    mock_client_instance = MagicMock(post=mock_post)
    mocker.patch(
        "main.httpx.AsyncClient",
        return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_client_instance)),
    )

    response = await client.post("/api/chat", json={"message": "Hi", "stream": False})

    assert response.status_code == 200
    assert response.json() == {"response": "Hello there!"}

    history_response = await client.get("/api/history")
    history_data = history_response.json()["history"]
    assert len(history_data) == 3
    assert history_data[2]["content"] == "Hello there!"


@pytest.mark.asyncio
async def test_chat_streaming(client: AsyncClient, mocker):
    """Test the streaming chat endpoint, mocking the Ollama API stream."""

    async def mock_stream_generator():
        chunks = [
            b'{"message": {"role": "assistant", "content": "Hello "}}\n',
            b'{"message": {"role": "assistant", "content": "World"}}\n',
        ]
        for chunk in chunks:
            yield chunk

    # This is the mock for the response object returned by the stream
    mock_response = MagicMock()
    mock_response.aiter_bytes.return_value = mock_stream_generator()

    # This is the mock for the async context manager itself
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__.return_value = mock_response

    # The `stream` method on the client instance should return the context manager
    mock_client_instance = MagicMock()
    mock_client_instance.stream.return_value = mock_context_manager

    # Patch the AsyncClient class to return a context manager that yields our mocked client instance
    mocker.patch(
        "main.httpx.AsyncClient",
        return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_client_instance)),
    )

    response = await client.post(
        "/api/chat", json={"message": "Hi stream", "stream": True}
    )

    assert response.status_code == 200

    response_chunks = [chunk async for chunk in response.aiter_bytes()]
    full_response = b"".join(response_chunks).decode("utf-8")

    assert "Hello " in full_response
    assert "World" in full_response

    # Verify history was saved correctly after the stream
    # Note: in a real scenario, the app might wait for the stream to end before saving.
    # This test assumes the save happens after the generator is consumed.
    history_response = await client.get("/api/history")
    history_data = history_response.json()["history"]
    assert len(history_data) == 3
    assert history_data[2]["content"] == "Hello World"
