from typing import Literal

from pydantic import BaseModel, Field, RootModel


class ATPM_Message(BaseModel):
    message_type: Literal["message"]
    payload: dict


class ATPM_Debug(BaseModel):
    message_type: Literal["debug"]
    payload: str


class ATPM_Error(BaseModel):
    message_type: Literal["error"]
    payload: str


class ATPM_ToUser(BaseModel):
    message_type: Literal["to_user"]
    payload: str


class ATPM_Halt(BaseModel):
    message_type: Literal["halt"]


class AgentToParentMessage(RootModel):
    root: (
        ATPM_Message
        | ATPM_Debug
        | ATPM_Error
        | ATPM_ToUser
        | ATPM_Halt
    ) = Field(discriminator="message_type")
