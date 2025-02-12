import json
import os
import subprocess
from typing import Tuple, Optional

from tools import PendingInput, create_file, edit_file, bash_tool

def handle_tool_call(tool_call) -> Tuple[Optional[str], Optional[PendingInput]]:
    if tool_call.function.name == "read_file":
        try:
            arguments = json.loads(tool_call.function.arguments)
            assert "path" in arguments, "path not specified"
            assert os.path.exists(arguments["path"]), "file does not exist"
            assert not os.path.isdir(arguments["path"]), "cannot read a directory"
            from_line = arguments.get("from_line")
            to_line = arguments.get("to_line")
            lines = open(arguments["path"]).readlines()
            if from_line is not None:
                assert isinstance(from_line, int), "from_line must be an integer"
                assert 1 <= from_line <= len(lines), "from_line out of range"
            if to_line is not None:
                assert isinstance(to_line, int), "to_line must be an integer"
                assert 1 <= to_line <= len(lines), "to_line out of range"
            if from_line is not None and to_line is not None:
                assert from_line <= to_line, "from_line cannot be after to_line"
            lines = lines[(None if from_line is None else from_line - 1) : to_line]
            return "".join(lines), None
        except Exception as e:
            return str(e), None

    elif tool_call.function.name == "view_path":
        try:
            arguments = json.loads(tool_call.function.arguments)
            assert "path" in arguments, "path not specified"
            assert os.path.exists(arguments["path"]), "directory does not exist"
            assert os.path.isdir(arguments["path"]), "path is a plain file"
            return subprocess.getoutput(f"find {arguments['path']} -maxdepth 2"), None
        except Exception as e:
            return str(e), None

    elif tool_call.function.name == "create_file":
        try:
            arguments = json.loads(tool_call.function.arguments)
            for k in ["path", "content"]:
                assert k in arguments, f"{k} not specified"
            assert not os.path.exists(arguments["path"]), "file already exists"
            return None, PendingInput(
                tool_call_id=tool_call.id,
                description=f"```\n{arguments['content']}\n```",
                callable=lambda: create_file(arguments['path'], arguments['content'])
            )
        except Exception as e:
            return str(e), None

    elif tool_call.function.name == "edit_file":
        try:
            arguments = json.loads(tool_call.function.arguments)
            for k in ["path", "from_line", "to_line", "content"]:
                assert k in arguments, f"{k} not specified"
            path = arguments["path"]
            assert os.path.exists(path), "file does not exist"
            with open(path) as f:
                existing_lines = f.readlines()
            from_line = arguments["from_line"]
            to_line = arguments["to_line"]
            assert isinstance(from_line, int), "from_line must be an integer"
            assert isinstance(to_line, int), "to_line must be an integer"
            assert 1 <= from_line <= len(existing_lines), "from_line out of range"
            assert 1 <= to_line <= len(existing_lines), "to_line out of range"
            assert from_line <= to_line - 4, "the line range must span at least 4 lines"

            new_lines = arguments["content"].splitlines(keepends=True)
            assert len(new_lines) >= 4, "content must be at least 4 lines long"

            assert new_lines[0].strip() == existing_lines[from_line-1].strip(), "first 2 lines don't match original content"
            assert new_lines[1].strip() == existing_lines[from_line].strip(), "first 2 lines don't match original content"
            assert new_lines[-2].strip() == existing_lines[to_line-2].strip(), "last 2 lines don't match original content"
            assert new_lines[-1].strip() == existing_lines[to_line-1].strip(), "last 2 lines don't match original content"

            return None, PendingInput(
                tool_call_id=tool_call.id,
                description=f"```\n{arguments['content']}\n```",
                callable=lambda: edit_file(path, from_line, to_line, new_lines)
            )
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