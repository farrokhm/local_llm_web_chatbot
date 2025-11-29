"""
Main application file for the chatbot API.

This file creates a FastAPI application that serves a simple chatbot frontend and
provides an API for chat interactions. The backend communicates with an Ollama
language model to generate responses.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from typing import Optional
import httpx
import json
import os

print("main.py loaded")

app = FastAPI()

# Enable Cross-Origin Resource Sharing (CORS) to allow the frontend,
# which may be served from a different origin, to communicate with this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Build a path to the frontend directory relative to this file to ensure it works
# regardless of the current working directory.
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

# Mount the static frontend files (HTML, JS, CSS) to the /frontend path.
# The `html=True` argument enables serving `index.html` for the root of the mount.
app.mount(
    "/frontend", StaticFiles(directory=frontend_dir, html=True), name="frontend"
)

# In-memory store for the conversation history.
SYSTEM_PROMPT = "You are a friendly and helpful AI assistant."
conversation_history = []


def reset_history():
    """Resets the conversation history to the initial system prompt."""
    global conversation_history
    conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]


class ChatRequest(BaseModel):
    """Request model for the /api/chat endpoint."""

    message: str
    model: Optional[str] = "tinyllama"
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7


def save_history_to_file():
    """Saves the current conversation history to a JSON file."""
    with open("chatlog.json", "w", encoding="utf-8") as f:
        json.dump(conversation_history, f, ensure_ascii=False, indent=2)


def load_history_from_file():
    """Loads conversation history from file or initializes it with a system prompt."""
    global conversation_history
    if os.path.exists("chatlog.json"):
        try:
            with open("chatlog.json", "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    loaded_history = json.loads(content)
                    # Ensure history is a list and starts with a system prompt
                    if (
                        isinstance(loaded_history, list)
                        and loaded_history
                        and loaded_history[0].get("role") == "system"
                    ):
                        conversation_history = loaded_history
                    else:
                        reset_history()
                else:
                    reset_history()  # File is empty
        except (json.JSONDecodeError, TypeError):
            print(
                "⚠️ Warning: chatlog.json is corrupted. Starting with a fresh history."
            )
            reset_history()
    else:
        reset_history()  # File doesn't exist


# Load conversation history from file when the application starts.
load_history_from_file()


@app.post("/api/chat")
async def chat(chat_request: ChatRequest):
    """
    Receives a user's message, gets a response from the Ollama model,
    and returns the model's reply. Supports both streaming and non-streaming.
    """
    global conversation_history
    conversation_history.append({"role": "user", "content": chat_request.message})

    json_payload = {
        "model": chat_request.model,
        "messages": conversation_history,
        "stream": chat_request.stream,
        "options": {"temperature": chat_request.temperature},
    }
    print("Request to Ollama:", json.dumps(json_payload, indent=2))

    if chat_request.stream:
        # Handle streaming response
        async def stream_generator():
            full_reply_content = ""
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    "http://localhost:11434/api/chat",
                    json=json_payload,
                    timeout=30.0,
                ) as response:
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            decoded_chunk = chunk.decode("utf-8")
                            # Each chunk can be a complete JSON object or part of one, ending with a newline.
                            # We yield it directly to the frontend which is set up to handle this.
                            yield decoded_chunk

                            # For history, we parse the line to get content
                            try:
                                # The decoded chunk might have leading/trailing whitespace
                                clean_chunk = decoded_chunk.strip()
                                if clean_chunk:
                                    json_line = json.loads(clean_chunk)
                                    if json_line.get("message", {}).get("content"):
                                        full_reply_content += json_line["message"]["content"]
                            except json.JSONDecodeError:
                                # This can happen with partial chunks, but we'll reassemble on the client
                                print(
                                    f"⚠️ Warning: Could not decode JSON chunk for history: {decoded_chunk}"
                                )

            # After the stream is complete, save the full response to history.
            if full_reply_content:
                conversation_history.append(
                    {"role": "assistant", "content": full_reply_content}
                )
                save_history_to_file()
                print("🤖 Assistant (streamed):", full_reply_content)

        return StreamingResponse(stream_generator(), media_type="application/x-ndjson")
    else:
        # Handle non-streaming response
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:11434/api/chat", json=json_payload, timeout=30.0
            )

        if response.status_code == 200:
            reply_data = response.json()
            reply = reply_data["message"]["content"]
            print("🤖 Assistant:", reply)

            conversation_history.append({"role": "assistant", "content": reply})
            save_history_to_file()
            return {"response": reply}
        else:
            print("❌ Error:", response.status_code, response.text)
            return {"error": f"Error {response.status_code}: {response.text}"}


@app.get("/api/history")
def get_history():
    """Returns the entire conversation history."""
    print("📜 Returning full conversation history")
    return {"history": conversation_history}


@app.post("/api/reset")
def reset():
    """Clears the conversation history and re-initializes the system prompt."""
    reset_history()
    save_history_to_file()
    print("🔄 Chat history reset")
    return {"message": "Chat history has been reset."}
