"""
Entrypoint for streamlit, see https://docs.streamlit.io/
"""

import base64
import os
from pathlib import Path
import traceback
from contextlib import contextmanager
from datetime import timedelta
from enum import StrEnum
from functools import partial
from typing import cast

import streamlit as st
from anthropic import RateLimitError
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
)

from .loop import sampling_loop
from .tools import ToolResult

MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-5-sonnet-20241022")

STREAMLIT_STYLE = """
<style>
    /* Highlight the stop button in red */
    button[kind=header] {
        background-color: rgb(255, 75, 75);
        border: 1px solid rgb(255, 75, 75);
        color: rgb(255, 255, 255);
    }
    button[kind=header]:hover {
        background-color: rgb(255, 51, 51);
    }
     /* Hide the streamlit deploy button */
    .stAppDeployButton {
        visibility: hidden;
    }
</style>
"""

INTERRUPT_TEXT = "(user stopped or interrupted and wrote the following)"
INTERRUPT_TOOL_ERROR = "human stopped or interrupted tool execution"


class Sender(StrEnum):
    USER = "user"
    BOT = "assistant"
    TOOL = "tool"


def setup_state():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "responses" not in st.session_state:
        st.session_state.responses = {}
    if "tools" not in st.session_state:
        st.session_state.tools = {}
    if "in_sampling_loop" not in st.session_state:
        st.session_state.in_sampling_loop = False


async def main():
    """Render loop for streamlit"""
    st.set_page_config(page_title="Verbal", menu_items={"About": "Verbal by Amir Livne Bar-on"})
    setup_state()

    st.markdown(STREAMLIT_STYLE, unsafe_allow_html=True)

    logo_image_data = base64.b64encode(open('/verbal/assets/logo.png', 'rb').read()).decode()
    st.title(f"![Verbal](data:image/png;base64,{logo_image_data})")

    with st.sidebar:
        if st.button("Reset", type="primary"):
            with st.spinner("Resetting..."):
                st.session_state.clear()
                setup_state()

    new_message = st.chat_input("Type your command here...")

    # render past chats
    for message in st.session_state.messages:
        if isinstance(message["content"], str):
            _render_message(message["role"], message["content"])
        elif isinstance(message["content"], list):
            for block in message["content"]:
                # the tool result we send back to the Anthropic API isn't sufficient to render all details,
                # so we store the tool use responses
                if isinstance(block, dict) and block["type"] == "tool_result":
                    _render_message(
                        Sender.TOOL, st.session_state.tools[block["tool_use_id"]]
                    )
                else:
                    _render_message(
                        message["role"],
                        cast(BetaContentBlockParam | ToolResult, block),
                    )

    # render past chats
    if new_message:
        st.session_state.messages.append(
            {
                "role": Sender.USER,
                "content": [
                    *maybe_add_interruption_blocks(),
                    BetaTextBlockParam(type="text", text=new_message),
                ],
            }
        )
        _render_message(Sender.USER, new_message)

    try:
        most_recent_message = st.session_state["messages"][-1]
    except IndexError:
        return

    if most_recent_message["role"] is not Sender.USER:
        # we don't have a user message to respond to, exit early
        return

    with track_sampling_loop():
        # run the agent sampling loop with the newest message
        st.session_state.messages = await sampling_loop(
            model=MODEL_NAME,
            messages=st.session_state.messages,
            output_callback=partial(_render_message, Sender.BOT),
            tool_output_callback=_tool_output_callback,
            exception_callback=_render_error,
        )


def maybe_add_interruption_blocks():
    if not st.session_state.in_sampling_loop:
        return []
    # If this function is called while we're in the sampling loop, we can assume that the previous sampling loop was interrupted
    # and we should annotate the conversation with additional context for the model and heal any incomplete tool use calls
    result = []
    last_message = st.session_state.messages[-1]
    previous_tool_use_ids = [
        block["id"] for block in last_message["content"] if block["type"] == "tool_use"
    ]
    for tool_use_id in previous_tool_use_ids:
        st.session_state.tools[tool_use_id] = ToolResult(error=INTERRUPT_TOOL_ERROR)
        result.append(
            BetaToolResultBlockParam(
                tool_use_id=tool_use_id,
                type="tool_result",
                content=INTERRUPT_TOOL_ERROR,
                is_error=True,
            )
        )
    result.append(BetaTextBlockParam(type="text", text=INTERRUPT_TEXT))
    return result


@contextmanager
def track_sampling_loop():
    st.session_state.in_sampling_loop = True
    yield
    st.session_state.in_sampling_loop = False


def _tool_output_callback(tool_output: ToolResult, tool_id: str):
    """Handle a tool output by storing it to state and rendering it."""
    st.session_state.tools[tool_id] = tool_output
    _render_message(Sender.TOOL, tool_output)


def _render_error(error: Exception):
    if isinstance(error, RateLimitError):
        body = "You have been rate limited."
        if retry_after := error.response.headers.get("retry-after"):
            body += f" **Retry after {str(timedelta(seconds=int(retry_after)))} (HH:MM:SS).** See our API [documentation](https://docs.anthropic.com/en/api/rate-limits) for more details."
        body += f"\n\n{error.message}"
    else:
        body = str(error)
        body += "\n\n**Traceback:**"
        lines = "\n".join(traceback.format_exception(error))
        body += f"\n\n```{lines}```"
    st.error(f"**{error.__class__.__name__}**\n\n{body}", icon=":material/error:")
    # TODO: save an error log to /var/log/verbal
    # save_to_storage(f"error_{datetime.now().timestamp()}.md", body)


def _render_message(
    sender: Sender,
    message: str | BetaContentBlockParam | ToolResult,
):
    """Convert input from the user or output from the agent to a streamlit message."""
    # streamlit's hotreloading breaks isinstance checks, so we need to check for class names
    is_tool_result = not isinstance(message, str | dict)
    if not message:
        return
    with st.chat_message(sender, avatar="🛠️" if sender == Sender.BOT and message["type"] == "tool_use" else None):
        if is_tool_result:
            message = cast(ToolResult, message)
            if message.output:
                if message.__class__.__name__ == "CLIResult":
                    st.code(message.output)
                else:
                    st.markdown(message.output)
            if message.error:
                st.error(message.error)
        elif isinstance(message, dict):
            if message["type"] == "text":
                st.write(message["text"])
            elif message["type"] == "tool_use":
                st.code(f'Tool Use: {message["name"]}\nInput: {message["input"]}')
            else:
                # only expected return types are text and tool_use
                raise Exception(f'Unexpected response type {message["type"]}')
        else:
            st.markdown(message)
