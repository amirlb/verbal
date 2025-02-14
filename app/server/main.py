"""
FastAPI backend service that implements the agent loop with Server-Sent Events (SSE).
"""

from datetime import datetime
import os
import platform

from anthropic import AsyncAnthropic
from anthropic.types import TextBlockParam
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import httpx
from sse_starlette.sse import EventSourceResponse

from .conversation import Conversation


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
* The current date is {datetime.today().strftime("%A, %B %-d, %Y")}.
</SYSTEM_CAPABILITY>"""

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-5-sonnet-20241022")


app = FastAPI(title="Verbal")

# Create a shared Anthropic client
anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)

# Global dictionary to store conversations
conversations: dict[str, Conversation] = {}


async def get_session_id(request: Request) -> str:
    """Get or create a session ID for the request."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        # In a real application, you'd want to generate a secure random session ID
        session_id = os.urandom(16).hex()
    return session_id


api = FastAPI(title="Verbal API")


@api.post("/chat")
async def chat_endpoint(request: Request) -> EventSourceResponse:
    """Chat endpoint that returns a Server-Sent Events stream."""
    data = await request.json()
    session_id = await get_session_id(request)

    # Get or create conversation for this session
    if session_id not in conversations:
        conversations[session_id] = Conversation(anthropic_client, MODEL_NAME, SYSTEM_PROMPT)

    conversation = conversations[session_id]

    # Add the new user message to the conversation history
    assert data["type"] == "text"
    conversation.add_message("user", TextBlockParam(type="text", text=data["text"]))

    response = EventSourceResponse(
        conversation.process_messages(),
        media_type="text/event-stream",
    )

    # Set session cookie in response
    response.set_cookie(key="session_id", value=session_id, httponly=True)
    return response


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
async def list_conversations() -> JSONResponse:
    """List all available conversation IDs with their message counts."""
    conversations_list = {}
    for session_id, conversation in conversations.items():
        first_msg = conversation.messages[0]["timestamp"]
        last_msg = conversation.messages[-1]["timestamp"]
        conversations_list[session_id] = {
            "message_count": len(conversation.messages),
            "created_at": first_msg,
            "last_message_at": last_msg,
        }

    return JSONResponse(content={"conversations": conversations_list})


@api.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> JSONResponse:
    """Get the full history of a specific conversation."""
    if conversation_id not in conversations:
        return JSONResponse(status_code=404, content={"error": "Conversation not found"})

    return JSONResponse(content={"messages": conversations[conversation_id].messages})


# Mount the API under /api
app.mount("/api", api)

# Serve static files at root
app.mount("/", StaticFiles(directory="/verbal/app/static", html=True), name="static")
