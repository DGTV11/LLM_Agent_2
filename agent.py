from pocketflow import *

from memory import Memory


class ExitNode(Node):
    def exec(prep_res):
        print("No heartbeat requested, exiting agent loop")


class AgentNode(Node):
    def prep(self, shared):
        return shared["memory"]  # TODO

    def exec(self, outline):
        pass

    def post(self, shared, prep_res, exec_res):
        pass
        shared["draft"] = exec_res


agent_node = AgentNode()


class Agent:
    def __init__(self, memory: Memory):
        # TODO: add function set adding
        flow = Flow(start=agent_node)


def agent_step(agent: Agent):
    pass
