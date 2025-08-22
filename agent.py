from typing import Any, Dict, List

from pocketflow import *

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
