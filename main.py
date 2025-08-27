import os
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

import agent
import persona_gen

app = FastAPI()


class AgentGoals(BaseModel):
    goals: str


@app.post("/persona-generator")
def generate_persona(agent_goals: AgentGoals):
    return persona_gen.generate_persona(agent_goals.goals)


@app.get("/optional-function-sets")
def get_optional_function_sets():
    base_function_sets_dir = os.path.join(
        os.path.dirname(__file__), "function_sets", "optional"
    )

    return list(
        map(
            lambda fsf: fsf.replace(".py", ""),
            filter(lambda fsf: fsf.endswith(".py"), os.listdir(base_function_sets_dir)),
        )
    )


@app.get("/agents")
def list_agents():
    return agent.list_agents()


@app.get("/agents/{agent_id}")
def get_agent_info(agent_id: str):
    return agent.get_agent_info(agent_id)


@app.delete("/agents/{agent_id}")
def delete_agent(agent_id: str):
    agent.delete_agent(agent_id)


class AgentDefinition(BaseModel):
    optional_function_sets: List[str]
    agent_persona: str
    user_persona: Optional[str]


@app.post("/agents")
def create_agent(agent_definition: AgentDefinition):
    return agent.create_new_agent(
        agent_definition.optional_function_sets,
        agent_definition.agent_persona,
        agent_definition.user_persona,
    )
