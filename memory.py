import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from os import path
from typing import Any, Deque, Dict, List, Literal, Optional, Tuple, Union
from uuid import uuid4

import chromadb
import yaml
from pocketflow import Node
from pydantic import BaseModel
from semantic_text_splitter import TextSplitter

import db
from config import (
    CHUNK_MAX_TOKENS,
    CTX_WINDOW,
    FLUSH_MIN_FIFO_QUEUE_LEN,
    FLUSH_TGT_TOK_FRAC,
    PERSONA_MAX_WORDS,
)
from function_sets import FunctionSets
from llm import call_llm, extract_yaml, llm_tokenise
from prompts import RECURSIVE_SUMMARY_PROMPT, SYSTEM_PROMPT


# *Messages
@dataclass
class TextContent:
    message: str


@dataclass
class FunctionCall:
    name: str
    arguments: Dict[str, Any]
    do_heartbeat: bool


@dataclass
class AssistantMessageContent:
    emotions: List[Tuple[str, float]]
    thoughts: List[str]
    function_call: FunctionCall


@dataclass
class FunctionResultContent:
    success: bool
    result: Any


@dataclass
class Message:
    message_type: Literal["user", "system", "assistant", "function_res"]
    timestamp: datetime
    content: Union[TextContent, AssistantMessageContent, FunctionResultContent]

    def to_intermediate_repr(self) -> Dict[str, Any]:
        match self.message_type:
            case "user":
                assert type(self.content) is TextContent
                return {
                    "message_type": self.message_type,
                    "timestamp": self.timestamp.isoformat(),
                    "content": {"message": self.content.message},
                }
            case "system":
                assert type(self.content) is TextContent
                return {
                    "message_type": self.message_type,
                    "timestamp": self.timestamp.isoformat(),
                    "content": {"message": self.content.message},
                }
            case "assistant":
                assert type(self.content) is AssistantMessageContent
                return {
                    "message_type": self.message_type,
                    "timestamp": self.timestamp.isoformat(),
                    "content": {
                        "emotions": self.content.emotions,
                        "thoughts": self.content.thoughts,
                        "function_call": {
                            "name": self.content.function_call.name,
                            "arguments": self.content.function_call.arguments,
                            "do_heartbeat": self.content.function_call.do_heartbeat,
                        },
                    },
                }
            case "function_res":
                assert type(self.content) is FunctionResultContent
                return {
                    "message_type": self.message_type,
                    "timestamp": self.timestamp.isoformat(),
                    "content": {
                        "success": self.content.success,
                        "result": self.content.result,
                    },
                }
            case _:
                raise ValueError("Invalid message_type")

    def to_std_message_format(self) -> Dict[str, str]:
        return {
            "role": "assistant" if self.message_type == "assistant" else "user",
            "content": yaml.dump(self.to_intermediate_repr()).strip(),
        }

    @staticmethod
    def from_intermediate_repr(intermediate_repr: Dict[str, Any]) -> "Message":
        match intermediate_repr["message_type"]:
            case "user":
                return Message(
                    message_type="user",
                    timestamp=datetime.fromisoformat(intermediate_repr["timestamp"]),
                    content=TextContent(
                        message=intermediate_repr["content"]["message"]
                    ),
                )
            case "system":
                return Message(
                    message_type="system",
                    timestamp=datetime.fromisoformat(intermediate_repr["timestamp"]),
                    content=TextContent(
                        message=intermediate_repr["content"]["message"]
                    ),
                )
            case "assistant":
                return Message(
                    message_type="assistant",
                    timestamp=datetime.fromisoformat(intermediate_repr["timestamp"]),
                    content=AssistantMessageContent(
                        emotions=intermediate_repr["content"]["emotions"],
                        thoughts=intermediate_repr["content"]["thoughts"],
                        function_call=FunctionCall(
                            name=intermediate_repr["content"]["function_call"]["name"],
                            arguments=intermediate_repr["content"]["function_call"][
                                "arguments"
                            ],
                            do_heartbeat=intermediate_repr["content"]["function_call"][
                                "do_heartbeat"
                            ],
                        ),
                    ),
                )
            case "function_res":
                return Message(
                    message_type="function_res",
                    timestamp=datetime.fromisoformat(intermediate_repr["timestamp"]),
                    content=FunctionResultContent(
                        success=intermediate_repr["content"]["success"],
                        result=intermediate_repr["content"]["result"],
                    ),
                )
            case _:
                raise ValueError("Invalid message_type")


# * Memory modules


@dataclass
class WorkingContext:
    agent_id: str

    @property
    def agent_persona(self) -> Union[str, Any]:
        return db.sqlite_db_read_query(
            "SELECT agent_persona FROM working_context WHERE agent_id = ?;",
            (self.agent_id,),
        )[0][0]

    @agent_persona.setter
    def agent_persona(self, value: str) -> None:
        new_persona_length = len(value.split())
        if new_persona_length > PERSONA_MAX_WORDS:
            raise ValueError(
                f"New persona too long (maximum length {PERSONA_MAX_WORDS}, requested length {new_persona_length})"
            )

        db.sqlite_db_write_query(
            "UPDATE working_context SET agent_persona = ? WHERE agent_id = ?;",
            (
                value,
                self.agent_id,
            ),
        )

    @property
    def user_persona(self) -> Union[str, Any]:
        return db.sqlite_db_read_query(
            "SELECT user_persona FROM working_context WHERE agent_id = ?;",
            (self.agent_id,),
        )[0][0]

    @user_persona.setter
    def user_persona(self, value: str) -> None:
        new_persona_length = len(value.split())
        if new_persona_length > PERSONA_MAX_WORDS:
            raise ValueError(
                f"New persona too long (maximum length {PERSONA_MAX_WORDS}, requested length {new_persona_length})"
            )

        db.sqlite_db_write_query(
            "UPDATE working_context SET user_persona = ? WHERE agent_id = ?;",
            (
                value,
                self.agent_id,
            ),
        )

    @property
    def tasks(self) -> Union[List[str], Any]:
        return json.loads(
            db.sqlite_db_read_query(
                "SELECT tasks FROM working_context WHERE agent_id = ?;",
                (self.agent_id,),
            )[0][0]
        )

    def push_task(self, task: str) -> None:
        db.sqlite_db_write_query(
            "UPDATE working_context SET tasks = ? WHERE agent_id = ?",
            (
                json.dumps(self.tasks + [task]),
                self.agent_id,
            ),
        )

    def pop_task(self) -> str:
        tasks = self.tasks

        if len(tasks) == 0:
            raise ValueError("Task queue empty!")

        task_queue = deque(tasks)
        popped_task = str(task_queue.popleft())
        db.sqlite_db_write_query(
            "UPDATE working_context SET tasks = ? WHERE agent_id = ?",
            (
                json.dumps(list(task_queue)),
                self.agent_id,
            ),
        )

        return popped_task

    def __repr__(self) -> str:
        return f"""
### Agent Persona

{self.agent_persona}

### User Persona

{self.user_persona}

### Task Queue

{self.tasks}
""".strip()


@dataclass
class ArchivalStorage:
    agent_id: str
    collection: Any = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.collection = chromadb.HttpClient(
            host="localhost",
            port=8000,
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        ).get_or_create_collection(name=self.agent_id)
        # self.collection = chromadb.PersistentClient(
        #     path=path.dirname(__file__),
        #     settings=chromadb.config.Settings(anonymized_telemetry=False),
        # ).get_or_create_collection(name=self.agent_id)

    def __len__(self) -> Union[int, Any]:
        return self.collection.count()

    @property
    def categories(self) -> List[str]:
        categories_set = set()

        batch_size = 50
        for i in range(0, len(self), batch_size):
            batch = self.collection.get(
                include=["metadatas"],
                limit=batch_size,
                offset=i,
            )
            categories_set |= set(map(lambda m: m["category"], batch["metadatas"]))

        return list(categories_set)

    def archival_insert(self, content: str, category: str) -> None:
        splitter = TextSplitter.from_tiktoken_model("gpt-3.5-turbo", CHUNK_MAX_TOKENS)
        chunks = splitter.chunks(content)

        self.collection.add(
            ids=[str(uuid4()) for _ in range(len(chunks))],
            documents=chunks,
            metadatas=[
                {"category": category, "timestamp": datetime.now().isoformat()},
            ]
            * len(chunks),
        )

    def archival_search(
        self, query: str, offset: int, count: int, category: Optional[str]
    ) -> List[Dict[str, Any]]:
        query_res = self.collection.query(
            query_texts=[query],
            include=["documents", "metadatas"],
            offset=offset,
            n_results=count,
            where=({"category": category} if category else None),
        )
        page_tuples = zip(*query_res.values())
        page_dicts = [
            {"document": document, "metadata": metadata}
            for document, metadata in page_tuples
        ]

        return page_dicts

    def __repr__(self) -> str:
        return f"""
Archival storage contains {len(self)} entries
Categories: {self.categories}
""".strip()


@dataclass
class RecallStorage:
    agent_id: str

    def __len__(self) -> int:
        return len(
            db.sqlite_db_read_query(
                "SELECT message_type, timestamp, content FROM recall_storage WHERE agent_id = ?",
                (self.agent_id,),
            )
        )

    def push_message(self, message: Message) -> None:
        message_intermediate = message.to_intermediate_repr()

        db.sqlite_db_write_query(
            """
            INSERT INTO recall_storage (id, agent_id, message_type, timestamp, content)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                str(uuid4()),
                self.agent_id,
                message_intermediate["message_type"],
                message_intermediate["timestamp"],
                json.dumps(message_intermediate["content"]),
            ),
        )

    def text_search(self, query_text: str) -> List[Message]:
        message_list = []
        for message_type, timestamp, content in db.sqlite_db_read_query(
            "SELECT message_type, timestamp, content FROM recall_storage WHERE agent_id = ? AND (message_type = 'user' OR message_type = 'assistant') AND content LIKE '%?%'",
            (self.agent_id, query_text),
        ):
            message_dict = {
                "message_type": message_type,
                "timestamp": timestamp,
                "content": json.loads(content),
            }

            message_list.append(Message.from_intermediate_repr(message_dict))

        return message_list

    def date_search(self, start_timestamp: str, end_timestamp: str) -> List[Message]:
        message_list = []
        for message_type, timestamp, content in db.sqlite_db_read_query(
            "SELECT message_type, timestamp, content FROM recall_storage WHERE agent_id = ? AND (message_type = 'user' OR message_type = 'assistant') AND timestamp BETWEEN '?' AND '?'",
            (self.agent_id, start_timestamp, end_timestamp),
        ):
            message_dict = {
                "message_type": message_type,
                "timestamp": timestamp,
                "content": json.loads(content),
            }

            message_list.append(Message.from_intermediate_repr(message_dict))

        return message_list


# * Queue


@dataclass
class FIFOQueue:
    agent_id: str

    @property
    def messages(self) -> List[Message]:
        message_list = []
        for message_type, timestamp, content in db.sqlite_db_read_query(
            "SELECT message_type, timestamp, content FROM fifo_queue WHERE agent_id = ?",
            (self.agent_id,),
        ):
            message_dict = {
                "message_type": message_type,
                "timestamp": timestamp,
                "content": json.loads(content),
            }

            message_list.append(Message.from_intermediate_repr(message_dict))

        return message_list

    def __len__(self) -> int:
        return len(
            db.sqlite_db_read_query(
                "SELECT message_type, timestamp, content FROM fifo_queue WHERE agent_id = ?",
                (self.agent_id,),
            )
        )

    def push_message(self, message: Message) -> None:
        message_intermediate = message.to_intermediate_repr()

        db.sqlite_db_write_query(
            """
            INSERT INTO fifo_queue (id, agent_id, message_type, timestamp, content)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                str(uuid4()),
                self.agent_id,
                message_intermediate["message_type"],
                message_intermediate["timestamp"],
                json.dumps(message_intermediate["content"]),
            ),
        )

    def peek_message(self) -> Message:
        db_res = db.sqlite_db_read_query(
            "SELECT id, agent_id, message_type, timestamp, content FROM fifo_queue WHERE agent_id = ? AND timestamp = (SELECT MIN(timestamp) FROM fifo_queue);",
            (self.agent_id,),
        )

        if len(db_res) == 0:
            raise ValueError("Message queue empty!")

        id, agent_id, message_type, timestamp, content = db_res[0]

        message_dict = {
            "message_type": message_type,
            "timestamp": timestamp,
            "content": json.loads(content),
        }

        return Message.from_intermediate_repr(message_dict)

    def pop_message(self) -> Message:
        last_message = self.peek_message()

        db.sqlite_db_write_query(
            "DELETE FROM fifo_queue WHERE agent_id = ? AND timestamp = (SELECT MIN(timestamp) FROM fifo_queue);",
            (self.agent_id,),
        )

        return last_message


class GenerateNewRecursiveSummaryResult(BaseModel):
    analysis: str
    summary: str


class GenerateNewRecursiveSummary(Node):
    def prep(self, shared: Dict[str, Any]) -> List[str]:
        evicted_message_strs = shared["evicted_message_strs"]
        assert isinstance(evicted_message_strs, list)

        return evicted_message_strs

    def exec(self, evicted_message_strs: List[str]) -> str:
        resp = call_llm(
            [
                {"role": "system", "content": RECURSIVE_SUMMARY_PROMPT},
                {"role": "user", "content": "\n\n".join(evicted_message_strs)},
            ]
        )

        result = extract_yaml(resp)
        result_validated = GenerateNewRecursiveSummaryResult.model_validate(result)

        return result_validated.summary

    def post(self, shared: Dict[str, Any], prep_res: List[str], exec_res: str) -> None:
        shared["summary"] = exec_res


generate_new_recursive_summary_node = GenerateNewRecursiveSummary(max_retries=10)


# *Memory obj
@dataclass
class Memory:
    working_context: WorkingContext
    archival_storage: ArchivalStorage
    recall_storage: RecallStorage
    function_sets: FunctionSets
    fifo_queue: FIFOQueue
    agent_id: str

    def __repr__(self) -> str:
        return f"""
# Memory information

## Working Context

{self.working_context}

## Archival Storage

{self.archival_storage}

## Recall Storage

{len(self.fifo_queue)} messages in FIFO Queue
{len(self.recall_storage)} messages in Recall Storage ({len(self.recall_storage) - len(self.fifo_queue)} previous messages evicted from FIFO Queue)

# Function Schemas

{self.function_sets}
""".strip()

    @property
    def system_prompt(self) -> str:
        return "\n\n".join([SYSTEM_PROMPT, repr(self)])

    @property
    def recursive_summary_and_summary_timestamp(self) -> Tuple[str, datetime]:
        rs, rsut_txt = db.sqlite_db_read_query(
            "SELECT recursive_summary, recursive_summary_update_time FROM agents WHERE id = ?;",
            (self.agent_id,),
        )[0]

        return rs, datetime.fromisoformat(rsut_txt)

    @property
    def main_ctx(self) -> List[Dict[str, str]]:
        processed_messages = [{"role": "system", "content": self.system_prompt}]

        last_userside_messages = []

        rs, rsut = self.recursive_summary_and_summary_timestamp

        for msg in (
            [
                Message(
                    message_type="system",
                    timestamp=rsut,
                    content=TextContent(
                        message=f"""
# Recursive summary (contains conversation history before beginning of context window, if any)

{rs}
""".strip()
                    ),
                )
            ]
            + self.fifo_queue.messages
        ):
            msg_intermediate = msg.to_std_message_format()
            if msg_intermediate["role"] == "user":
                last_userside_messages.append(msg_intermediate["content"])
            else:
                processed_messages.append(
                    {"role": "user", "content": "\n\n".join(last_userside_messages)}
                )
                processed_messages.append(
                    {"role": "assistant", "content": msg_intermediate["content"]}
                )
                last_userside_messages = []

        if len(last_userside_messages) > 0:
            processed_messages.append(
                {"role": "user", "content": "\n\n".join(last_userside_messages)}
            )

        return processed_messages

    @property
    def in_ctx_no_tokens(self) -> int:
        return len(llm_tokenise(self.main_ctx))

    def push_message(self, message: Message) -> None:
        self.fifo_queue.push_message(message)
        self.recall_storage.push_message(message)

    def flush_fifo_queue(self, tgt_token_frac: float) -> None:
        rs, rsut = self.recursive_summary_and_summary_timestamp

        evicted_message_strs = [
            yaml.dump(
                Message(
                    message_type="system",
                    timestamp=rsut,
                    content=TextContent(
                        message=f"""
# Recursive summary (contains conversation history before beginning of context window, if any)

{rs}
""".strip()
                    ),
                ).to_intermediate_repr()
            ).strip()
        ]

        while (
            self.in_ctx_no_tokens > FLUSH_TGT_TOK_FRAC * CTX_WINDOW
            or self.fifo_queue.peek_message().message_type != "user"
        ):
            if (
                len(self.fifo_queue) <= FLUSH_MIN_FIFO_QUEUE_LEN
                and self.fifo_queue.peek_message().message_type == "user"
            ):
                break

            evicted_message_strs.append(
                yaml.dump(self.fifo_queue.pop_message().to_intermediate_repr()).strip()
            )

        shared = {"evicted_message_strs": evicted_message_strs}

        generate_new_recursive_summary_node.run(shared)

        new_summary = shared["summary"]

        db.sqlite_db_write_query(
            "UPDATE agents SET recursive_summary = ?, recursive_summary_update_time = ? WHERE id = ?",
            (
                new_summary,
                datetime.now().isoformat(),
                self.agent_id,
            ),
        )
