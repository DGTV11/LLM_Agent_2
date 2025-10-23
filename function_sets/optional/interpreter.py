from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal, Optional

from llm_sandbox import SandboxBackend, SandboxSession
from pocketflow import *
from pydantic import BaseModel, Field

from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *execute_python
class ExecutePythonValidator(BaseModel):
    """Executes a Python 3.12 program in a sandbox (maximum execution time: 30s). Use this when you need to run computations requiring accuracy or mathematical calculations. Stdout and stderr returned."""

    program: str = Field(description="Python program to be run in the sandbox.")

    model_config = {"title": "execute_python"}


class ExecutePython(FunctionNode):
    name = "execute_python"
    validator = ExecutePythonValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: ExecutePythonValidator,
    ) -> Message:
        with SandboxSession(
            backend=SandboxBackend.DOCKER,
            lang="python",
            image="python:3.12-slim",
            reuse_container=False,
            execution_timeout=30,
        ) as session:
            result = session.run(arguments_validated.program)

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=bool(result.exit_code),
                result="\n\n".join(
                    [
                        f"stdout: {result.stdout}",
                        f"stderr: {result.stderr}",
                    ]
                ),
            ),
        )


FUNCTION_NODES = [ExecutePython()]
