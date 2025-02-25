from datetime import timedelta
import traceback
from typing import Any, AsyncGenerator

from anthropic import AsyncAnthropic, RateLimitError
from anthropic.types import (
    TextBlockParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
)

from .db import DAL, Message
from .tools import BashTool, BashSessionsManager, EditTool, ToolCollection


class Conversations:
    def __init__(
        self, db: DAL, client: AsyncAnthropic, model_name: str, system_prompt: str
    ):
        self._db = db
        self._client = client
        self._bash_manager = BashSessionsManager(db)
        self._model_name = model_name
        self._system_prompt = system_prompt

    async def agent_loop(self, session_id: str) -> AsyncGenerator[dict[str, Any], None]:
        tool_collection = ToolCollection(
            BashTool(self._bash_manager, session_id),
            EditTool(),
        )
        conversation = self._db.get_conversation(session_id)
        try:
            while conversation[-1]["role"] == "user":
                response = await self._client.messages.create(
                    max_tokens=4096,
                    messages=[
                        {"role": msg["role"], "content": [msg["content"]]} for msg in conversation
                    ],
                    model=self._model_name,
                    system=self._system_prompt,
                    tools=tool_collection.to_params(),
                )
                for block in response.content:
                    content = self._parse_response_block(block)
                    message = Message(role="assistant", content=content)
                    self._db.add_message(session_id, message)
                    conversation.append(message)
                    yield content
                    if content["type"] == "tool_use":
                        result = await tool_collection.run(
                            name=content["name"],
                            tool_input=content["input"],
                        )
                        result_block = ToolResultBlockParam(
                            type="tool_result",
                            tool_use_id=content["id"],
                            content=str(result),
                            is_error=bool(result.error),
                        )
                        message = Message(role="user", content=result_block)
                        self._db.add_message(session_id, message)
                        conversation.append(message)
                        yield result_block
        except Exception as e:
            yield {"type": "error", "message": self._exception_to_error_message(e)}

    @staticmethod
    def _parse_response_block(block) -> TextBlockParam | ToolUseBlockParam:
        if block.type == "text":
            return TextBlockParam(type="text", text=block.text)
        elif block.type == "tool_use":
            return ToolUseBlockParam(
                type="tool_use", id=block.id, name=block.name, input=block.input
            )
        else:
            raise ValueError(f"Unexpected block type: {block.type}")

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
