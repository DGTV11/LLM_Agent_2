import json
from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal

from pocketflow import *
from pydantic import BaseModel, Field

from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *send_message
class SendMessageValidator(BaseModel):
    """Sends a message to the user. You usually shouldn't request heartbeats when calling this function."""

    message: str = Field(description="Message to be sent.")


class SendMessage(FunctionNode):
    name = "send_message"
    validator = SendMessageValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: SendMessageValidator,
    ) -> Message:

        conn.send(json.dumps({"message_to_user": arguments_validated.message}))

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result=f"Successfully sent message",
            ),
        )


FUNCTION_NODES = [SendMessage()]
