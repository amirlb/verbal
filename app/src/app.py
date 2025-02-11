from dataclasses import dataclass
import json

import requests
from requests import RequestException
import streamlit as st
from streamlit.components.v1 import html
import os
import subprocess
from openai import OpenAI
from typing import Callable
import platform, datetime


client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
model = os.getenv('OPENAI_MODEL', "gpt-4o-mini")


SYSTEM_PROMPT = f"""You are a natural language interface to controlling
remote machines. You operate the machine on behalf of the user when they're
on their phone and can't easily edit files or type code.
The user accesses the assistant via a mobile app, so you need to keep
your answers short enough to usable with a small screen.
You try to understand and anticipate what the user wants and act accordingly.

* You are utilising an Debian virtual machine using {platform.machine()} architecture with internet access.
* You can feel free to install Debian applications with your bash tool.
* When using your bash tool with commands that are expected to output very large quantities of text, redirect into a tmp file and use `grep -n -B <lines before> -A <lines after> <query> <filename>` to confirm output.
* Prefer using specialized tools over writing complicated commands with the bash tool.
* The current date is {datetime.datetime.today().strftime('%A, %B %-d, %Y')}."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a command in a shell on the same machine as the server runs, which is a container based on the python3.12-slim image (derived from Debian). The response is a JSON object with stdout, stderr, and exitcode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The exact text that would be run in bash"
                    }
                },
                "required": [
                    "command"
                ],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Returns the full contents of the file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The full path of the file, starting with /"
                    },
                    "from_line": {
                        "type": "int",
                        "description": "Start from this line (1-based, optional)"
                    },
                    "to_line": {
                        "type": "int",
                        "description": "Show content up to this line and including it (1-based, optional)"
                    }
                },
                "required": [
                    "path"
                ],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "view_path",
            "description": "List files and directories two levels deep into the directory tree",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The full path of the directory, starting with /"
                    }
                },
                "required": ["path"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "str_replace",
    #         "description": "Replace occurrences of a string in a file",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "path": {
    #                     "type": "string",
    #                     "description": "The full path of the file, starting with /"
    #                 },
    #                 "old_str": {
    #                     "type": "string", 
    #                     "description": "String to be replaced"
    #                 },
    #                 "new_str": {
    #                     "type": "string",
    #                     "description": "String to replace with"
    #                 }
    #             },
    #             "required": [
    #                 "path",
    #                 "old_str", 
    #                 "new_str"
    #             ],
    #             "additionalProperties": False
    #         },
    #         "strict": True
    #     }
    # },
    # todo: create_file, replace_lines
]


@dataclass
class PendingInput:
    tool_call_id: str
    description: str
    callable: Callable


def bash_tool(command: str) -> str:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        response = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitcode": result.returncode
        }
        return json.dumps(response)
    except Exception as e:
        return str(e)


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
        model=model,
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


def handle_tool_call(tool_call):
    if tool_call.function.name == "read_file":
        try:
            arguments = json.loads(tool_call.function.arguments)
            if "path" not in arguments:
                return "path not specified", None
            if not os.path.exists(arguments["path"]):
                return "file does not exist"
            if os.path.isdir(arguments["path"]):
                return "cannot read a directory"
            from_line = arguments.get("from_line")
            to_line = arguments.get("to_line")
            if from_line is not None and not isinstance(from_line, int):
                return "from_line must be an int"
            if to_line is not None and not isinstance(to_line, int):
                return "from_line must be an int"
            if from_line is not None and to_line is not None and from_line > to_line:
                return "from_line cannot be after to_line"
            lines = open(arguments["path"]).read().split("\n")
            lines = lines[from_line : (None if to_line is None else to_line + 1)]
            return "\n".join(lines), None
        except Exception as e:
            return str(e), None
    elif tool_call.function.name == "view_path":
        try:
            arguments = json.loads(tool_call.function.arguments)
            if "path" not in arguments:
                return "path not specified", None
            if not os.path.exists(arguments["path"]):
                return "directory does not exist"
            if not os.path.isdir(arguments["path"]):
                return "path is a plain file"
            return subprocess.getoutput(f"find {arguments['path']} -maxdepth 2"), None
        except Exception as e:
            return str(e), None
    elif tool_call.function.name == "bash":
        try:
            arguments = json.loads(tool_call.function.arguments)
            command = arguments["command"]
            return None, PendingInput(
                tool_call_id=tool_call.id,
                description=f"```bash\n{command}\n```",
                callable=lambda: bash_tool(command)
            )
        except Exception as e:
            return str(e), None
    else:
        return f"Tool does not exist: {tool_call.function.name!r}", None


def trigger_deployment():
    try:
        response = requests.post("http://host.docker.internal:8000/deploy/verbal")
        if response.status_code == 200:
            st.sidebar.success(response.text)
        else:
            st.sidebar.error(response.text)
    except RequestException as e:
        st.sidebar.error(f"Failed to trigger deployment: {e}")


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
