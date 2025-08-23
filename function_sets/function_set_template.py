from datetime import datetime
from typing import Any, Dict, List, Literal

from pocketflow import *
from pydantic import BaseModel, Field

from function_sets import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *example_func
class ExampleFuncValidator(BaseModel):
    """Example function description."""

    pass


class ExampleFunc(FunctionNode):
    name = "example_func"
    validator = ExampleFuncValidator

    def exec_function(
        self, memory: Memory, arguments_validated: ExampleFuncValidator
    ) -> Message:
        # *Do something here

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result=f"Successfully did something",
            ),
        )


FUNCTION_NODES = [ExampleFunc()]
