import os
import signal
import traceback
from datetime import datetime
from multiprocessing import Pipe, Process
from multiprocessing.connection import Connection
from time import sleep
from typing import (
    Annotated,
    Any,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    TypedDict,
    Union,
)
from uuid import uuid4

import orjson
import yaml
from pocketflow import Flow, Node
from pydantic import BaseModel, ValidationError, conint

import db
from communication import (
    AgentToParentMessage,
    ATPM_Debug,
    ATPM_Error,
    ATPM_Halt,
    ATPM_Message,
    ATPM_ToUser,
)
from config import (
    CTX_WINDOW,
    FLUSH_TGT_TOK_FRAC,
    FLUSH_TOK_FRAC,
    OVERTHINK_WARNING_HEARTBEAT_COUNT,
    WARNING_TOK_FRAC,
)
from function_sets import FunctionSets
from llm import call_llm, extract_yaml, llm_tokenise
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
            AgentToParentMessage.model_validate(
                {"message_type": "debug", "payload": "Calling agent"}
            ).model_dump_json()
        )

        return memory, conn

    def exec(self, inputs: Tuple[Memory, Connection]) -> CallAgentResult:
        memory, conn = inputs

        resp = call_llm(memory.main_ctx)

        conn.send(
            AgentToParentMessage.model_validate(
                {"message_type": "debug", "payload": f"Got respose: {resp}"}
            ).model_dump_json()
        )

        result = extract_yaml(resp)

        try:
            result_validated = CallAgentResult.model_validate(result)
        except ValidationError as e:
            try:
                result_validated = CallAgentResult.model_validate(
                    result["content"]
                )  # *Fallback: if the LLM decides to conform to the input schema instead of output schema
            except Exception:
                raise e

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
            AgentToParentMessage.model_validate(
                {"message_type": "message", "payload": agent_message_dict}
            ).model_dump_json()
        )

        function_call = exec_res.function_call
        shared["arguments"] = function_call["arguments"]
        shared["do_heartbeat"] = function_call["do_heartbeat"]

        return (
            function_call["name"]
            if function_call["name"] in memory.function_sets.get_function_nodes()
            else "invalid_function"
        )


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
            AgentToParentMessage.model_validate(
                {
                    "message_type": "message",
                    "payload": error_message.to_intermediate_repr(),
                }
            ).model_dump_json()
        )

        shared["do_heartbeat"] = True


# *ExitOrContinue node
class ExitOrContinue(Node):
    def prep(
        self, shared: Dict[str, Any]
    ) -> Tuple[Memory, bool, Connection, int, bool]:
        memory = shared["memory"]
        assert isinstance(memory, Memory)

        do_heartbeat = shared["do_heartbeat"]
        assert isinstance(do_heartbeat, bool)

        conn = shared["conn"]
        assert isinstance(conn, Connection)

        loops_since_overthink_warning = shared["loops_since_overthink_warning"] + 1
        assert isinstance(loops_since_overthink_warning, int)
        shared["loops_since_overthink_warning"] = loops_since_overthink_warning

        ctx_window_warning_given_flag = shared["ctx_window_warning_given_flag"]
        assert isinstance(ctx_window_warning_given_flag, bool)

        return (
            memory,
            do_heartbeat,
            conn,
            loops_since_overthink_warning,
            ctx_window_warning_given_flag,
        )

    def exec(
        self, inputs: Tuple[Memory, bool, Connection, int, bool]
    ) -> Tuple[bool, bool, int]:
        (
            memory,
            do_heartbeat,
            conn,
            loops_since_overthink_warning,
            ctx_window_warning_given_flag,
        ) = inputs

        memory_in_ctx_no_tokens = memory.in_ctx_no_tokens

        conn.send(
            AgentToParentMessage.model_validate(
                {
                    "message_type": "debug",
                    "payload": f"Context window contains {memory_in_ctx_no_tokens}/{CTX_WINDOW} ({memory_in_ctx_no_tokens/CTX_WINDOW:.0%}) tokens",
                }
            ).model_dump_json()
        )

        if (
            memory_in_ctx_no_tokens > FLUSH_TOK_FRAC * CTX_WINDOW
        ):  # *FIFO Queue overflow check
            system_message = Message(
                message_type="system",
                timestamp=datetime.now(),
                content=TextContent(
                    message=f"FIFO Queue above {FLUSH_TOK_FRAC:.0%} of context window. Queue has been flushed to free up context space."
                ),
            )
            memory.push_message(system_message)

            conn.send(
                AgentToParentMessage.model_validate(
                    {
                        "message_type": "message",
                        "payload": system_message.to_intermediate_repr(),
                    },
                ).model_dump_json()
            )

            ctx_window_warning_given_flag = False

            memory.flush_fifo_queue(FLUSH_TGT_TOK_FRAC)

        elif (
            not ctx_window_warning_given_flag
            and memory_in_ctx_no_tokens > WARNING_TOK_FRAC * CTX_WINDOW
        ):  # *FIFO Queue warning check
            system_message = Message(
                message_type="system",
                timestamp=datetime.now(),
                content=TextContent(
                    message=f"FIFO Queue above {WARNING_TOK_FRAC:.0%} of context window. Please store relevant information from your conversation history into your Archival Storage or Working Context before continuing where you left off (you may use your Task Queue to keep track)."
                ),
            )
            memory.push_message(system_message)

            conn.send(
                AgentToParentMessage.model_validate(
                    {
                        "message_type": "message",
                        "payload": system_message.to_intermediate_repr(),
                    }
                ).model_dump_json()
            )

            ctx_window_warning_given_flag = True
            loops_since_overthink_warning = 0

            do_heartbeat = True

        elif conn.poll(0.25):
            match (conn.recv(), do_heartbeat):
                case ("halt", True):
                    system_message = Message(
                        message_type="system",
                        timestamp=datetime.now(),
                        content=TextContent(
                            message=f"The user has overridden your heartbeat request. Your AI has been halted."
                        ),
                    )
                    memory.push_message(system_message)

                    conn.send(
                        AgentToParentMessage.model_validate(
                            {
                                "message_type": "message",
                                "payload": system_message.to_intermediate_repr(),
                            }
                        ).model_dump_json()
                    )

                    do_heartbeat = False
                case ("halt_soon", True):
                    system_message = Message(
                        message_type="system",
                        timestamp=datetime.now(),
                        content=TextContent(
                            message=f"The user has requested that you finish up whatever you are doing soon. You should double-check whether you have gathered sufficient information to accurately answer the user's query or finish your background tasks. If you have, please send a final message to the user or finish up your tasks and then set your 'do_heartbeat' field to false. If you have not, please carry on until you have, but hurry up as the user has the option to forcefully halt your AI."
                        ),
                    )
                    memory.push_message(system_message)

                    conn.send(
                        AgentToParentMessage.model_validate(
                            {
                                "message_type": "message",
                                "payload": system_message.to_intermediate_repr(),
                            }
                        ).model_dump_json()
                    )

                    loops_since_overthink_warning = 0
                case _:
                    raise ValueError("Invalid command (what were you even thinking?)")

        elif (
            loops_since_overthink_warning >= OVERTHINK_WARNING_HEARTBEAT_COUNT
            and do_heartbeat
        ):  # *Overthink check
            system_message = Message(
                message_type="system",
                timestamp=datetime.now(),
                content=TextContent(
                    message=f"You have requested heartbeats {loops_since_overthink_warning} times in a row. You should double-check whether you have gathered sufficient information to accurately answer the user's query or finish your background tasks. If you have, please send a final message to the user or finish up your tasks and then set your 'do_heartbeat' field to false. If you have not, please carry on until you have."
                ),
            )
            memory.push_message(system_message)

            conn.send(
                AgentToParentMessage.model_validate(
                    {
                        "message_type": "message",
                        "payload": system_message.to_intermediate_repr(),
                    }
                ).model_dump_json()
            )

            loops_since_overthink_warning = 0

        return (
            do_heartbeat,
            ctx_window_warning_given_flag,
            loops_since_overthink_warning,
        )

    def post(
        self,
        shared: Dict[str, Any],
        prep_res: Tuple[Memory, bool, Connection, int, bool],
        exec_res: Tuple[bool, bool, int],
    ) -> Optional[str]:
        do_heartbeat, ctx_window_warning_given_flag, loops_since_overthink_warning = (
            exec_res
        )

        shared["ctx_window_warning_given_flag"] = ctx_window_warning_given_flag

        return "heartbeat" if do_heartbeat else None


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
    call_agent_node - "invalid_function" >> invalid_function_node
    invalid_function_node >> exit_or_continue_node

    exit_or_continue_node - "heartbeat" >> call_agent_node

    return Flow(start=call_agent_node)


# *Agent runner functions
def create_new_agent(
    optional_function_sets: List[str], agent_persona: str, user_persona: Optional[str]
) -> str:
    agent_id = uuid4()

    db.write(
        """
        INSERT INTO agents (id, optional_function_sets)
        VALUES (%s, %s);
        """,
        (
            agent_id,
            optional_function_sets,
        ),
    )

    db.write(
        """
        INSERT INTO working_context (id, agent_id, agent_persona, user_persona, tasks)
        VALUES (%s, %s, %s, %s, %s);
        """,
        (
            uuid4(),
            agent_id,
            agent_persona,
            user_persona
            or "This is what I know about the user. I should update this persona as our conversation progresses",
            [],
        ),
    )

    db.create_chromadb_client().create_collection(str(agent_id))

    return str(agent_id)


def list_agents() -> List[Tuple[str, datetime]]:
    return db.read("SELECT id, created_at FROM agents;")


def get_agent_info(agent_id: str) -> Tuple[str, str, List[str], datetime]:
    optional_function_sets_json, created_at = db.read(
        "SELECT optional_function_sets, created_at FROM agents WHERE id = %s;",
        (agent_id,),
    )[0]

    return (
        *db.read(
            "SELECT agent_persona, user_persona FROM working_context WHERE agent_id = %s;",
            (agent_id,),
        )[0],
        optional_function_sets_json,
        created_at,
    )


def delete_agent(agent_id: str) -> None:
    db.write("DELETE FROM agents WHERE id = %s;", (agent_id,))
    db.write("DELETE FROM working_context WHERE agent_id = %s;", (agent_id,))
    db.write("DELETE FROM recall_storage WHERE agent_id = %s;", (agent_id,))
    db.write("DELETE FROM fifo_queue WHERE agent_id = %s;", (agent_id,))

    db.create_chromadb_client().delete_collection(agent_id)


def list_optional_function_sets() -> List[str]:
    base_function_sets_dir = os.path.join(
        os.path.dirname(__file__), "function_sets", "optional"
    )

    return list(
        map(
            lambda fsf: fsf.replace(".py", ""),
            filter(lambda fsf: fsf.endswith(".py"), os.listdir(base_function_sets_dir)),
        )
    )


def call_agent_worker(agent_id: str, conn: Connection) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        conn.send(
            AgentToParentMessage.model_validate(
                {"message_type": "debug", "payload": "Loading agent memory..."}
            ).model_dump_json()
        )
        memory = get_memory_object(agent_id)

        conn.send(
            AgentToParentMessage.model_validate(
                {"message_type": "debug", "payload": "Loading agent flow..."}
            ).model_dump_json()
        )
        agent_flow = get_agent_flow(memory)

        shared = {
            "memory": memory,
            "conn": conn,
            "loops_since_overthink_warning": 0,
            "ctx_window_warning_given_flag": False,
        }

        conn.send(
            AgentToParentMessage.model_validate(
                {"message_type": "debug", "payload": "Starting agent loop..."}
            ).model_dump_json()
        )

        agent_flow.run(shared)
    except Exception:
        conn.send(
            AgentToParentMessage.model_validate(
                {"message_type": "error", "payload": traceback.format_exc()}
            ).model_dump_json()
        )
    finally:
        try:
            conn.send(
                AgentToParentMessage.model_validate(
                    {"message_type": "halt"}
                ).model_dump_json()
            )
        except Exception:
            pass
        conn.close()


def call_agent(
    agent_id: str,
) -> Generator[
    Union[ATPM_Message, ATPM_Debug, ATPM_Error, ATPM_ToUser, ATPM_Halt, None],
    str,
    None,
]:
    parent_conn, child_conn = Pipe()
    p = Process(target=call_agent_worker, args=(agent_id, child_conn))
    p.start()

    # print("Stream start")

    try:
        while True:
            try:
                if parent_conn.poll(0.25):
                    msg = AgentToParentMessage.model_validate(
                        orjson.loads(parent_conn.recv())
                    ).root
                    if msg.message_type == "halt":
                        yield msg
                        break
                else:
                    msg = None
            except EOFError:
                break

            input_cmd = yield msg
            if input_cmd:
                if input_cmd not in [
                    "halt",
                    "halt_soon",
                ]:
                    input_cmd = "halt"  # *automatically send halt signal because error

                parent_conn.send(input_cmd)
    finally:
        child_conn.close()
        parent_conn.close()
        p.join()
        # print("End of stream")
