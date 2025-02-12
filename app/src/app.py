import streamlit as st
from streamlit.components.v1 import html
import requests
from requests import RequestException
from openai import OpenAI

from config import SYSTEM_PROMPT, TOOLS, OPENAI_API_KEY, OPENAI_MODEL
from handlers import handle_tool_call
from tools import PendingInput

client = OpenAI(api_key=OPENAI_API_KEY)

def get_user_confirmation(pending_input: PendingInput) -> bool:
    placeholder = st.empty()
    with placeholder.container():
        st.warning(pending_input.description)
        col1, col2 = st.columns(2)
        if col1.button("Execute", key=f"execute_btn_{pending_input.tool_call_id}"):
            placeholder.empty()
            return True
        if col2.button("Cancel", key=f"cancel_btn_{pending_input.tool_call_id}"):
            placeholder.empty()
            return False
    return None

def get_chat_completion():
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=st.session_state.messages,
        tools=TOOLS,
    )
    completion = response.choices[0].message
    st.session_state.messages.append(completion)
    return completion

def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.session_state.pending_inputs = []
        st.session_state.new_messages = False

_display_message_counter = 0

def display_chat_history():
    global _display_message_counter
    for message in st.session_state.messages[_display_message_counter:]:
        if isinstance(message, dict):
            if message["role"] == "user":
                with st.chat_message("user"):
                    st.write(message["content"])
            # if message["role"] == "tool" and "error" in message["content"]:
            #     with st.chat_message("assistant", avatar="❗"):
            #         st.write(f"```\nmessage['content']['error']\n```")
        else:
            # assistant messages are API objects, i.e. assistant responses
            if message.content:
                with st.chat_message("assistant"):
                    st.write(message.content)
            for tool_call in message.tool_calls or []:
                with st.chat_message("assistant", avatar="🛠️"):
                    st.write(tool_call.function.name + tool_call.function.arguments)
    _display_message_counter = len(st.session_state.messages)

def check_pending_inputs():
    still_pending = []
    for pending_input in st.session_state.pending_inputs:
        choice = get_user_confirmation(pending_input)
        if choice is None:
            still_pending.append(pending_input)
            continue
        if choice:
            result = pending_input.callable()
            st.session_state.messages.append({
                "role": "tool",
                "tool_call_id": pending_input.tool_call_id,
                "content": result
            })
        else:
            st.session_state.messages.append({
                "role": "tool",
                "tool_call_id": pending_input.tool_call_id,
                "content": "User cancelled the operation"
            })
        st.session_state.new_messages = True
    st.session_state.pending_inputs = still_pending

def trigger_deployment():
    try:
        response = requests.post("http://host.docker.internal:8000/deploy/verbal")
        if response.status_code == 200:
            st.sidebar.success(response.text)
        else:
            st.sidebar.error(response.text)
    except RequestException as e:
        st.sidebar.error(f"Failed to trigger deployment: {e}")

def main():
    st.set_page_config(page_title="Verbal", layout="wide", initial_sidebar_state="collapsed")
    with st.sidebar:
        if st.button("Re-deploy"):
            trigger_deployment()
            html("<script>window.location.reload(true);</script>")

    init_session_state()
    st.title("Verbal")

    if prompt := st.chat_input("Enter command"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state.new_messages = True

    display_chat_history()
    check_pending_inputs()

    while st.session_state.new_messages and not st.session_state.pending_inputs:
        completion = get_chat_completion()
        st.session_state.new_messages = False
        display_chat_history()
        for tool_call in completion.tool_calls or []:
            immediate_response, pending_input = handle_tool_call(tool_call)
            if immediate_response is not None:
                st.session_state.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": immediate_response
                })
                st.session_state.new_messages = True
            if pending_input is not None:
                st.session_state.pending_inputs.append(pending_input)
                assert get_user_confirmation(pending_input) is None
        if not st.session_state.new_messages:
            display_chat_history()

if __name__ == "__main__":
    main()
