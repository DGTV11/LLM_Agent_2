import sqlite3
from os import path
from sqlite3 import Error
from typing import Any, List, Optional, Tuple

import chromadb

SQLITE_DB_CONNECTION = sqlite3.connect(path.join(path.dirname(__file__), "db.sqlite"))
client = chromadb.PersistentClient(
    path=path.join(path.dirname(__file__), "vector_db.chroma"),
    settings=chromadb.config.Settings(anonymized_telemetry=False),
)


def sqlite_db_write_query(
    query: str, values: Optional[str] = None
) -> Any:  # values can be tuple
    cursor = SQLITE_DB_CONNECTION.cursor()
    if values:
        cursor.execute(query, values)
    else:
        cursor.execute(query)
    SQLITE_DB_CONNECTION.commit()

    return cursor.lastrowid


def sqlite_db_read_query(
    query: str, values: Optional[str] = None
) -> List[Tuple[Any, ...]]:  # values can be tuple
    cursor = SQLITE_DB_CONNECTION.cursor()
    if values:
        cursor.execute(query, values)
    else:
        cursor.execute(query)

    return cursor.fetchall()


# *Init SQLite DB

sqlite_db_write_query(
    """
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY NOT NULL,
        optional_function_sets TEXT NOT NULL, -- json list
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        recursive_summary TEXT DEFAULT "No content in recursive summary yet"
    );
    """,
)

## *Working Context

sqlite_db_write_query(
    """
    CREATE TABLE IF NOT EXISTS working_context (
        id TEXT PRIMARY KEY NOT NULL,
        agent_id TEXT NOT NULL,
        agent_persona TEXT NOT NULL,
        user_persona TEXT NOT NULL,
        tasks TEXT NOT NULL, -- json list
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
    );
    """,
)

## *Recall Storage

sqlite_db_write_query(
    """
    CREATE TABLE IF NOT EXISTS recall_storage (
        id TEXT PRIMARY KEY NOT NULL,
        agent_id TEXT NOT NULL,
        message_type TEXT NOT NULL,
        timestamp DATETIME NOT NULL,
        content TEXT NOT NULL, -- json obj
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
    );
    """,
)

## *FIFO Queue

sqlite_db_write_query(
    """
    CREATE TABLE IF NOT EXISTS fifo_queue (
        id TEXT PRIMARY KEY NOT NULL,
        agent_id TEXT NOT NULL,
        message_type TEXT NOT NULL,
        timestamp DATETIME NOT NULL,
        content TEXT NOT NULL, -- json obj
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
    );
    """,
)
