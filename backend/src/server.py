"""
FastAPI backend service that implements the agent loop with Server-Sent Events (SSE).
"""

import asyncio
from datetime import datetime, timedelta
import json
import os
import platform
from typing import Any, AsyncGenerator, cast

from anthropic import (
    AsyncAnthropic,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    RateLimitError,
)
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .tools import BashTool, EditTool, ToolCollection, ToolResult


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
* The current date is {datetime.today().strftime('%A, %B %-d, %Y')}.
</SYSTEM_CAPABILITY>"""

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-5-sonnet-20241022")


app = FastAPI(title="Verbal Backend")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def agent_loop(
    messages: list[BetaMessageParam],
) -> AsyncGenerator[dict[str, Any], None]:
    """Agent loop that processes messages and yields events for SSE."""
    tool_collection = ToolCollection(
        BashTool(),
        EditTool(),
    )

    client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY, max_retries=4)

    try:
        response = await client.messages.create(
            max_tokens=4096,
            messages=messages,
            model=MODEL_NAME,
            system=SYSTEM_PROMPT,
            tools=tool_collection.to_params(),
        )
    except RateLimitError as e:
        body = "You have been rate limited."
        if retry_after := e.response.headers.get("retry-after"):
            body += f" **Retry after {str(timedelta(seconds=int(retry_after)))} (HH:MM:SS).** See our API [documentation](https://docs.anthropic.com/en/api/rate-limits) for more details."
        body += f"\n\n{e.message}"
        yield json.dumps({"type": "error", "text": body})
        return
    except (APIError, APIStatusError, APIResponseValidationError) as e:
        yield json.dumps({"type": "error", "text": str(e)})
        return

    for block in response.content:
        if block.type == "text":
            yield json.dumps({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            yield json.dumps({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input
            })
            result = await tool_collection.run(
                name=block.name,
                tool_input=cast(dict[str, Any], block.input),
            )
            yield json.dumps({
                "type": "tool_result",
                "tool_use_id": block.id,
                "result": {
                    "output": result.output or "",
                    "error": result.error,
                    "system": result.system,
                },
            })
        else:
            assert False, f"Unexpected block type: {block.type}"


def to_block(message: dict[str, Any]) -> BetaTextBlockParam | BetaToolUseBlockParam:
    if message["type"] == "text":
        return BetaTextBlockParam(type="text", text=message["text"])
    elif message["type"] == "tool_use":
        return BetaToolUseBlockParam(
            type="tool_use",
            id=message["id"],
            name=message["name"],
            input=message["input"]
        )
    elif message["type"] == "tool_result":
        return BetaToolResultBlockParam(
            type="tool_result",
            tool_use_id=message["tool_use_id"],
            content=tool_result_content(message["result"], message["is_error"]),
            is_error=message["is_error"]
        )


def tool_result_content(result: ToolResult, is_error: bool) -> str:
    system_prefix = f"<system>{result['system']}</system>" if result['system'] else ""
    content = result["error"] if is_error else result["output"]
    return f"{system_prefix}{content}"


@app.post("/chat")
async def chat_endpoint(request: Request) -> EventSourceResponse:
    """Chat endpoint that returns a Server-Sent Events stream."""
    data = await request.json()
    messages: list[BetaMessageParam] = [
        BetaMessageParam(
            role=message["role"],
            content=[to_block(message["content"])],
        )
        for message in data["messages"]
    ]

    return EventSourceResponse(
        agent_loop(messages),
        media_type="text/event-stream",
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}