import asyncio
import os
from typing import ClassVar, Literal
import time

from anthropic.types.beta import BetaToolBash20241022Param

from .base import BaseAnthropicTool, CLIResult, ToolError, ToolResult


class _BashSession:
    """A session of a bash shell."""

    _started: bool
    _process: asyncio.subprocess.Process

    command: str = "/bin/bash"
    _output_delay: float = 0.2  # seconds
    _timeout: float = 120.0  # seconds
    _sentinel: str = "<<exit>>"

    def __init__(self):
        self._started = False
        self._timed_out = False

    async def start(self):
        if self._started:
            return

        self._process = await asyncio.create_subprocess_shell(
            self.command,
            preexec_fn=os.setsid,
            shell=True,
            bufsize=0,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._started = True

    def stop(self):
        """Terminate the bash shell."""
        if not self._started:
            raise ToolError("Session has not started.")
        if self._process.returncode is not None:
            return
        self._process.terminate()

    async def run(self, command: str):
        """Execute a command in the bash shell."""
        if not self._started:
            raise ToolError(
                "Session has been stopped due to resource constraints and must be restarted."
            )
        if self._process.returncode is not None:
            return ToolResult(
                system="tool must be restarted",
                error=f"bash has exited with returncode {self._process.returncode}",
            )
        if self._timed_out:
            raise ToolError(
                f"timed out: bash has not returned in {self._timeout} seconds and must be restarted",
            )

        # we know these are not None because we created the process with PIPEs
        assert self._process.stdin
        assert self._process.stdout
        assert self._process.stderr

        # send command to the process
        self._process.stdin.write(command.encode() + f"; echo '{self._sentinel}'\n".encode())
        await self._process.stdin.drain()

        # read output from the process, until the sentinel is found
        try:
            async with asyncio.timeout(self._timeout):
                while True:
                    await asyncio.sleep(self._output_delay)
                    # if we read directly from stdout/stderr, it will wait forever for
                    # EOF. use the StreamReader buffer directly instead.
                    output = self._process.stdout._buffer.decode()  # pyright: ignore[reportAttributeAccessIssue]
                    if self._sentinel in output:
                        # strip the sentinel and break
                        output = output[: output.index(self._sentinel)]
                        break
        except asyncio.TimeoutError:
            self._timed_out = True
            raise ToolError(
                f"timed out: bash has not returned in {self._timeout} seconds and must be restarted",
            ) from None

        if output.endswith("\n"):
            output = output[:-1]

        error = self._process.stderr._buffer.decode()  # pyright: ignore[reportAttributeAccessIssue]
        if error.endswith("\n"):
            error = error[:-1]

        # clear the buffers so that the next output can be read correctly
        self._process.stdout._buffer.clear()  # pyright: ignore[reportAttributeAccessIssue]
        self._process.stderr._buffer.clear()  # pyright: ignore[reportAttributeAccessIssue]

        return CLIResult(output=output, error=error)


class BashSessionsManager:
    """Manages BashSessions."""

    def __init__(self, db, max_sessions: int = 10):
        self.db = db
        self.max_sessions = max_sessions
        self.sessions: dict[str, _BashSession] = {}
        self.session_timestamps: dict[str, float] = {}

    async def get_session(self, session_id: str) -> _BashSession:
        if session_id not in self.sessions and self._did_session_ever_use_bash(session_id):
            # A non-started session means it was killed due to resource constraints
            return _BashSession()

        if session_id not in self.sessions: 
            await self._create_session(session_id)

        return self.sessions[session_id]

    def stop_session(self, session_id: str):
        self.sessions[session_id].stop()
        del self.sessions[session_id]
        del self.session_timestamps[session_id]

    async def restart_session(self, session_id: str):
        if session_id in self.sessions:
            self.stop_session(session_id)
        await self._create_session(session_id)

    def _did_session_ever_use_bash(self, session_id: str) -> bool:
        cursor = self.db._db.cursor()
        cursor.execute("""
            SELECT 1 FROM message
            WHERE session_id = ? AND json_extract(content, '$.type') = 'tool_use' AND json_extract(content, '$.name') = 'bash'
            LIMIT 2
        """, (session_id,))
        return len(cursor.fetchall()) > 1

    async def _create_session(self, session_id: str) -> _BashSession:
        assert session_id not in self.sessions
        if len(self.sessions) >= self.max_sessions:
            self._pop_oldest_session()
        self.sessions[session_id] = _BashSession()
        self.session_timestamps[session_id] = time.monotonic()
        await self.sessions[session_id].start()

    def _pop_oldest_session(self):
        least_recently_used = min(self.session_timestamps.keys(), key=self.session_timestamps.get)
        self.stop_session(least_recently_used)


class BashTool(BaseAnthropicTool):
    """
    A tool that allows the agent to run bash commands.
    The tool parameters are defined by Anthropic and are not editable.
    """

    _manager: BashSessionsManager
    _session_id: str

    name: ClassVar[Literal["bash"]] = "bash"
    api_type: ClassVar[Literal["bash_20250124"]] = "bash_20250124"

    def __init__(self, manager: BashSessionsManager, session_id: str):
        super().__init__()
        self._manager = manager
        self._session_id = session_id

    async def __call__(self, command: str | None = None, restart: bool = False, **kwargs):
        if restart:
            await self._manager.restart_session(self._session_id)
            return ToolResult(system="tool has been restarted.")

        if command is None:
            raise ToolError("no command provided.")

        session = await self._manager.get_session(self._session_id)
        return await session.run(command)

    def to_params(self) -> BetaToolBash20241022Param:
        return {
            "type": self.api_type,
            "name": self.name,
        }
