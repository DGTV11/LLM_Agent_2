from datetime import datetime
from math import ceil
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal, Optional

import orjson
from pocketflow import *
from pydantic import BaseModel, Field, NonNegativeInt

from config import PAGE_SIZE
from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *recall_search
class RecallSearchValidator(BaseModel):
    """Searches Recall Storage by text (exact match)."""

    query: str = Field(
        description="Search query. Exact match (case-insensitive) required for result to show up."
    )
    page: Optional[NonNegativeInt] = Field(
        default=0,
        description="Result list page number. Defaults to 0 and must be non-negative. If you haven't found the target information from Recall Storage but are certain it's there, increment page number or tweak query and try again.",
    )

    model_config = {"title": "recall_search"}


class RecallSearch(FunctionNode):
    name = "recall_search"
    validator = RecallSearchValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: RecallSearchValidator,
    ) -> Message:
        messages = memory.recall_storage.text_search(arguments_validated.query)

        result_str = f"Results for page {arguments_validated.page}/{ceil(len(messages)/PAGE_SIZE)}:"
        offset = min(arguments_validated.page * PAGE_SIZE, len(messages))

        for res_no, message in enumerate(
            messages[offset : offset + PAGE_SIZE], start=1
        ):
            message_dict = message.to_intermediate_repr()

            result_str += (
                "\n\n"
                + f"Result {res_no}: {orjson.dumps(message_dict).decode('utf-8')}"
            )

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(success=True, result=result_str),
        )


# *recall_search_by_date
class RecallSearchByDateValidator(BaseModel):
    """Searches Recall Storage by datetime range."""

    start_timestamp: datetime = Field(
        description="Starting timestamp (must conform to ISO 8601 format)"
    )
    end_timestamp: datetime = Field(
        description="Ending timestamp (must conform to ISO 8601 format)"
    )
    page: Optional[NonNegativeInt] = Field(
        default=0,
        description="Result list page number. Defaults to 0 and must be non-negative. If you haven't found the target information from Recall Storage but are certain it's there, increment page number or tweak date range and try again.",
    )

    model_config = {"title": "recall_search_by_date"}


class RecallSearchByDate(FunctionNode):
    name = "recall_search_by_date"
    validator = RecallSearchByDateValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: RecallSearchByDateValidator,
    ) -> Message:
        messages = memory.recall_storage.date_search(
            arguments_validated.start_timestamp, arguments_validated.end_timestamp
        )

        result_str = f"Results for page {arguments_validated.page}/{ceil(len(messages)/PAGE_SIZE)}:"
        offset = min(arguments_validated.page * PAGE_SIZE, len(messages))

        for res_no, message in enumerate(
            messages[offset : offset + PAGE_SIZE], start=1
        ):
            message_dict = message.to_intermediate_repr()

            result_str += (
                "\n\n"
                + f"Result {res_no}: {orjson.dumps(message_dict).decode('utf-8')}"
            )

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(success=True, result=result_str),
        )


FUNCTION_NODES = [RecallSearch(), RecallSearchByDate()]
