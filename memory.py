from collections import deque
from dataclasses import dataclass
from datetime import datetime
from queue import Queue
from typing import Any, Deque, Dict, List, Literal, Tuple, Union

import yaml

from prompts import SYSTEM_PROMPT

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

    def to_intermediate_repr(self) -> Dict[str, str]:
        match self.message_type:
            case "user":
                assert type(self.content) is TextContent
                yaml_str = yaml.dump(
                    {
                        "message_type": self.message_type,
                        "timestamp": self.timestamp.strftime("%a %d %b %Y, %I:%M%p"),
                        "content": {"message": self.content.message},
                    }
                ).strip()
            case "system":
                assert type(self.content) is TextContent
                yaml_str = yaml.dump(
                    {
                        "message_type": self.message_type,
                        "timestamp": self.timestamp.strftime("%a %d %b %Y, %I:%M%p"),
                        "content": {"message": self.content.message},
                    }
                ).strip()
            case "assistant":
                assert type(self.content) is AssistantMessageContent
                yaml_str = yaml.dump(
                    {
                        "message_type": self.message_type,
                        "timestamp": self.timestamp.strftime("%a %d %b %Y, %I:%M%p"),
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
                ).strip()
            case "function_res":
                assert type(self.content) is FunctionResultContent
                yaml_str = yaml.dump(
                    {
                        "message_type": self.message_type,
                        "timestamp": self.timestamp.strftime("%a %d %b %Y, %I:%M%p"),
                        "content": {
                            "success": self.content.success,
                            "result": self.content.result,
                        },
                    }
                ).strip()
            case _:
                raise ValueError("Invalid message_type")

        return {
            "role": "assistant" if self.message_type == "assistant" else "user",
            "content": yaml_str,
        }


# *Memory obj
@dataclass
class Memory:
    working_context: WorkingContext
    archival_storage: ArchivalStorage
    recall_storage: RecallStorage
    function_sets: FunctionSets
    fifo_queue: Deque[Message]

    def __repr__(self) -> str:
        return f"""
# Memory information

## Working Context

{self.working_context}

## Archival Storage

{self.working_context}

# Function Schemas

{self.function_sets}
""".strip()

    def get_system_prompt(self) -> str:
        return "\n\n".join([SYSTEM_PROMPT, repr(self)])

    def get_llm_ctx(self) -> List[Dict[str, str]]:
        processed_messages = [{"role": "system", "content": self.get_system_prompt()}]

        last_userside_messages = []

        for msg in self.fifo_queue:
            msg_intermediate = msg.to_intermediate_repr()
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
