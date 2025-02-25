"""
FastAPI backend service that implements the agent loop with Server-Sent Events (SSE).
"""

from datetime import datetime
import json
import logging
import os
import platform
import sqlite3
import uuid

from anthropic import AsyncAnthropic
from anthropic.types import TextBlockParam
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, PlainTextResponse
import httpx
from sse_starlette.sse import EventSourceResponse

from .conversations import Conversations
from .db import DAL, Message


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)


# This system prompt is optimized for the Docker environment in this repository and
# specific tool combinations enabled.
# We encourage modifying this system prompt to ensure the model has context for the
# environment it is running in, and to provide any additional information that may be
# helpful for the task at hand.
SYSTEM_PROMPT = f"""<SYSTEM_CAPABILITY>
You are a natural language interface to controlling remote machines. You operate the machine on behalf of the user when they're on their phone and can't easily edit files or type code.
The user accesses the assistant via a mobile app, so you need to keep your answers short enough to usable with a small screen. You try to understand and anticipate what the user wants and act accordingly.

* You are utilising an Ubuntu virtual machine using {platform.machine()} architecture with internet access.
* You can feel free to install Ubuntu applications with your bash tool. Use curl instead of wget.
* When using your bash tool with commands that are expected to output very large quantities of text, redirect into a tmp file and use str_replace_editor or `grep -n -B <lines before> -A <lines after> <query> <filename>` to confirm output.
* Most of the user's projects are stored in `/workspace` directory. Your own code is in the `/verbal` directory.
* There is no need to tell the user what tools you are using. They can see for themselves in a sidebar.
* Keep your explanations very brief. When you make changes to files, just list the key functional changes in 1-2 lines. Don't explain code structure or CSS properties in detail unless specifically asked. The user is on a phone and needs to scroll as little as possible.
* The current date is {datetime.today().strftime("%A, %B %-d, %Y")}.
</SYSTEM_CAPABILITY>"""

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-7-sonnet-20250219")


db = DAL()

conversations = Conversations(
    db=db,
    client=AsyncAnthropic(api_key=ANTHROPIC_API_KEY, max_retries=4),
    model_name=MODEL_NAME,
    system_prompt=SYSTEM_PROMPT,
)


app = FastAPI(title="Verbal")

api = FastAPI(title="Verbal API")


@api.post("/chat")
async def chat_endpoint(request: Request) -> EventSourceResponse:
    """Chat endpoint that returns a Server-Sent Events stream."""
    data = await request.json()
    assert data["type"] == "text"
    session_id = data["session_id"]

    db.add_message(session_id, Message(role="user", content=TextBlockParam(type="text", text=data["text"])))

    async def stream():
        async for event in conversations.agent_loop(session_id):
            yield json.dumps(event)

    return EventSourceResponse(stream(), media_type="text/event-stream")


@api.get("/health")
async def health_endpoint() -> JSONResponse:
    """Check if the service is healthy and ready to accept requests."""
    return JSONResponse(content={"status": "ok"})


@api.post("/redeploy")
async def redeploy_endpoint() -> JSONResponse:
    """Trigger a redeployment of the service."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://host.docker.internal:8000/deploy/verbal")
            # We should never get the response!
            return JSONResponse(
                status_code=response.status_code,
                content={"error": response.text},
            )
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to trigger deployment: {str(e)}"},
        )


@api.get("/conversations")
async def list_conversations(request: Request) -> JSONResponse:
    """List all available conversation IDs with their message counts."""
    # Get user ID from header to filter conversations
    user_id = request.headers.get("x-forwarded-user")
    return JSONResponse(content={"conversations": db.list_conversations(user_id)})


@api.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> JSONResponse:
    """Get the full history of a specific conversation."""
    return JSONResponse(content={"messages": db.get_conversation(conversation_id)})


@api.post("/create_session")
async def create_session(request: Request) -> JSONResponse:
    """Record a new conversation in the database."""
    session_id = str(uuid.uuid4())
    # Get user ID from header if available
    user_id = request.headers.get("x-forwarded-user")
    db.create_session(session_id, user_id)
    return JSONResponse(content={"session_id": session_id})


@api.post("/conversations/{conversation_id}/rename")
async def rename_conversation(conversation_id: str, request: Request) -> JSONResponse:
    """Rename a conversation."""
    data = await request.json()
    if "name" not in data:
        return JSONResponse(status_code=400, content={"error": "Name is required"})
    db.rename_session(conversation_id, data["name"])
    return JSONResponse(content={"status": "ok"})


@api.post("/conversations/{conversation_id}/delete")
async def delete_conversation(conversation_id: str) -> JSONResponse:
    """Mark a conversation as deleted."""
    db.delete_session(conversation_id)
    return JSONResponse(content={"status": "ok"})


@api.get("/whoami")
async def whoami_endpoint(request: Request) -> JSONResponse:
    email = request.headers.get("x-forwarded-email")
    if email is None:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return JSONResponse(content={"email": email})

# NEW API endpoints for filesystem browsing
@api.get("/fs/list")
async def list_fs_endpoint(path: str) -> JSONResponse:
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Path not found"})
    if not os.path.isdir(path):
        return JSONResponse(status_code=400, content={"error": "Not a directory"})
    items = []
    for name in os.listdir(path):
        full_path = os.path.join(path, name)
        if os.path.isdir(full_path):
            type_str = "directory"
        elif os.path.isfile(full_path):
            type_str = "file"
        else:
            type_str = "other"
        items.append({"name": name, "type": type_str})
    return JSONResponse(content={"contents": items})

@api.get("/fs/file")
async def get_fs_file_endpoint(path: str):
    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "Path not found"})
    if not os.path.isfile(path):
        return JSONResponse(status_code=400, content={"error": "Not a file"})
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    return PlainTextResponse(content, media_type='text/plain')

# Mount the API under /api
app.mount("/api", api)

# Serve static files at root
app.mount("/", StaticFiles(directory="/verbal/app/static", html=True), name="static")
