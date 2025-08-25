import json
import traceback
from datetime import datetime
from multiprocessing import Pipe, Process
from multiprocessing.connection import Connection
from typing import Annotated, Any, Dict, Generator, List, Optional, Tuple, TypedDict
from uuid import uuid4

import yaml
from pocketflow import Flow, Node
from pydantic import BaseModel, conint

import db
from communication import AgentToParentMessage
from config import CTX_WINDOW, FLUSH_TGT_TOK_FRAC, FLUSH_TOK_FRAC, WARNING_TOK_FRAC
from function_sets import FunctionSets
from llm import call_llm, llm_tokenise
from memory import (
    ArchivalStorage,
    AssistantMessageContent,
    FIFOQueue,
    FunctionResultContent,
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

        conn.send(
            AgentToParentMessage(
                message_type="debug", payload="Calling agent"
            ).model_dump_json()
        )

        return memory, conn

    def exec(self, inputs: Tuple[Memory, Connection]) -> CallAgentResult:
        memory, conn = inputs

        resp = call_llm(memory.main_ctx)

        conn.send(
            AgentToParentMessage(
                message_type="debug", payload=f"Got respose: {resp}"
            ).model_dump_json()
        )

        result = extract_yaml(resp)
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

        conn.send(
            AgentToParentMessage(
                message_type="message", payload=agent_message_dict
            ).model_dump_json()
        )

        function_call = exec_res.function_call
        shared["arguments"] = function_call["arguments"]
        shared["do_heartbeat"] = function_call["do_heartbeat"]

        return function_call["name"]


# *InvalidFunction node
class InvalidFunction(Node):
    def post(
        self,
        shared: Dict[str, Any],
        prep_res: None,
        exec_res: None,
    ) -> None:
        memory = shared["memory"]
        assert isinstance(memory, Memory)

        conn = shared["conn"]
        assert isinstance(conn, Connection)

        error_message = Message(
            message_type="function_res",
            timestamp=datetime.now(),
            content=FunctionResultContent(
                success=False, result="Function does not exist"
            ),
        )

        memory.push_message(error_message)
        conn.send(
            AgentToParentMessage(
                message_type="message", payload=error_message.to_intermediate_repr()
            ).model_dump_json()
        )

        shared["do_heartbeat"] = True


# *ExitOrContinue node
class ExitOrContinue(Node):
    def prep(self, shared: Dict[str, Any]) -> Tuple[Memory, bool, Connection]:
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

            conn.send(
                AgentToParentMessage(
                    message_type="message",
                    payload=system_message.to_intermediate_repr(),
                ).model_dump_json()
            )

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

            conn.send(
                AgentToParentMessage(
                    message_type="message",
                    payload=system_message.to_intermediate_repr(),
                ).model_dump_json()
            )

            do_heartbeat = True

        return do_heartbeat

    def post(
        self,
        shared: Dict[str, Any],
        prep_res: Tuple[Memory, bool, Connection],
        exec_res: bool,
    ) -> Optional[str]:
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


# def get_memory_object(agent_id: str):
#     working_context = WorkingContext(agent_id=agent_id)
#     print("working_context:", working_context)
#
#     archival_storage = ArchivalStorage(agent_id=agent_id)
#     print("archival_storage:", archival_storage)
#
#     recall_storage = RecallStorage(agent_id=agent_id)
#     print("recall_storage:", recall_storage)
#
#     function_sets = FunctionSets(agent_id=agent_id)
#     print("function_sets:", function_sets)
#
#     fifo_queue = FIFOQueue(agent_id=agent_id)
#     print("fifo_queue:", fifo_queue)
#
#     memory = Memory(
#         working_context=working_context,
#         archival_storage=archival_storage,
#         recall_storage=recall_storage,
#         function_sets=function_sets,
#         fifo_queue=fifo_queue,
#         agent_id=agent_id,
#     )
#
#     print("memory object created:", memory)
#     return memory


def get_agent_flow(memory: Memory):
    call_agent_node = CallAgent(max_retries=10)
    invalid_function_node = InvalidFunction()
    exit_or_continue_node = ExitOrContinue()

    function_node_dict = memory.function_sets.get_function_nodes()
    for function_name, function_node in function_node_dict.items():
        call_agent_node - function_name >> function_node
        function_node >> exit_or_continue_node
    call_agent_node >> invalid_function_node
    invalid_function_node >> exit_or_continue_node

    exit_or_continue_node - "heartbeat" >> call_agent_node

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

    return agent_id


def call_agent(agent_id: str, conn: Connection) -> None:
    try:
        conn.send(
            AgentToParentMessage(
                message_type="debug", payload="Loading agent memory..."
            ).model_dump_json()
        )
        memory = get_memory_object(agent_id)

        conn.send(
            AgentToParentMessage(
                message_type="debug", payload="Loading agent flow..."
            ).model_dump_json()
        )
        agent_flow = get_agent_flow(memory)

        shared = {"memory": memory, "conn": conn}

        conn.send(
            AgentToParentMessage(
                message_type="debug", payload="Starting agent loop..."
            ).model_dump_json()
        )

        agent_flow.run(shared)
    except Exception:
        conn.send(
            AgentToParentMessage(
                message_type="error", payload=traceback.format_exc()
            ).model_dump_json()
        )
    finally:
        try:
            conn.send(None)
        except Exception:
            pass
        conn.close()


def agent_step(agent_id: str) -> Generator[Dict[str, Any], None, None]:
    parent_conn, child_conn = Pipe()
    p = Process(target=call_agent, args=(agent_id, child_conn))
    p.start()

    # print("Stream start")

    try:
        while True:
            try:
                # print("Receiving message")
                msg = parent_conn.recv()
                # print(f"Received msg {msg} with type {type(msg)}")
            except EOFError:
                # print("Child closed the pipe")
                break

            if msg is None:
                print("End-of-stream marker")
                break

            yield json.loads(msg)
    finally:
        child_conn.close()
        parent_conn.close()
        p.join()
        # print("End of stream")


def main():
    # Ask if user wants to load an existing agent
    use_existing = input("Load existing agent? (y/n): ").strip().lower() == "y"

    if use_existing:
        agent_id = input("Enter agent ID: ").strip()
        print(f"Loading agent {agent_id}")

        memory = get_memory_object(agent_id)

        memory.push_message(
            Message(
                message_type="system",
                timestamp=datetime.now(),
                content=TextContent(
                    message="The user has re-entered the conversation. You should greet the user then carry on where you had left off."
                ),
            )
        )
    else:
        agent_persona = input(
            "Enter agent persona (default: AI-generated persona): "
        ).strip()
        if not agent_persona:
            agent_persona = generate_persona("Provide companionship to the user")
            # agent_persona = "I'm a warm and considerate person with a friendly demeanor. I'm known for my active listening skills, so I should take the time to fully understand the user. I'm outgoing, curious, and enthusiastic, always eager to learn and share knowledge. I respect personal boundaries and maintain confidentiality, never divulging sensitive information. I genuinely care about the user's well-being, prioritizing their safetyand happiness above all else. I love exploring new ideas and experiences through conversations with the user."
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

        agent_id = create_new_agent(
            optional_function_sets=optional_function_sets,
            agent_persona=agent_persona,
            user_persona=user_persona,
        )
        print(f"Created new agent {agent_id}")

        memory = get_memory_object(agent_id)
        memory.push_message(
            Message(
                message_type="system",
                timestamp=datetime.now(),
                content=TextContent(
                    message="A new user has entered the conversation. You should greet the user then get to know him."
                ),
            )
        )

    print("\nAssistant first response:")
    for resp in agent_step(agent_id):
        print(json.dumps(resp, indent=2))

    try:
        while True:
            user_message = input("Enter user message: ").strip()

            memory.push_message(
                Message(
                    message_type="user",
                    timestamp=datetime.now(),
                    content=TextContent(message=user_message),
                )
            )

            print("\nAssistant response:")
            for resp in agent_step(agent_id):
                print(json.dumps(resp, indent=2))
    except KeyboardInterrupt:
        memory.push_message(
            Message(
                message_type="system",
                timestamp=datetime.now(),
                content=TextContent(
                    message="The user has exited the conversation. You should do some background tasks(if necessary) before going into standby mode."
                ),
            )
        )

        print("\nAssistant response:")
        for resp in agent_step(agent_id):
            print(json.dumps(resp, indent=2))


if __name__ == "__main__":
    main()
