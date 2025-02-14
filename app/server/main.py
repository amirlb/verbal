"""
FastAPI backend service that implements the agent loop with Server-Sent Events (SSE).
"""

from datetime import datetime, timedelta
import json
import os
import platform
import traceback
from typing import Any, AsyncGenerator, Dict, Literal, TypedDict, Union, cast

from anthropic import (
    AsyncAnthropic,
    RateLimitError,
)
from anthropic.types import (
    TextBlockParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
)
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import httpx
from sse_starlette.sse import EventSourceResponse

from .tools import BashTool, EditTool, ToolCollection


class Message(TypedDict):
    """A message in the conversation."""
    role: Literal["user", "assistant"]
    content: Union[TextBlockParam, ToolUseBlockParam, ToolResultBlockParam]
    timestamp: datetime


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
* Prefer using specialized tools over writing complicated commands with the bash tool.
* There is no need to tell the user what tools you are using. They can see for themselves in a sidebar.
* The current date is {datetime.today().strftime("%A, %B %-d, %Y")}.
</SYSTEM_CAPABILITY>"""

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-5-sonnet-20241022")


app = FastAPI(title="Verbal")

# Global dictionary to store conversation history
conversation_history: dict[str, list[Message]] = {}


async def get_session_id(request: Request) -> str:
    """Get or create a session ID for the request."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        # In a real application, you'd want to generate a secure random session ID
        session_id = os.urandom(16).hex()
    return session_id


async def agent_loop(
    messages: list[Message],
) -> AsyncGenerator[str, None]:
    """Agent loop that processes messages and yields events for SSE."""
    tool_collection = ToolCollection(
        BashTool(),
        EditTool(),
    )

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)

    while messages[-1]["role"] == "user":
        try:
            # Convert our messages to MessageParam format for Claude
            claude_messages = [
                {"role": msg["role"], "content": [msg["content"]]} 
                for msg in messages
            ]
            
            response = await client.messages.create(
                max_tokens=4096,
                messages=claude_messages,
                model=MODEL_NAME,
                system=SYSTEM_PROMPT,
                tools=tool_collection.to_params(),
            )
        except Exception as e:
            yield json.dumps({"type": "error", "message": exception_to_error_message(e)})
            break

        for block in response.content:
            if block.type == "text":
                text_block = TextBlockParam(type="text", text=block.text)
                messages.append(Message(
                    role="assistant",
                    content=text_block,
                    timestamp=datetime.utcnow()
                ))
                yield json.dumps(text_block)
            elif block.type == "tool_use":
                use_block = ToolUseBlockParam(
                    type="tool_use", id=block.id, name=block.name, input=block.input
                )
                messages.append(Message(
                    role="assistant",
                    content=use_block,
                    timestamp=datetime.utcnow()
                ))
                yield json.dumps(use_block)
                result = await tool_collection.run(
                    name=block.name,
                    tool_input=cast(dict[str, Any], block.input),
                )
                result_block = ToolResultBlockParam(
                    type="tool_result",
                    tool_use_id=block.id,
                    content=str(result),
                    is_error=bool(result.error),
                )
                messages.append(Message(
                    role="user",
                    content=result_block,
                    timestamp=datetime.utcnow()
                ))
                yield json.dumps(result_block)
            else:
                yield json.dumps(
                    {"type": "error", "message": f"Unexpected block type: {block.type}"}
                )
                break


def exception_to_error_message(e: Exception) -> str:
    if isinstance(e, RateLimitError):
        body = "You have been rate limited."
        if retry_after := e.response.headers.get("retry-after"):
            body += f" **Retry after {timedelta(seconds=int(retry_after))} (HH:MM:SS).** "
            body += "See our API [documentation](https://docs.anthropic.com/en/api/rate-limits) for more details."
        body += f"\n\n{e.message}"
        return body
    else:
        return traceback.format_exc()


api = FastAPI(title="Verbal API")


@api.post("/chat")
async def chat_endpoint(request: Request) -> EventSourceResponse:
    """Chat endpoint that returns a Server-Sent Events stream."""
    data = await request.json()
    session_id = await get_session_id(request)

    # Initialize conversation history for new sessions
    if session_id not in conversation_history:
        conversation_history[session_id] = []

    # Add the new user message to the conversation history
    assert data["type"] == "text"
    user_message = Message(
        role="user",
        content=TextBlockParam(type="text", text=data["text"]),
        timestamp=datetime.utcnow()
    )
    conversation_history[session_id].append(user_message)

    response = EventSourceResponse(
        agent_loop(conversation_history[session_id]),
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
    conversations = {}
    for session_id, messages in conversation_history.items():
        first_msg = messages[0]["timestamp"]
        last_msg = messages[-1]["timestamp"]
        conversations[session_id] = {
            "message_count": len(messages),
            "created_at": first_msg.isoformat(),
            "last_message_at": last_msg.isoformat()
        }

    return JSONResponse(content={"conversations": conversations})


@api.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> JSONResponse:
    """Get the full history of a specific conversation."""
    if conversation_id not in conversation_history:
        return JSONResponse(
            status_code=404,
            content={"error": "Conversation not found"}
        )

    return JSONResponse(content={
        "messages": conversation_history[conversation_id]
    })


# Mount the API under /api
app.mount("/api", api)

# Serve static files at root
app.mount("/", StaticFiles(directory="/verbal/app/static", html=True), name="static")
