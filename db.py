from os import path
from sqlite3 import Error
from typing import Any, List, Optional, Tuple, Union

import chromadb
import psycopg

from config import POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER


# *Helper functions
def db_write_query(
    query: str, values: Optional[Tuple[Any, ...]] = None
) -> Union[int, float, str, bytes, None]:  # values can be tuple
    with psycopg.connect(
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@postgres:5432"
    ) as conn:
        with conn.cursor() as cur:
            if values:
                cur.execute(query, values)
            else:
                cur.execute(query)
            conn.commit()
            return cur.lastrowid


def db_read_query(
    query: str, values: Optional[Tuple[Any, ...]] = None
) -> List[Tuple[Any, ...]]:  # values can be tuple
    with psycopg.connect(
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@postgres:5432"
    ) as conn:
        with conn.cursor() as cur:
            if values:
                cur.execute(query, values)
            else:
                cur.execute(query)
            return cur.fetchall()


create_chromadb_client = lambda: chromadb.HttpClient(
    # host="localhost",
    host="chroma",
    port=8000,
    settings=chromadb.config.Settings(anonymized_telemetry=False),
)


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
        user_persona TEXT NOT NULL,
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
