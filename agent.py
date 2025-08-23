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
from config import CTX_WINDOW, FLUSH_TGT_TOK_FRAC, FLUSH_TOK_FRAC, WARNING_TOK_FRAC
from function_sets import FunctionSets
from llm import call_llm, llm_tokenise
from memory import (
    ArchivalStorage,
    AssistantMessageContent,
    FIFOQueue,
    Memory,
    Message,
    RecallStorage,
    TextContent,
    WorkingContext,
)
from persona_gen import generate_persona


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

        conn.send(json.dumps({"info": "Calling agent"}))

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
    def prep(self, shared: Dict[str, Any]) -> Tuple[Memory, Connection]:
        memory = shared["memory"]
        assert isinstance(memory, Memory)

        do_heartbeat = shared["do_heartbeat"]
        assert isinstance(do_heartbeat, bool)

        conn = shared["conn"]
        assert isinstance(conn, Connection)

        return memory, do_heartbeat, conn

    def exec(self, inputs: Tuple[Memory, bool, Connection]) -> bool:
        memory, do_heartbeat, conn = inputs

        if memory.in_ctx_no_tokens > FLUSH_TOK_FRAC * CTX_WINDOW:
            system_message = Message(
                message_type="system",
                timestamp=datetime.now(),
                content=TextContent(
                    message=f"FIFO Queue above {FLUSH_TOK_FRAC:.0%} of context window. Queue has been flushed to free up context space."
                ),
            )
            memory.push_message(system_message)

            conn.send(json.dumps({"message": system_message.to_intermediate_repr()}))

            memory.flush_fifo_queue(FLUSH_TGT_TOK_FRAC)

        elif memory.in_ctx_no_tokens > WARNING_TOK_FRAC * CTX_WINDOW:
            system_message = Message(
                message_type="system",
                timestamp=datetime.now(),
                content=TextContent(
                    message=f"FIFO Queue above {WARNING_TOK_FRAC:.0%} of context window. Please store relevant information from your conversation history into your Archival Storage or Working Context."
                ),
            )
            memory.push_message(system_message)

            conn.send(json.dumps({"message": system_message.to_intermediate_repr()}))

            do_heartbeat = True

        return do_heartbeat

    def post(
        self,
        shared: Dict[str, Any],
        prep_res: Tuple[Memory, bool, Connection],
        exec_res: bool,
    ) -> str:
        return "heartbeat" if exec_res else None


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
        VALUES (?, ?);
        """,
        (
            agent_id,
            json.dumps(optional_function_sets),
        ),
    )

    db.sqlite_db_write_query(
        """
        INSERT INTO working_context (id, agent_id, agent_persona, user_persona, tasks)
        VALUES (?, ?, ?, ?, ?);
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


def call_agent(agent_id: str, conn: Connection) -> None:
    try:
        conn.send(json.dumps({"info": "Loading agent memory..."}))
        memory = get_memory_object(agent_id)

        conn.send(json.dumps({"info": "Loading agent flow..."}))
        agent_flow = get_agent_flow(memory)

        shared = {"memory": memory, "conn": conn}

        conn.send(json.dumps({"info": "Starting agent loop..."}))

        agent_flow.run(shared)
    finally:
        try:
            conn.send(None)
        except Exception:
            pass
        conn.close()


def agent_step(agent_id: str) -> Generator[Dict[str, Any], None, None]:
    parent_conn, child_conn = Pipe()

    p = Process(
        target=call_agent,
        args=(
            agent_id,
            child_conn,
        ),
    )

    p.start()
    child_conn.close()

    try:
        while True:
            try:
                msg = parent_conn.recv()  # may raise EOFError if child dies early
            except EOFError:
                break
            if msg is None:
                break
            yield json.loads(msg)
    finally:
        parent_conn.close()
        p.join(timeout=5)
        if p.is_alive():
            p.terminate()
            p.join()


def main():
    # Ask if user wants to load an existing agent
    use_existing = input("Load existing agent? (y/n): ").strip().lower() == "y"

    if use_existing:
        agent_id = input("Enter agent ID: ").strip()
        print(f"Loading agent {agent_id}")
    else:
        agent_id = str(uuid4())
        agent_persona = input(
            "Enter agent persona (default: AI-generated persona): "
        ).strip()
        if not agent_persona:
            agent_persona = generate_persona("Provide companionship to the user")
            print(f'Generated persona: "{agent_persona}"')
        user_persona = (
            input("Enter user persona (optional, press Enter to skip): ").strip()
            or None
        )
        optional_functions = input(
            "Enter optional function sets (comma separated, optional): "
        ).strip()
        optional_function_sets = (
            [f.strip() for f in optional_functions.split(",") if f.strip()]
            if optional_functions
            else []
        )

        create_new_agent(
            optional_function_sets=optional_function_sets,
            agent_persona=agent_persona,
            user_persona=user_persona,
        )
        print(f"Created new agent {agent_id}")

    # Ask first message
    user_message = input("Enter your first user message: ").strip()

    # push user message to memory
    memory = get_memory_object(agent_id)
    memory.push_message(
        Message(
            message_type="user",
            timestamp=datetime.now(),
            content=TextContent(message=user_message),
        )
    )

    # run agent_step generator
    print("\nAssistant response:")
    for resp in agent_step(agent_id):
        print(json.dumps(resp, indent=2))
        break  # only first response for test


if __name__ == "__main__":
    main()
