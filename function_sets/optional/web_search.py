from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal, Optional

from pocketflow import *
from pydantic import BaseModel, Field

from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *call_research_agent
class CallResearchAgentValidator(BaseModel):
    """Requests a researcher AI to search the web to answer a given query."""

    query: str = Field(
        description="Question to ask the researcher to research about. Should have the necessary background information and be well-framed and specific in the required internet information."
    )


class CallResearchAgent(FunctionNode):
    name = "call_research_agent"
    validator = CallResearchAgentValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: CallResearchAgentValidator,
    ) -> Message:

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result="",
            ),
        )  # TODO


FUNCTION_NODES = [CallResearchAgent()]
