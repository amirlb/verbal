import os
import platform
import datetime
from typing import List, Dict, Any

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
* When editing a file, if the line numbers don't work out, re-read the surrounding lines of the file and locate the text you want to change before. Once you found it try the edit again.
* The current date is {datetime.datetime.today().strftime('%A, %B %-d, %Y')}."""

TOOLS: List[Dict[str, Any]] = [
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
                "required": ["command"],
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
                        "type": "integer",
                        "description": "Start from this line (1-based, optional)"
                    },
                    "to_line": {
                        "type": "integer",
                        "description": "Show content up to this line and including it (1-based, optional)"
                    }
                },
                "required": ["path"],
                "additionalProperties": False
            }
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
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file with specified content",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The full path of the file to create, starting with /"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["path", "content"],
                "additionalProperties": False
            },
            "strict": True
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit specific lines in a file. The first and last 2 lines must match the existing file content",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The full path of the file to edit, starting with /"
                    },
                    "from_line": {
                        "type": "integer",
                        "description": "Replace lines starting from this line (1-based)"
                    },
                    "to_line": {
                        "type": "integer",
                        "description": "The last line of the replaced block (1-based)"
                    },
                    "content": {
                        "type": "string",
                        "description": "New content to replace the specified line range. First and last 2 lines must match original file"
                    }
                },
                "required": ["path", "from_line", "to_line", "content"],
                "additionalProperties": False
            },
            "strict": True
        }
    }
]

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', "gpt-4o-mini") 