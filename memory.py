import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from queue import Queue
from typing import Any, Deque, Dict, List, Literal, Tuple, Union

import yaml

import db
from prompts import SYSTEM_PROMPT


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
    def from_intermediate_repr(intermediate_repr: Dict[str, Any]) -> Message:
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
    agent_persona: str
    user_persona: str
    tasks: Queue[str]  # *To add functions for pushing and popping this queue
    agent_id: str

    def __repr__(self) -> str:
        return f"""
## Agent Persona

{self.agent_persona}

## User Persona

{self.user_persona}

## Task Queue

{self.tasks}
""".strip()

    def save(self) -> None:
        pass

    @staticmethod
    def load(agent_id) -> WorkingContext:
        pass


class ArchivalStorage:  # *ChromaDB
    def __init__(self, agent_id: str) -> None:
        pass


class RecallStorage:  # *ChromaDB/SQLite
    # TODO: decide whether to have just `recall_search` (sqlite)
    # or `recall_search_exact` and `recall_search_similarity` (chromadb)
    def __init__(self, agent_id: str) -> None:
        pass


# * Function sets (TBD)


class FunctionSets:
    def __init__(self, agent_id: str) -> None:
        pass


@dataclass
class FIFOQueue:  # use SQLite to store
    agent_id: str

    @property
    def messages(self) -> List[Message]:
        message_list = []
        for message_type, timestamp, content in db.sqlite_db_read_query(
            """
        SELECT message_type, timestamp, content FROM fifo_queue WHERE agent_id = ?
        """,
            (self.agent_id,),
        ):
            message_dict = {
                "message_type": message_type,
                "timestamp": timestamp,
                "content": json.loads(content),
            }

            message_list.append(Message.from_intermediate_repr(message_dict))

        return message

    def push_message(self, message: Message) -> None:
        pass

    def pop_message(self) -> Message:
        pass


# *Memory obj
@dataclass
class Memory:
    working_context: WorkingContext
    archival_storage: ArchivalStorage
    recall_storage: RecallStorage
    function_sets: FunctionSets
    fifo_queue: FIFOQueue

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

    def get_llm_ctx(self) -> List[Dict[str, str]]:
        processed_messages = [{"role": "system", "content": self.get_system_prompt()}]

        last_userside_messages = []

        for msg in self.fifo_queue.messages:  # TODO: add recursive summary db query
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
