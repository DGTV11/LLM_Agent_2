import json
from datetime import datetime
from multiprocessing import Pipe, Process
from multiprocessing.connection import Connection
from typing import Annotated, Any, Dict, Generator, List, Optional, Tuple, TypedDict
from uuid import uuid4

import yaml
from pocketflow import *
from pydantic import BaseModel, conint

import db
from function_sets import FunctionSets
from llm import call_llm, llm_tokenise
from memory import (
    ArchivalStorage,
    AssistantMessageContent,
    Memory,
    Message,
    RecallStorage,
    TextContent,
    WorkingContext,
)


# *CallAgent node
class FunctionCallDict(TypedDict):
    name: str
    arguments: Dict
    do_heartbeat: bool


class CallAgentResult(BaseModel):
    emotions: List[Tuple[str, Annotated[int, conint(ge=1, le=10)]]]
    thoughts: List[str]
    function_call: FunctionCallDict


class CallAgent(Node):
    def prep(self, shared: Dict[str, Any]) -> Tuple[Memory, Connection]:
        memory = shared["memory"]
        assert isinstance(memory, Memory)

        conn = shared["conn"]
        assert isinstance(conn, Connection)

        return memory, conn

    def exec(self, inputs: Tuple[Memory, Connection]) -> CallAgentResult:
        memory, conn = inputs

        resp = call_llm(memory.main_ctx)

        yaml_str = resp.split("```yaml")[1].split("```")[0].strip()
        result = yaml.safe_load(yaml_str)
        result_validated = CallAgentResult.model_validate(result)

        return result_validated

    def post(
        self,
        shared: Dict[str, Any],
        prep_res: Tuple[Memory, Connection],
        exec_res: CallAgentResult,
    ) -> str:
        memory, conn = prep_res

        agent_message_dict = {
            "message_type": "assistant",
            "timestamp": datetime.now().isoformat(),
            "content": exec_res.model_dump(),
        }
        agent_message_obj = Message.from_intermediate_repr(agent_message_dict)
        memory.push_message(agent_message_obj)

        conn.send(json.dumps({"message": agent_message_dict}))

        function_call = exec_res.function_call
        shared["arguments"] = function_call["arguments"]
        shared["do_heartbeat"] = function_call["do_heartbeat"]

        return function_call["name"]


# *ExitOrContinue node
class ExitOrContinue(Node):
    def exec(_) -> None:
        print("No heartbeat requested, exiting agent loop")


# *Helper functions
def get_memory_object(agent_id: str):
    return Memory(
        working_context=WorkingContext(agent_id=agent_id),
        archival_storage=ArchivalStorage(agent_id=agent_id),
        recall_storage=RecallStorage(agent_id=agent_id),
        function_sets=FunctionSets(agent_id=agent_id),
        fifo_queue=FIFOQueue(agent_id=agent_id),
        agent_id=agent_id,
    )


def get_agent_flow(memory: Memory):
    call_agent_node = CallAgent(max_retries=10)
    exit_or_continue_node = ExitOrContinue()

    function_node_dict = memory.function_sets.get_function_nodes()
    for function_name, function_node in function_node_dict.items():
        call_agent_node - function_name >> function_node
        function_node >> exit_or_continue_node

    return Flow(start=call_agent_node)


# *Agent runner functions
def create_new_agent(
    optional_function_sets: List[str], agent_persona: str, user_persona: Optional[str]
):
    agent_id = str(uuid4())

    db.sqlite_db_write_query(
        """
        INSERT INTO agents (id, optional_function_sets)
        (?, ?);
        """,
        (
            agent_id,
            json.dumps(optional_function_sets),
        ),
    )

    db.sqlite_db_write_query(
        """
        INSERT INTO working_context (id, agent_id, agent_persona, user_persona, tasks)
        (?, ?, ?, ?, ?);
        """,
        (
            str(uuid4()),
            agent_id,
            agent_persona,
            user_persona
            or "This is what I know about the user. I should update this persona as our conversation progresses",
            json.dumps([]),
        ),
    )


def call_agent(memory: Memory, agent_flow: Flow, conn: Connection) -> None:
    shared = {"memory": memory, "conn": conn}

    flow.run(shared)

    conn.send(None)


def agent_step(agent_id: str) -> Generator[Dict[str, Any], None, None]:
    parent_conn, child_conn = Pipe()

    memory = get_memory_object(agent_id)
    agent_flow = get_agent_flow(memory)

    p = Process(
        target=agent.call_agent,
        args=(
            memory,
            agent_flow,
            child_conn,
        ),
    )

    p.start()

    while True:
        msg = parent_conn.recv()
        if msg is None:
            break
        yield json.loads(msg)

    p.join()
