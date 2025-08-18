from dataclasses import dataclass
from queue import Queue

from prompts import SYSTEM_PROMPT


@dataclass
class WorkingContext:
    """Persona info storage"""

    agent_persona: str
    user_persona: str
    tasks: Queue[str]  # *To add functions for pushing and popping this queue

    def __repr__(self):
        return f"""
# Working Context

## Agent Persona

{self.agent_persona}

## User Persona

{self.user_persona}

## Task Queue

{self.tasks}

""".strip()


class ArchivalStorage:
    def __init__(self):
        pass


class RecallStorage:
    def __init__(self):
        pass


class Memory:
    def __init__(
        self, working_context, archival_storage, recall_storage, function_sets
    ):
        pass

    def get_system_prompt(self):
        return "\n\n".join([SYSTEM_PROMPT, repr(working_context)])
