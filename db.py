import sqlite3
from os import path
from sqlite3 import Error
from typing import Any, List, Optional, Tuple, Union

import chromadb

SQLITE_DB_CONNECTION = sqlite3.connect(path.join(path.dirname(__file__), "db.sqlite"))

CHROMA_DB_CLIENT = chromadb.PersistentClient(
    path=path.dirname(__file__),
    settings=chromadb.config.Settings(anonymized_telemetry=False),
)


def sqlite_db_write_query(
    query: str, values: Optional[Tuple[Any, ...]] = None
) -> Union[int, float, str, bytes, None]:  # values can be tuple
    cursor = SQLITE_DB_CONNECTION.cursor()
    if values:
        cursor.execute(query, values)
    else:
        cursor.execute(query)
    SQLITE_DB_CONNECTION.commit()

    return cursor.lastrowid


def sqlite_db_read_query(
    query: str, values: Optional[Tuple[Any, ...]] = None
) -> List[Tuple[Any, ...]]:  # values can be tuple
    cursor = SQLITE_DB_CONNECTION.cursor()
    if values:
        cursor.execute(query, values)
    else:
        cursor.execute(query)

    return cursor.fetchall()


# *Init SQLite DB

## *Agents
sqlite_db_write_query(
    """
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY NOT NULL,
        -- json list
        optional_function_sets TEXT NOT NULL, 
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        recursive_summary TEXT DEFAULT "No content in recursive summary yet",
        recursive_summary_update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        user_persona TEXT NOT NULL DEFAULT "This is what I know about the user. I should update this persona as our conversation progresses",
        -- json list
        tasks TEXT NOT NULL, 
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
        -- json obj
        content TEXT NOT NULL, 
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
        -- json obj
        content TEXT NOT NULL, 
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
    );
    """,
)
