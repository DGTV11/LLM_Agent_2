from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal, Optional

from pocketflow import *
from pydantic import BaseModel, Field, NonNegativeInt

from config import PAGE_SIZE
from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *archival_insert
class ArchivalInsertValidator(BaseModel):
    """Inserts text into Archival Storage."""

    text: str = Field(
        description="Text to be inserted into archival storage. To be formatted such that it can be easily queried through vector search."
    )
    category: str = Field(
        description="Category of information presented in the given text. Keep the number of categories low (so as not to make the categories too fine-grained) but not too low (to avoid overgeneralising the stored info)."
    )


class ArchivalInsert(FunctionNode):
    name = "archival_insert"
    validator = ArchivalInsertValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: ArchivalInsertValidator,
    ) -> Message:
        memory.archival_storage.archival_insert(
            arguments_validated.text, arguments_validated.category
        )

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result=f"Successfully inserted text '{arguments_validated.text}' into Archival Storage with category '{arguments_validated.category}'",
            ),
        )


# *archival_search
class ArchivalSearchValidator(BaseModel):
    """Searches Archival Storage by text (vector search)."""

    query: str = Field(
        description="Search query. To be formatted for more effective vector search."
    )
    page: Optional[NonNegativeInt] = Field(
        default=0,
        description="Result list page number. Defaults to 0 and must be non-negative. If you haven't found the target information from Archival Storage but are certain it's there, increment page number and try again.",
    )
    category: Optional[str] = Field(
        description="Category of information to limit search to."
    )


class ArchivalSearch(FunctionNode):
    name = "archival_search"
    validator = ArchivalSearchValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: ArchivalSearchValidator,
    ) -> Message:
        page_dicts = memory.archival_storage.archival_search(
            arguments_validated.query,
            arguments_validated.page * PAGE_SIZE,
            PAGE_SIZE,
            arguments_validated.category,
        )

        result_str = f"Results for page {arguments_validated.page}:"

        for res_no, page_dict in enumerate(page_dicts, start=1):
            document = page_dict["document"]
            category = page_dict["metadata"]["category"]
            timestamp = page_dict["metadata"]["timestamp"]

            result_str += (
                "\n\n"
                + f"Result {res_no} (Category '{category}', Timestamp {timestamp}): {document}"
            )

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(success=True, result=result_str),
        )


FUNCTION_NODES = [ArchivalInsert(), ArchivalSearch()]
