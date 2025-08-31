from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal, Optional

from llm_sandbox import SandboxSession
from pocketflow import *
from pydantic import BaseModel, Field

from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *execute_python
class ExecutePythonValidator(BaseModel):
    """Executes a Python program in a sandbox (maximum execution time before timeout: 30s). Use this when you need to run computations requiring accuracy or mathematical calculations. Stdout returned."""

    program: str = Field(description="Python program to be run in the sandbox.")


class ExecutePython(FunctionNode):
    name = "execute_python"
    validator = ExecutePython

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: ExecutePythonValidator,
    ) -> Message:
        with SandboxSession(
            backend="docker", lang="python", docker_url="tcp://docker-proxy:2375"
        ) as session:
            result = session.run(arguments_validated.program)

            return Message(
                message_type="function_res",
                timestamp=datetime.now(),
                content=FunctionResultContent(
                    success=True,
                    result=result.stdout,
                ),
            )


FUNCTION_NODES = [ExecutePython()]
