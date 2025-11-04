from datetime import datetime
from math import ceil
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal, Optional

import orjson
from pocketflow import *
from pydantic import BaseModel, Field, NonNegativeInt

from config import CHAT_LOG_PAGE_SIZE
from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *chat_log_search
class ChatLogSearchValidator(BaseModel):
    """Queries recent messages (oldest to newest within page, higher pages yield older messages) from Chat Log. Optionally filters by text (exact match)."""

    query: Optional[str] = Field(
        description="Optional search query. Exact match (case-insensitive) required for result to show up."
    )
    page: Optional[NonNegativeInt] = Field(
        default=0,
        description="Result list page number.",
    )

    model_config = {"title": "chat_log_search"}


class ChatLogSearch(FunctionNode):
    name = "chat_log_search"
    validator = ChatLogSearchValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: ChatLogSearchValidator,
    ) -> Message:
        messages = memory.chat_log.recent_search(arguments_validated.query)

        result_str = f"Results for page {arguments_validated.page}/{ceil(len(messages)/CHAT_LOG_PAGE_SIZE)} (Newest message timestamp: {messages[0].timestamp.isoformat()}, Oldest message timestamp: {messages[-1].timestamp.isoformat()}):"
        offset = min(arguments_validated.page * CHAT_LOG_PAGE_SIZE, len(messages))

        for res_no, message in enumerate(
            messages[offset : offset + CHAT_LOG_PAGE_SIZE][::-1], start=1
        ):
            result_str += (
                "\n\n"
                + f"Result {res_no} ({message.message_type} message, timestamp {message.timestamp.isoformat()}): {message.content}"
            )

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(success=True, result=result_str),
        )


# *chat_log_search_by_date
class ChatLogSearchByDateValidator(BaseModel):
    """Searches Chat Log by datetime range (oldest to newest within page, higher pages yield older messages) ."""

    start_timestamp: datetime = Field(
        description="Starting timestamp (must conform to ISO 8601 format)"
    )
    end_timestamp: datetime = Field(
        description="Ending timestamp (must conform to ISO 8601 format)"
    )
    page: Optional[NonNegativeInt] = Field(
        default=0,
        description="Result list page number.",
    )

    model_config = {"title": "chat_log_search_by_date"}


class ChatLogSearchByDate(FunctionNode):
    name = "chat_log_search_by_date"
    validator = ChatLogSearchByDateValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: ChatLogSearchByDateValidator,
    ) -> Message:
        messages = memory.chat_log.date_search(
            arguments_validated.start_timestamp, arguments_validated.end_timestamp
        )

        result_str = f"Results for page {arguments_validated.page}/{ceil(len(messages)/CHAT_LOG_PAGE_SIZE)}:"
        offset = min(arguments_validated.page * CHAT_LOG_PAGE_SIZE, len(messages))

        for res_no, message in enumerate(
            messages[offset : offset + CHAT_LOG_PAGE_SIZE][::-1], start=1
        ):
            result_str += (
                "\n\n"
                + f"Result {res_no} ({message.message_type} message, timestamp {message.timestamp.isoformat()}): {message.content}"
            )

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(success=True, result=result_str),
        )


FUNCTION_NODES = [ChatLogSearch(), ChatLogSearchByDate()]
