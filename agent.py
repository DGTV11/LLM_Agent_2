import json
from datetime import datetime
from multiprocessing import Pipe, Process
from multiprocessing.connection import Connection
from typing import Annotated, Any, Dict, List, Tuple, TypedDict

import yaml
from pocketflow import *
from pydantic import BaseModel, conint

from llm import call_llm, llm_tokenise
from memory import AssistantMessageContent, Memory, Message, TextContent


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


class Agent:
    def __init__(self, memory: Memory):
        self.memory = memory

        call_agent_node = CallAgent(max_retries=10)
        function_node_dict = self.memory.function_sets.get_function_nodes()
        self.flow = Flow(start=call_agent_node)  # TODO: construct dynamically

    def call_agent(self, conn: Connection):
        shared = {"memory": self.memory, "conn": conn}

        self.flow.run(shared)

        conn.send(None)


def agent_step(agent: Agent):
    parent_conn, child_conn = Pipe()

    p = Process(target=agent.call_agent, args=(child_conn,))
    p.start()

    while True:
        msg = parent_conn.recv()
        if msg is None:
            break
        yield msg

    p.join()
