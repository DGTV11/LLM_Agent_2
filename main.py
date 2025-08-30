import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Annotated, List, Literal, Optional

from fastapi import FastAPI, Form, Request, WebSocket, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import agent
import persona_gen
from memory import Message, TextContent

app = FastAPI()
templates = Jinja2Templates(directory="templates")

agent_semaphores: defaultdict[str, asyncio.Semaphore] = defaultdict(
    lambda: asyncio.Semaphore(1)
)


# *Backend API


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
async def send_message(agent_id: str, user_or_system_message: UserOrSystemMessage):
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
async def interact(agent_id: str, websocket: WebSocket):
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


@app.post("/api/agents/{agent_id}/query")
async def interact_no_stream(agent_id: str):
    async with agent_semaphores[agent_id]:
        gen = agent.call_agent(agent_id)
        msg = next(gen)

        while True:
            try:
                msg = next(gen)
            except StopIteration:
                break
            await asyncio.sleep(0.05)  # small sleep to avoid tight loop


# * Frontend
@app.get("/")
def home_page(
    request: Request,
):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"agent_infos": agent.list_agents()},
    )


@app.post("/create/raw-agent-persona")
def create_agent_using_raw_agent_persona(
    agent_persona: Annotated[str, Form()],
    user_persona: Annotated[Optional[str], Form()],
    optional_function_sets: Annotated[Optional[List[str]], Form] = Form([]),
):
    agent_id = agent.create_new_agent(
        optional_function_sets,
        agent_persona,
        user_persona,
    )

    return RedirectResponse(f"/{agent_id}?fi=y", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/create/generated-agent-persona")
def create_agent_using_generated_agent_persona(
    agent_goals: Annotated[str, Form()],
    user_persona: Annotated[Optional[str], Form()],
    optional_function_sets: Annotated[Optional[List[str]], Form] = Form([]),
):
    agent_id = agent.create_new_agent(
        optional_function_sets,
        persona_gen.generate_persona(agent_goals),
        user_persona,
    )

    return RedirectResponse(f"/{agent_id}?fi=y", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/create")
def create_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="create.html",
        context={"optional_function_sets": agent.list_optional_function_sets()},
    )


@app.get("/{agent_id}")
def chat_page(agent_id: str, request: Request):
    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={"agent_id": agent_id},
        # context={"optional_function_sets": agent.list_optional_function_sets()},
    )
