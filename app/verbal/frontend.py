import json
import os
from pathlib import Path
from datetime import timedelta
from enum import StrEnum
import traceback
from typing import Any, TypedDict, Literal, cast

import requests
from requests import RequestException
import streamlit as st


MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-5-sonnet-20241022")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


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
    ASSISTANT = "assistant"


def init_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "responses" not in st.session_state:
        st.session_state.responses = {}
    if "pending_tool_use_ids" not in st.session_state:
        st.session_state.pending_tool_use_ids = []


class ToolResult(TypedDict):
    output: str
    error: str
    system: str


class TextBlock(TypedDict):
    type: Literal["text"]
    text: str


class ToolResultBlock(TypedDict):
    type: Literal["tool_result"]
    tool_use_id: str
    result: ToolResult
    is_error: bool


class ToolUseBlock(TypedDict):
    type: Literal["tool_use"]
    id: str
    name: str
    input: dict[str, Any]


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock


class Message(TypedDict):
    role: Sender
    content: ContentBlock


def _render_message(message: Message) -> None:
    """Render a message in the chat UI."""
    if message["content"]["type"] == "text":
        with st.chat_message(message["role"]):
            st.markdown(message["content"]["text"])

    elif message["content"]["type"] == "tool_use":
        with st.chat_message(message["role"], avatar="🛠"):
            st.code(message["content"]["name"] + json.dumps(message["content"]["input"]))

    elif message["content"]["type"] == "tool_result":
        result = message["content"]["result"]
        with st.chat_message("TOOL"):
            if result["error"]:
                st.error(result["error"])
            else:
                if result["system"]:
                    st.info(result["system"])
                if result["output"]:
                    st.code(result["output"])


def display_chat_history() -> None:
    """Display the chat history."""
    for message in st.session_state.messages:
        _render_message(message)


def setup_page() -> None:
    """Initialize the page configuration and styling."""
    st.set_page_config(
        page_title="Verbal",
        page_icon=Path("/verbal/assets/icon.png"),
        menu_items={"About": "Verbal by Amir Livne Bar-on"},
    )
    st.markdown(STREAMLIT_STYLE, unsafe_allow_html=True)
    st.title("Verbal command line")


def setup_sidebar() -> None:
    """Setup the sidebar with reset and re-deploy buttons."""
    with st.sidebar:
        if st.button("Reset", type="primary"):
            with st.spinner("Resetting..."):
                st.session_state.clear()
                init_session_state()

        if st.button("Re-deploy"):
            trigger_deployment()
            st.html("<script>window.location.reload(true);</script>")


def process_new_message(new_message: str) -> None:
    """Process and display a new user message."""
    message = Message(role=Sender.USER, content=TextBlock(type="text", text=new_message))
    st.session_state.messages.append(message)
    _render_message(message)


def handle_sse_event(event_data: str) -> None:
    """Handle a single SSE event and update the UI accordingly."""
    if not event_data.startswith("data: "):
        return

    data = json.loads(event_data[6:])  # Skip "data: " prefix

    if data["type"] == "error":
        st.error(data["text"], icon="🚨")
        return

    if data["type"] == "text":
        message = Message(role=Sender.ASSISTANT, content=TextBlock(type="text", text=data["text"]))
        st.session_state.messages.append(message)
        _render_message(message)

    if data["type"] == "tool_use":
        message = Message(
            role=Sender.ASSISTANT,
            content=ToolUseBlock(
                type="tool_use", id=data["id"], name=data["name"], input=data["input"]
            ),
        )
        st.session_state.messages.append(message)
        _render_message(message)
        st.session_state.pending_tool_use_ids.append(data["id"])

    elif data["type"] == "tool_result":
        message = Message(
            role=Sender.USER,
            content=ToolResultBlock(
                type="tool_result",
                tool_use_id=data["tool_use_id"],
                result=data["result"],
                is_error=bool(data["result"]["error"]),
            ),
        )
        st.session_state.messages.append(message)
        _render_message(message)
        st.session_state.pending_tool_use_ids.remove(data["tool_use_id"])


def process_chat_response():
    """Process the chat response from the backend."""
    response = requests.post(
        f"{BACKEND_URL}/chat",
        json={"messages": st.session_state.messages},
        stream=True,
        headers={"Accept": "text/event-stream"},
    )
    response.raise_for_status()

    for line in response.iter_lines():
        if line:
            handle_sse_event(line.decode())


async def main():
    """Render loop for streamlit"""
    setup_page()
    init_session_state()
    display_chat_history()

    setup_sidebar()

    new_message = st.chat_input("Type your command here...")
    if not new_message:
        return

    process_new_message(new_message)
    for tool_use_id in st.session_state.pending_tool_use_ids:
        st.session_state.messages.append(
            Message(
                role=Sender.USER,
                content=ToolResultBlock(
                    type="tool_result",
                    tool_use_id=tool_use_id,
                    content=INTERRUPT_TOOL_ERROR,
                    is_error=True,
                ),
            )
        )
    st.session_state.pending_tool_use_ids = []

    try:
        while st.session_state.messages[-1]["role"] != Sender.ASSISTANT:
            process_chat_response()
    except Exception:
        st.error(traceback.format_exc(), icon="🚨")


def trigger_deployment():
    """Trigger a deployment of the service."""
    try:
        response = requests.post("http://host.docker.internal:8000/deploy/verbal")
        if response.status_code == requests.codes.ok:
            st.sidebar.success(response.text)
        else:
            st.sidebar.error(response.text)
    except RequestException as e:
        st.sidebar.error(f"Failed to trigger deployment: {e}")
