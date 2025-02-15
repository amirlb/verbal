"""
Handles conversation state and message processing logic.
"""

from datetime import datetime, timedelta
import traceback
from typing import Any, AsyncGenerator, Literal, TypedDict, Union

from anthropic import RateLimitError
from anthropic.types import (
    TextBlockParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
)

from .tools import BashTool, EditTool, ToolCollection


class Message(TypedDict):
    """A message in the conversation."""

    role: Literal["user", "assistant"]
    content: Union[TextBlockParam, ToolUseBlockParam, ToolResultBlockParam]
    timestamp: int


class Conversation:
    """A conversation that maintains tool state and message history."""

    def __init__(self, anthropic_client, model_name: str, system_prompt: str):
        """Initialize a new conversation with its own tool collection."""
        self.tool_collection = ToolCollection(
            BashTool(),
            EditTool(),
        )
        self.messages: list[Message] = []
        self.anthropic_client = anthropic_client
        self.model_name = model_name
        self.system_prompt = system_prompt

    def add_message(
        self,
        role: Literal["user", "assistant"],
        content: Union[TextBlockParam, ToolUseBlockParam, ToolResultBlockParam],
    ) -> None:
        """Add a message to the conversation history."""
        self.messages.append(
            Message(role=role, content=content, timestamp=datetime.now().timestamp())
        )

    async def get_model_responses(self) -> AsyncGenerator[TextBlockParam | ToolUseBlockParam, None]:
        response = await self.anthropic_client.messages.create(
            max_tokens=4096,
            messages=[{"role": msg["role"], "content": [msg["content"]]} for msg in self.messages],
            model=self.model_name,
            system=self.system_prompt,
            tools=self.tool_collection.to_params(),
        )

        for block in response.content:
            if block.type == "text":
                yield TextBlockParam(type="text", text=block.text)
            elif block.type == "tool_use":
                yield ToolUseBlockParam(
                    type="tool_use", id=block.id, name=block.name, input=block.input
                )
            else:
                raise ValueError(f"Unexpected block type: {block.type}")

    async def process_messages(self) -> AsyncGenerator[dict[str, Any], None]:
        """Process messages and yield events for SSE."""
        try:
            while self.messages[-1]["role"] == "user":
                async for content in self.get_model_responses():
                    self.add_message("assistant", content)
                    yield content
                    if content["type"] == "tool_use":
                        result = await self.tool_collection.run(
                            name=content["name"],
                            tool_input=content["input"],
                        )
                        result_block = ToolResultBlockParam(
                            type="tool_result",
                            tool_use_id=content["id"],
                            content=str(result),
                            is_error=bool(result.error),
                        )
                        self.add_message("user", result_block)
                        yield result_block
        except Exception as e:
            yield {"type": "error", "message": self._exception_to_error_message(e)}

    @staticmethod
    def _exception_to_error_message(e: Exception) -> str:
        if isinstance(e, RateLimitError):
            body = "You have been rate limited."
            if retry_after := e.response.headers.get("retry-after"):
                body += f" **Retry after {timedelta(seconds=int(retry_after))} (HH:MM:SS).** "
                body += "See our API [documentation](https://docs.anthropic.com/en/api/rate-limits) for more details."
            body += f"\n\n{e.message}"
            return body
        else:
            return traceback.format_exc()
