from datetime import datetime
import json
import os
import sqlite3
from typing import Any, Literal, Self, TypedDict



class Message(TypedDict):
    """A message in the conversation."""

    role: Literal["user", "assistant"]
    content: dict[str, Any]
    timestamp: int

    @classmethod
    def create(cls, role: Literal["user", "assistant"], content: dict[str, Any]) -> Self:
        return cls(role=role, content=content, timestamp=datetime.now().timestamp())


class ConversationDetails(TypedDict):
    message_count: int
    created_at: int
    last_message_at: int


class DAL:
    _DATABASE_FILE_NAME_ENV_VAR = "DATABASE_FILE_NAME"
    _DEFAULT_DATABASE_FILE_NAME = "/verbal/db.sqlite"

    def __init__(self, db: sqlite3.Connection | None = None):
        self._db = db or self._connect()

        self._db.execute("""
            CREATE TABLE IF NOT EXISTS message (
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp INTEGER
            );
        """)
        self._db.execute("""
            CREATE INDEX IF NOT EXISTS message_session_id_timestmap_idx ON message (session_id, timestamp);
        """)
        self._db.commit()

    @classmethod
    def _connect(cls) -> sqlite3.Connection:
        db_file_name = os.getenv(cls._DATABASE_FILE_NAME_ENV_VAR, cls._DEFAULT_DATABASE_FILE_NAME)
        return sqlite3.connect(db_file_name)

    def list_conversations(self) -> dict[str, ConversationDetails]:
        query = """
            SELECT
                session_id,
                count(*) as message_count,
                min(timestamp) as created_at,
                max(timestamp) as last_message_at
            FROM message
            GROUP BY session_id
        """
        cursor = self._db.cursor()
        cursor.execute(query)
        return {
            session_id: {
                "message_count": message_count,
                "created_at": created_at,
                "last_message_at": last_message_at,
            }
            for session_id, message_count, created_at, last_message_at in cursor.fetchall()
        }

    def get_conversation(self, session_id: str) -> list[Message]:
        query_template = """
            SELECT role, content, timestamp
            FROM message
            WHERE session_id = ?
            ORDER BY timestamp
        """
        cursor = self._db.cursor()
        cursor.execute(query_template, (session_id,))
        return [
            Message(role=role, content=json.loads(content), timestamp=timestamp)
            for role, content, timestamp in cursor.fetchall()
        ]

    def add_message(self, session_id: str, message: Message) -> None:
        query_template = """
            INSERT INTO message (session_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
        """
        cursor = self._db.cursor()
        cursor.execute(query_template, (session_id, message["role"], json.dumps(message["content"]), message["timestamp"]))
        self._db.commit()
