import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque, Dict, List, Literal, Tuple, Union
from uuid import uuid4

import yaml

import db
from prompts import SYSTEM_PROMPT
from config import PERSONA_MAX_WORDS


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
                    message_type="system",
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
            raise ValueError(f"New persona too long (maximum length {PERSONA_MAX_WORDS}, requested length {new_persona_length})")
            
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
            raise ValueError(f"New persona too long (maximum length {PERSONA_MAX_WORDS}, requested length {new_persona_length})")
            
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
                json.dumps(self.tasks + [str]),
                self.agent_id,
            ),
        )

    def pop_task(self) -> str:
        tasks = self.tasks

        if len(tasks) == 0:
            raise ValueError("Task queue empty!")

        task_queue = deque(tasks)
        popped_task = task_queue.popleft()
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
## Agent Persona

{self.agent_persona}

## User Persona

{self.user_persona}

## Task Queue

{self.tasks}
""".strip()


@dataclass
class ArchivalStorage:  # *ChromaDB
    agent_id: str

    def __init__(self, agent_id: str) -> None:
        pass

    @property
    def categories(self):
        pass

    @property
    def no_items(self):
        pass

    def archival_insert(self, content: str, category: str) -> None:
        pass

    def archival_search(self, query: str, category: str | None):
        pass

    def __repr__(self):
        pass  # TODO: add category listing


class RecallStorage:  # *SQLite
    def __init__(self, agent_id: str) -> None:
        pass


# * Function sets (TBD)


class FunctionSets:
    def __init__(self, agent_id: str) -> None:
        pass


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
            (?, ?, ?, ?, ?);
            """,
            (
                str(uuid4()),
                self.agent_id,
                message_intermediate["message_type"],
                message_intermediate["timestamp"],
                json.dumps(message_intermediate["content"]),
            ),
        )

    def pop_message(self) -> Message:
        db_res = db.sqlite_db_read_query(
            "SELECT message_type, timestamp, content FROM fifo_queue WHERE agent_id = ? AND timestamp = (SELECT MIN(timestamp) FROM fifo_queue);",
            (self.agent_id,),
        )

        if len(db_res) == 0:
            raise ValueError("Message queue empty!")

        id, agent_id, message_type, timestamp, content = db_res[0]

        db.sqlite_db_write_query(
            "DELETE FROM fifo_queue WHERE agent_id = ? AND timestamp = (SELECT MIN(timestamp) FROM fifo_queue);",
            (self.agent_id,),
        )
        message_dict = {
            "message_type": message_type,
            "timestamp": timestamp,
            "content": json.loads(content),
        }

        return Message.from_intermediate_repr(message_dict)


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

{self.recall_storage}

# Function Schemas

{self.function_sets}
""".strip()

    def get_system_prompt(self) -> str:
        return "\n\n".join([SYSTEM_PROMPT, repr(self)])

    def get_recursive_summary_and_summary_timestamp(self) -> Tuple[str, datetime]:
        rs, rsut_txt = db.sqlite_db_read_query(
            "SELECT recursive_summary, recursive_summary_update_time FROM agents WHERE agent_id = ?;",
            (self.agent_id,),
        )[0]

        return rs, datetime.fromisoformat(rsut_txt)

    def get_llm_ctx(self) -> List[Dict[str, str]]:
        processed_messages = [{"role": "system", "content": self.get_system_prompt()}]

        last_userside_messages = []

        rs, rsut = self.get_recursive_summary_and_summary_timestamp()

        for msg in (
            [
                Message(
                    message_type="system",
                    timestamp=rsut,
                    content=TextContent(
                        message=f"""
# Recursive summary (contains conversation history beyond beginning of context window)

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

    def get_in_ctx_no_tokens(self) -> int:
        pass
