from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Literal

from pocketflow import *
from pydantic import BaseModel, Field

from function_node import FunctionNode
from memory import FunctionResultContent, Memory, Message


# *persona_append
class PersonaAppendValidator(BaseModel):
    """Appends text to a persona section in Working Context."""

    section: Literal["user", "agent"] = Field(
        description="Persona section where the text will be appended to ('user' or 'agent')."
    )
    text: str = Field(description="Text to be appended to the given section.")


class PersonaAppend(FunctionNode):
    name = "persona_append"
    validator = PersonaAppendValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: PersonaAppendValidator,
    ) -> Message:
        match arguments_validated.section:
            case "user":
                memory.working_context.user_persona += arguments_validated.text
            case "agent":
                memory.working_context.agent_persona += arguments_validated.text

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result=f"Successfully updated {'Agent' if arguments_validated.section == 'agent' else 'user'} Persona",
            ),
        )


# *persona_replace
class PersonaReplaceValidator(BaseModel):
    """Replaces text in a persona section in Working Context."""

    section: Literal["user", "agent"] = Field(
        description="Persona section in which the text will be replaced ('user' or 'agent')."
    )
    old_text: str = Field(description="Old text in the given section.")
    new_text: str = Field(description="New text in the given section.")


class PersonaReplace(FunctionNode):
    name = "persona_replace"
    validator = PersonaReplaceValidator

    def exec_function(
        self,
        memory: Memory,
        conn: Connection,
        arguments_validated: PersonaReplaceValidator,
    ) -> Message:
        match arguments_validated.section:
            case "user":
                memory.working_context.user_persona = (
                    memory.working_context.user_persona.replace(
                        arguments_validated.old_text, arguments_validated.new_text
                    )
                )
            case "agent":
                memory.working_context.agent_persona = (
                    memory.working_context.agent_persona.replace(
                        arguments_validated.old_text, arguments_validated.new_text
                    )
                )

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result=f"Successfully updated {'Agent' if arguments_validated.section == 'agent' else 'user'} Persona",
            ),
        )


# *push_task
class PushTaskValidator(BaseModel):
    """Pushes a task to your Working Context's task queue."""

    task: str = Field(description="Task to be pushed.")


class PushTask(FunctionNode):
    name = "push_task"
    validator = PushTaskValidator

    def exec_function(
        self, memory: Memory, conn: Connection, arguments_validated: PushTaskValidator
    ) -> Message:
        memory.working_context.push_task(arguments_validated.task)

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result=f"Successfully pushed task '{arguments_validated.task}' to task queue.",
            ),
        )


# *pop_task
class PopTaskValidator(BaseModel):
    """Pops task from your Working Context's task queue."""

    pass


class PopTask(FunctionNode):
    name = "pop_task"
    validator = PopTaskValidator

    def exec_function(
        self, memory: Memory, conn: Connection, arguments_validated: PushTaskValidator
    ) -> Message:
        popped_task = memory.working_context.pop_task()

        return Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=True,
                result=f"Successfully popped task '{popped_task}' from task queue.",
            ),
        )


FUNCTION_NODES = [PersonaAppend(), PersonaReplace(), PushTask(), PopTask()]
