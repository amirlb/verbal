import json
import os
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

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

def create_file(path: str, content: str) -> str:
    try:
        open(path, "w").write(content)
        return f"Created file {path}"
    except Exception as e:
        return str(e)

def edit_file(path: str, from_line: int, to_line: int, new_lines: Sequence[str]) -> str:
    try:
        # Read existing file
        with open(path, 'r') as f:
            lines = f.read().splitlines()

        # Replace content in specified range
        assert new_lines[0].strip() == lines[from_line-1].strip(), "first 2 lines don't match original content"
        assert new_lines[1].strip() == lines[from_line].strip(), "first 2 lines don't match original content"
        assert new_lines[-2].strip() == lines[to_line-2].strip(), "last 2 lines don't match original content"
        assert new_lines[-1].strip() == lines[to_line-1].strip(), "last 2 lines don't match original content"
        lines[from_line-1:to_line] = new_lines

        # Write back to file
        with open(path, 'w') as f:
            f.writelines(lines)

        return f"Modified lines {from_line}-{to_line} in {path}"
    except Exception as e:
        return str(e)