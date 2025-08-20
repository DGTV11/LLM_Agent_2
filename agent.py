from pocketflow import *

from memory import Memory


class ExitHeartbeatLoop(Node):
    def exec(prep_res):
        print("No heartbeat requested, exiting agent loop")


class CallAgent(Node):
    def prep(self, shared):
        return shared["memory"]  # TODO

    def exec(self, outline):
        pass

    def post(self, shared, prep_res, exec_res):
        pass
        shared["draft"] = exec_res


call_agent_node = CallAgent()


class Agent:
    def __init__(self, memory: Memory):
        # TODO: add function set adding
        flow = Flow(start=call_agent_node)


def agent_step(agent: Agent):
    pass
