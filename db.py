from os import path
from sqlite3 import Error
from typing import Any, List, Optional, Tuple, Union

import chromadb
import orjson
import psycopg
from psycopg.types.json import set_json_dumps, set_json_loads

from config import POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER


# *Helper functions
def write(query: str, values: Optional[Tuple[Any, ...]] = None) -> None:
    with psycopg.connect(
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@postgres:5432"
    ) as conn:
        with conn.cursor() as cur:
            if values:
                cur.execute(query, values)
            else:
                cur.execute(query)
            conn.commit()


def read(
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

# *Init DB


def orjson_dumps_str(*args) -> str:
    return orjson.dumps(*args).decode("utf-8")


set_json_dumps(orjson_dumps_str)
set_json_loads(orjson.loads)

## *Agents
write(
    """
    CREATE TABLE IF NOT EXISTS agents (
        id UUID PRIMARY KEY NOT NULL,
        optional_function_sets TEXT[] NOT NULL, 
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        recursive_summary TEXT DEFAULT "No content in recursive summary yet",
        recursive_summary_update_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
)

## *Working Context

write(
    """
    CREATE TABLE IF NOT EXISTS working_context (
        id UUID PRIMARY KEY NOT NULL,
        agent_id UUID NOT NULL,
        agent_persona TEXT NOT NULL,
        user_persona TEXT NOT NULL,
        tasks TEXT[] NOT NULL, 
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
    );
    """,
)

## *Recall Storage

write(
    """
    CREATE TABLE IF NOT EXISTS recall_storage (
        id UUID PRIMARY KEY NOT NULL,
        agent_id UUID NOT NULL,
        message_type TEXT NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        content JSONB NOT NULL, 
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
    );
    """,
)

## *FIFO Queue

write(
    """
    CREATE TABLE IF NOT EXISTS fifo_queue (
        id UUID PRIMARY KEY NOT NULL,
        agent_id UUID NOT NULL,
        message_type TEXT NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        content JSONB NOT NULL, 
        FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
    );
    """,
)

## *DB helper functions

write(
    """
CREATE OR REPLACE FUNCTION array_pop_in_place(
    tbl regclass,          -- table name
    keycol text,           -- primary key column name
    keyval anyelement,     -- primary key value
    arrcol text            -- array column name
)
RETURNS anyelement
LANGUAGE plpgsql AS $$
DECLARE
    last_elem anyelement;
    new_arr   anyarray;
    sql       text;
BEGIN
    -- Get the last element + shortened array
    sql := format(
        'SELECT %1$I[array_length(%1$I,1)], %1$I[1:array_length(%1$I,1)-1]
         FROM %2$s WHERE %3$I = $1',
        arrcol, tbl, keycol
    );
    EXECUTE sql INTO last_elem, new_arr USING keyval;

    -- Update the row with the shortened array
    sql := format(
        'UPDATE %1$s SET %2$I = $1 WHERE %3$I = $2',
        tbl, arrcol, keycol
    );
    EXECUTE sql USING new_arr, keyval;

    RETURN last_elem;
END;
$$;
    """
)

write(
    """
CREATE OR REPLACE FUNCTION array_popleft_in_place(
    tbl regclass,          -- table name
    keycol text,           -- primary key column
    keyval anyelement,     -- primary key value
    arrcol text            -- array column
)
RETURNS anyelement
LANGUAGE plpgsql AS $$
DECLARE
    first_elem anyelement;
    new_arr    anyarray;
    sql        text;
BEGIN
    -- Get first element and remainder
    sql := format(
        'SELECT %1$I[1], %1$I[2:array_length(%1$I,1)]
         FROM %2$s WHERE %3$I = $1',
        arrcol, tbl, keycol
    );
    EXECUTE sql INTO first_elem, new_arr USING keyval;

    -- Update with remainder
    sql := format(
        'UPDATE %1$s SET %2$I = $1 WHERE %3$I = $2',
        tbl, arrcol, keycol
    );
    EXECUTE sql USING new_arr, keyval;

    RETURN first_elem;
END;
$$;
    """
)
