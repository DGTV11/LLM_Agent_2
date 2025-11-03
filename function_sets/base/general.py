from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal

from pocketflow import *
from pydantic import BaseModel, Field

from communication import AgentToParentMessage
from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *noop
class NoopValidator(BaseModel):
    """Does nothing. To be used when you do not need to do anything. MINIMISE unnecessary usage of this function."""

    model_config = {"title": "noop"}


class Noop(FunctionNode):
    name = "noop"
    validator = NoopValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: NoopValidator,
    ) -> Message:

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result=None,
            ),
        )


# *send_message
class SendMessageValidator(BaseModel):
    """Sends a message to the user. You usually shouldn't request heartbeats when calling this function (unless you want to double text or perform other operations before sending updates to the user). Can only be used during conversations with the user."""

    message: str = Field(description="Message to be sent.")

    model_config = {"title": "send_message"}


class SendMessage(FunctionNode):
    name = "send_message"
    validator = SendMessageValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: SendMessageValidator,
    ) -> Message:

        if memory.in_convo:
            msg_timestamp = datetime.now()

            conn.send(
                AgentToParentMessage(
                    message_type="to_user", payload=arguments_validated.message
                ).model_dump_json()
            )

            memory.chat_log.push_message(
                ChatLogMessage(
                    message_type="agent",
                    timestamp=msg_timestamp,
                    content=arguments_validated.message,
                )
            )

            return Message(
                message_type="function_res",
                timestamp=msg_timestamp,
                content=FunctionResultContent(
                    success=True,
                    result=f"Successfully sent message",
                ),
            )
        raise ValueError("Cannot be used outside conversation when user is absent")


FUNCTION_NODES = [Noop(), SendMessage()]
