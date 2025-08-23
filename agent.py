from typing import Any, Dict, List

from pocketflow import *

from llm import call_llm, llm_tokenise
from memory import Memory


class ExitHeartbeatLoop(Node):
    def exec(prep_res):
        print("No heartbeat requested, exiting agent loop")


class CallAgent(Node):
    def prep(self, shared: Dict[str, Any]) -> Memory:
        memory = shared["memory"]
        assert isinstance(memory, Memory)

        return memory

    def exec(self, memory: Memory):
        resp = call_llm(memory.main_ctx)

        yaml_str = resp.split("```yaml")[1].split("```")[0].strip()
        result = yaml.safe_load(yaml_str)

        pass

    def post(self, shared, prep_res, exec_res):
        pass
        shared["draft"] = exec_res


call_agent_node = CallAgent(max_retries=10)


class Agent:
    def __init__(self, memory: Memory):
        flow = Flow(start=call_agent_node)


def agent_step(agent: Agent):
    pass
