import streamlit as st
import os
import subprocess
from openai import OpenAI
from typing import Dict, Any


client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
model = os.getenv('OPENAI_MODEL', "gpt-4o-mini")

SYSTEM_PROMPT = """You are a helpful assistant that can manage remote
computers for users on a phone, that can't easily type code or edit files.
You are in a mobile app, and you try to understand and anticipate what
the user wants and act accordingly.

You have access to a shell via the bash function."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a command in a shell on the same machine as the server runs, which is a container based on the python3.12-slim image (derived from Debian)",
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
]

def execute_command(command: str) -> Dict[str, Any]:
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitcode": result.returncode
        }
    except Exception as e:
        return {"error": str(e), "exitcode": -1}

def format_command_result(command: str, result: Dict[str, Any]) -> str:
    return f"""Executing: {command}

Output:
```
{result['stdout']}
```

Errors:
```
{result['stderr']}
```"""

def handle_command_execution():
    if not st.session_state.pending_command:
        return

    with st.container():
        st.warning(f"Do you want to execute this command?\n```bash\n{st.session_state.pending_command}```")
        col1, col2 = st.columns(2)
        if col1.button("Execute", key="execute_btn"):
            result = execute_command(st.session_state.pending_command)
            add_assistant_message(format_command_result(st.session_state.pending_command, result))
            clear_pending_command()
        if col2.button("Cancel", key="cancel_btn"):
            add_assistant_message("Command execution cancelled.")
            clear_pending_command()

def get_openai_response():
    completion = client.chat.completions.create(
        model=model,
        messages=st.session_state.messages,
        tools=TOOLS,
    )
    return completion.choices[0].message

def add_assistant_message(content: str):
    st.session_state.messages.append({"role": "assistant", "content": content})

def add_user_message(content: str):
    st.session_state.messages.append({"role": "user", "content": content})

def clear_pending_command():
    st.session_state.pending_command = None
    st.rerun()

def init_session_state():
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        st.session_state.pending_command = None

def display_chat_history():
    for message in st.session_state.messages:
        if message["role"] != "system":
            with st.chat_message(message["role"]):
                st.write(message["content"])

def main():
    st.set_page_config(page_title="Verbal", layout="wide", initial_sidebar_state="collapsed")
    init_session_state()
    st.title("Verbal")

    if prompt := st.chat_input("How can I help?"):
        add_user_message(prompt)
        response = get_openai_response()

        if response.function_call:
            command = eval(response.function_call.arguments).get('command')
            st.session_state.pending_command = command
            add_assistant_message(f"I would like to execute this command:\n```bash\n{command}```\nPlease confirm if you want to proceed.")
            st.rerun()
        else:
            add_assistant_message(response.content)

    display_chat_history()
    handle_command_execution()

if __name__ == "__main__":
    main()
