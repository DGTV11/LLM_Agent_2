import asyncio
from collections import defaultdict
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel

import agent
import persona_gen
from memory import Message, TextContent

app = FastAPI()

agent_semaphores: defaultdict[str, asyncio.Semaphore] = defaultdict(
    lambda: asyncio.Semaphore(1)
)


class AgentGoals(BaseModel):
    goals: str


@app.post("/api/persona-generator")
def generate_persona(agent_goals: AgentGoals):
    return persona_gen.generate_persona(agent_goals.goals)


@app.get("/api/optional-function-sets")
def list_optional_function_sets():
    return agent.list_optional_function_sets()


@app.get("/api/agents")
def list_agents():
    return agent.list_agents()


@app.get("/api/agents/{agent_id}")
def get_agent_info(agent_id: str):
    return agent.get_agent_info(agent_id)


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    async with agent_semaphores[agent_id]:
        agent.delete_agent(agent_id)


class AgentDefinition(BaseModel):
    optional_function_sets: List[str]
    agent_persona: str
    user_persona: Optional[str]


@app.post("/api/agents")
def create_agent(agent_definition: AgentDefinition):
    return agent.create_new_agent(
        agent_definition.optional_function_sets,
        agent_definition.agent_persona,
        agent_definition.user_persona,
    )


class UserOrSystemMessage(BaseModel):
    message_type: Literal["user", "system"]
    message: str


@app.post("/api/agents/{agent_id}/send-message")
async def send_message_no_stream(
    agent_id: str, user_or_system_message: UserOrSystemMessage
):
    async with agent_semaphores[agent_id]:
        memory = agent.get_memory_object(agent_id)
        memory.push_message(
            Message(
                message_type=user_or_system_message.message_type,
                timestamp=datetime.now(),
                content=TextContent(message=user_or_system_message.message),
            )
        )


@app.websocket("/api/agents/{agent_id}/interact")
async def send_message(agent_id: str, websocket: WebSocket):
    async with agent_semaphores[agent_id]:
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
