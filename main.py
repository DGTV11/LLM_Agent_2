import asyncio
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel

import agent
import persona_gen
from memory import Message, TextContent

app = FastAPI()


class AgentGoals(BaseModel):
    goals: str


@app.post("/persona-generator")
def generate_persona(agent_goals: AgentGoals):
    return persona_gen.generate_persona(agent_goals.goals)


@app.get("/optional-function-sets")
def list_optional_function_sets():
    return agent.list_optional_function_sets()


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


class UserOrSystemMessage(BaseModel):
    message_type: Literal["user", "system"]
    message: str


@app.post("/agents/{agent_id}/send-message")
def send_message(agent_id: str, user_or_system_message: UserOrSystemMessage):
    memory = agent.get_memory_object(agent_id)
    memory.push_message(
        Message(
            message_type=user_or_system_message.message_type,
            timestamp=datetime.now(),
            content=TextContent(message=user_or_system_message.message),
        )
    )


@app.websocket("/agents/{agent_id}/stream")
async def agent_stream(agent_id: str, websocket: WebSocket):
    await websocket.accept()

    gen = agent.call_agent(agent_id)
    msg = next(gen)  # start generator

    async def receive_commands():
        try:
            while True:
                data = await websocket.receive_json()
                command = data.get("command")
                if command:
                    nonlocal msg
                    msg = gen.send(command)
        except Exception:
            pass

    # Run command receiver in background
    receive_task = asyncio.create_task(receive_commands())

    try:
        while True:
            if msg:
                await websocket.send_json(msg.model_dump())
            try:
                msg = next(gen)
            except StopIteration:
                break
            await asyncio.sleep(0.05)  # small sleep to avoid tight loop
    finally:
        receive_task.cancel()
        await websocket.close()
