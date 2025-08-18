from pocketflow import *

from memory import Memory


class AgentNode(Node):
    def exec(self, prep_res):
        print(f"Retry {self.cur_retry} times")
        raise Exception("Failed")


agent_node = AgentNode()


class Agent:
    def __init__(self, memory: Memory, function_sets: list[str]):
        # TODO: add function set adding
        flow = Flow(start=agent_node)


def agent_step(agent: Agent):
    pass
