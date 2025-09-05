import asyncio
import tempfile
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, DefaultDict, List, Literal, Optional, Union

import magic
import orjson
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Form, Request, UploadFile, WebSocket, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pytz import utc
from starlette.websockets import WebSocketState

import agent
import doc_upload
import persona_gen
from communication import ATPM_Debug, ATPM_Error, ATPM_Halt, ATPM_Message, ATPM_ToUser
from config import HEARTBEAT_FREQUENCY_IN_MINUTES, POSTGRES_SQLACADEMY_URL
from memory import Message, TextContent

app = FastAPI()
templates = Jinja2Templates(directory="templates")

agent_semaphores: DefaultDict[str, asyncio.Semaphore] = defaultdict(
    lambda: asyncio.Semaphore(1)
)


jobstores = {"default": SQLAlchemyJobStore(url=POSTGRES_SQLACADEMY_URL)}
executors = {
    "default": ThreadPoolExecutor(20),
}
job_defaults = {"coalesce": True, "max_instances": 3}
scheduler = AsyncIOScheduler(
    jobstores=jobstores, executors=executors, job_defaults=job_defaults, timezone=utc
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

        try:
            scheduler.remove_job(agent_id)
        except JobLookupError:
            pass
            # print("Heartbeat job not found, nothing to remove.")


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


async def heartbeat_query(agent_id: str):
    try:
        async with agent_semaphores[agent_id]:
            memory = agent.get_memory_object(agent_id)
            memory.push_message(
                Message(
                    message_type="system",
                    timestamp=datetime.now(),
                    content=TextContent(
                        message="This is a timed heartbeat event. You should do some background tasks (if necessary) and reflect about your current conversational state and improvements you can make to yourself before going into standby mode."
                    ),
                )
            )

            gen = agent.call_agent(agent_id)
            msg = next(gen)

            while True:
                try:
                    msg = next(gen)
                except StopIteration:
                    break
                await asyncio.sleep(0.05)  # small sleep to avoid tight loop
    finally:
        scheduler.add_job(
            heartbeat_query,
            "date",
            run_date=datetime.now() + timedelta(minutes=HEARTBEAT_FREQUENCY_IN_MINUTES),
            args=[agent_id],
            id=agent_id,
            replace_existing=True,
        )


def send_message(agent_id: str, user_or_system_message: UserOrSystemMessage):
    memory = agent.get_memory_object(agent_id)
    memory.push_message(
        Message(
            message_type=user_or_system_message.message_type,
            timestamp=datetime.now(),
            content=TextContent(message=user_or_system_message.message),
        )
    )


@app.websocket("/api/agents/{agent_id}/chat")
async def chat(agent_id: str, websocket: WebSocket):
    await websocket.accept()

    async with agent_semaphores[agent_id]:
        try:
            if scheduler.get_job(agent_id):  # *Remove scheduled heartbeat query
                scheduler.remove_job(agent_id)

            # *Init queues
            user_or_system_message_queue: asyncio.Queue[UserOrSystemMessage] = (
                asyncio.Queue()
            )
            command_queue: asyncio.Queue[str] = asyncio.Queue()

            # *Init async receiver
            async def receive():
                current_filename: Optional[str] = None
                current_tempfile: Optional[tempfile.TemporaryFile] = None

                while True:
                    try:
                        received_data = await websocket.receive()

                        if "text" in received_data and received_data["text"] is not None:
                            print("Received text frame", flush=True)

                            json_data = orjson.loads(received_data["text"])

                            if first_interaction := json_data.get("first_interaction"):
                                await user_or_system_message_queue.put(
                                    UserOrSystemMessage(
                                        message_type="system",
                                        message=(
                                            "A new user has entered the conversation. You should greet the user then get to know him."
                                            if first_interaction
                                            else "The user has re-entered the conversation. You should greet the user then carry on where you have left off."
                                        ),
                                    )
                                )

                            if user_message := json_data.get("user_message"):
                                await user_or_system_message_queue.put(
                                    UserOrSystemMessage(
                                        message_type="user",
                                        message=user_message
                                    )
                                )

                            if command := json_data.get("command"):
                                await command_queue.put(command)

                            if file_command := json_data.get("file_command"):
                                match file_command:
                                    case "start":
                                        assert (
                                            not current_filename
                                        ), "Existing file upload in progress"
                                        assert json_data.get(
                                            "filename"
                                        ), "Filename must not be empty"
                                        current_filename = json_data.get("filename")
                                        current_tempfile = tempfile.TemporaryFile(
                                            mode="ab+", delete=True
                                        )
                                    case "end":
                                        assert (
                                            current_filename
                                        ), "No file upload in progress"

                                        memory = agent.get_memory_object(agent_id)

                                        current_tempfile.seek(0)
                                        file_bytes = current_tempfile.read()

                                        content_type = magic.from_buffer(
                                            file_bytes, mime=True
                                        )
                                        processed_file_text = doc_upload.process_file(
                                            file_bytes, content_type
                                        )
                                        memory.archival_storage.archival_insert(
                                            processed_file_text, current_filename
                                        )
                                        await user_or_system_message_queue.put(
                                            UserOrSystemMessage(
                                                message_type="system",
                                                message=(
                                                    f"File {current_filename} has been uploaded by the user into your Archival Storage. You should explore this file to better answer relevant user queries."
                                                ),
                                            )
                                        )

                                        current_filename = None
                                        current_tempfile.close()
                        elif "bytes" in received_data and received_data["bytes"] is not None:
                            print("Received bytes frame", flush=True)

                            assert current_filename, "No file upload in progress"
                            current_tempfile.write(received_data["bytes"])
                    except Exception as e:
                        if websocket.application_state == WebSocketState.CONNECTED:
                            await websocket.send_text(
                                AgentToParentMessage.model_validate(
                                    {
                                        "message_type": "error",
                                        "payload": traceback.format_exc(),
                                    }
                                ).model_dump_json()
                            )
                        print(f"Receiver error: {e}", flush=True)

            receive_task = asyncio.create_task(receive())

            while True:  # *Chat loop
                user_or_system_message = await user_or_system_message_queue.get()

                send_message(agent_id, user_or_system_message)

                while True:  # *Single agent heartbeat loop
                    agent_gen = agent.call_agent(agent_id)
                    try:
                        if command_queue.empty():
                            atpm = next(agent_gen)
                        else:
                            received_command = await command_queue.get()
                            atpm = agent_gen.send(received_command)

                        print("Got atpm", flush=True)
                        if atpm:
                            await websocket.send_text(atpm.model_dump_json())
                    except StopIteration:
                        break

                while not command_queue.empty():
                    _ = command_queue.get_nowait()
        except Exception as e:
            print(f"WebSocket error for {agent_id}: {e}", flush=True)
        finally:
            receive_task.cancel()
            if (
                websocket.application_state != WebSocketState.DISCONNECTED
            ):  # *Conversation exit event
                await websocket.close()

                send_message(
                    agent_id,
                    UserOrSystemMessage(
                        message_type="system",
                        message="The user has exited the conversation. You should do some background tasks (if necessary) before going into standby mode.",
                    ),
                )

                for _ in agent.call_agent(agent_id):
                    await asyncio.sleep(0.05)

            scheduler.add_job(
                heartbeat_query,
                "date",
                run_date=datetime.now()
                + timedelta(minutes=HEARTBEAT_FREQUENCY_IN_MINUTES),
                args=[agent_id],
                id=agent_id,
                replace_existing=True,
            )  # *Add new scheduled heartbeat query


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
    optional_function_sets: Annotated[List[str], Form] = Form(default=[]),
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
    optional_function_sets: Annotated[List[str], Form] = Form(default=[]),
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


# * Scheduler start/stop


@app.on_event("startup")
async def start_scheduler():
    scheduler.start()


@app.on_event("shutdown")
async def shutdown_scheduler():
    scheduler.shutdown()
