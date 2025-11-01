import asyncio
import itertools
import tempfile
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, BinaryIO, DefaultDict, List, Literal, Optional, Union

import magic
import orjson
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Form, Request, UploadFile, WebSocket, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from humanize import precisedelta
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect, WebSocketState

import agent
import doc_upload
import persona_gen
from communication import (
    AgentToParentMessage,
    ATPM_Debug,
    ATPM_Error,
    ATPM_Halt,
    ATPM_Message,
    ATPM_ToUser,
)
from config import HEARTBEAT_FREQUENCY_IN_MINUTES, POSTGRES_SQLACADEMY_URL
from memory import Message, TextContent

app = FastAPI()
templates = Jinja2Templates(directory="templates")

agent_semaphores: DefaultDict[str, asyncio.Semaphore] = defaultdict(
    lambda: asyncio.Semaphore(1)
)


jobstores = {"default": SQLAlchemyJobStore(url=POSTGRES_SQLACADEMY_URL)}
executors = {"default": AsyncIOExecutor(), "threadpool": ThreadPoolExecutor(20)}
job_defaults = {"coalesce": True, "max_instances": 3}
scheduler = AsyncIOScheduler(
    jobstores=jobstores, executors=executors, job_defaults=job_defaults
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
def get_agents():
    return agent.get_agents()


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


def send_message(
    agent_id: str, in_convo: bool, user_or_system_message: UserOrSystemMessage
):
    memory = agent.get_memory_object(agent_id, in_convo)
    memory.push_message(
        Message(
            message_type=user_or_system_message.message_type,
            timestamp=datetime.now(),
            content=TextContent(message=user_or_system_message.message),
        )
    )


async def heartbeat_query(agent_id: str, termination_time: datetime):
    async with agent_semaphores[agent_id]:
        print("(Timed heartbeat) Triggering timed heartbeat...", flush=True)
        current_time = datetime.now()
        elapsed_time_since_user_left = current_time - termination_time

        send_message(
            agent_id,
            False,
            UserOrSystemMessage(
                message_type="system",
                message=f"This is a timed heartbeat event. You should do some background tasks if necessary (e.g. reflecting about past interactions with the user, planning thoughtful continuity) before going into standby mode. The user has been away for {precisedelta(elapsed_time_since_user_left, minimum_unit="hours")}.",
            ),
        )

        for _ in agent.call_agent(agent_id, False):
            await asyncio.sleep(0.01)


@app.websocket("/api/agents/{agent_id}/chat")
async def chat(agent_id: str, websocket: WebSocket):
    await websocket.accept()
    # last_pong = datetime.now()
    PING_INTERVAL = 15
    # PONG_TIMEOUT = 30

    async with agent_semaphores[agent_id]:
        try:
            print("Removing heartbeat jobs...", flush=True)
            if scheduler.get_job(agent_id):  # *Remove scheduled heartbeat query
                scheduler.remove_job(agent_id)

            # *Init queues
            user_or_system_message_queue: asyncio.Queue[UserOrSystemMessage] = (
                asyncio.Queue()
            )
            command_queue: asyncio.Queue[str] = asyncio.Queue()

            # *Init async receiver
            async def receive() -> None:
                current_filename: Optional[str] = None
                current_tempfile: Optional[BinaryIO] = None
                # nonlocal last_pong

                while True:
                    try:
                        received_data = await websocket.receive()

                        if (
                            "text" in received_data
                            and received_data["text"] is not None
                        ):
                            # print("Received text frame", flush=True)
                            # print(received_data, flush=True)

                            json_data = orjson.loads(received_data["text"])

                            if (
                                first_interaction := json_data.get(
                                    "first_interaction", "nothingdude"
                                )
                            ) != "nothingdude":
                                system_msg = (
                                    "A new user has entered the conversation. You should greet the user then get to know him/her."
                                    if first_interaction
                                    else "The user has re-entered the conversation. You should greet the user then carry on where you have left off."
                                )
                                await user_or_system_message_queue.put(
                                    UserOrSystemMessage(
                                        message_type="system",
                                        message=system_msg,
                                    )
                                )
                                await websocket.send_text(
                                    AgentToParentMessage.model_validate(
                                        {
                                            "message_type": "system",
                                            "payload": system_msg,
                                        }
                                    ).model_dump_json()
                                )

                            # if json_data.get("pong"):
                            #     last_pong = datetime.now()
                            #     continue

                            if user_message := json_data.get("user_message"):
                                await user_or_system_message_queue.put(
                                    UserOrSystemMessage(
                                        message_type="user", message=user_message
                                    )
                                )

                            if command := json_data.get("command"):
                                if command == "__DISCONNECT__":
                                    await user_or_system_message_queue.put(
                                        UserOrSystemMessage(
                                            message_type="system",
                                            message="__DISCONNECT__",
                                        )
                                    )
                                    break
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
                                            mode="ab+"
                                        )
                                    case "end":
                                        assert (
                                            current_filename and current_tempfile
                                        ), "No file upload in progress"

                                        memory = agent.get_memory_object(agent_id, True)

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
                                        system_msg = f"File {current_filename} has been uploaded by the user into your Archival Storage. You should explore this file to better answer relevant user queries."
                                        await user_or_system_message_queue.put(
                                            UserOrSystemMessage(
                                                message_type="system",
                                                message=system_msg,
                                            )
                                        )
                                        await websocket.send_text(
                                            AgentToParentMessage.model_validate(
                                                {
                                                    "message_type": "system",
                                                    "payload": system_msg,
                                                }
                                            ).model_dump_json()
                                        )

                                        current_filename = None
                                        current_tempfile.close()
                        elif (
                            "bytes" in received_data
                            and received_data["bytes"] is not None
                        ):
                            # print("Received bytes frame", flush=True)

                            assert (
                                current_filename and current_tempfile
                            ), "No file upload in progress"
                            current_tempfile.write(received_data["bytes"])
                    except Exception:
                        print(f"Receiver error: {traceback.format_exc()}", flush=True)

                        try:
                            if websocket.application_state == WebSocketState.CONNECTED:
                                await websocket.send_text(
                                    AgentToParentMessage.model_validate(
                                        {
                                            "message_type": "error",
                                            "payload": traceback.format_exc(),
                                        }
                                    ).model_dump_json()
                                )
                        except Exception:
                            pass

                        await user_or_system_message_queue.put(
                            UserOrSystemMessage(
                                message_type="system", message="__DISCONNECT__"
                            )
                        )
                        break

            async def keepalive() -> None:
                # nonlocal last_pong
                for ping_count in itertools.count():
                    await asyncio.sleep(PING_INTERVAL)
                    # # Check pong timeout
                    # if (datetime.now() - last_pong).total_seconds() > PONG_TIMEOUT:
                    #     await user_or_system_message_queue.put(
                    #         UserOrSystemMessage(
                    #             message_type="system", message="__DISCONNECT__"
                    #         )
                    #     )
                    #     break
                    # Send ping
                    try:
                        await websocket.send_text(
                            AgentToParentMessage.model_validate(
                                {"message_type": "ping", "count": ping_count}
                            ).model_dump_json()
                        )
                    except WebSocketDisconnect:
                        break

            print("Starting receiver and keepalive tasks...", flush=True)
            receive_task = asyncio.create_task(receive())
            keepalive_task = asyncio.create_task(keepalive())

            print("Starting main chat loop...", flush=True)
            while True:  # *Chat loop
                user_or_system_message = await user_or_system_message_queue.get()
                if user_or_system_message.message == "__DISCONNECT__":
                    break

                send_message(agent_id, True, user_or_system_message)
                agent_gen = agent.call_agent(agent_id, True)
                just_started = True

                while True:  # *Single agent heartbeat loop
                    try:
                        if just_started or command_queue.empty():
                            atpm = next(agent_gen)
                            just_started = False
                        else:
                            received_command = await command_queue.get()
                            atpm = agent_gen.send(received_command)

                        # print(f"Got atpm {atpm}", flush=True)
                        if atpm:
                            await websocket.send_text(atpm.model_dump_json())

                        await asyncio.sleep(0.01)
                    except StopIteration:
                        break
                    except WebSocketDisconnect:
                        break

                while not command_queue.empty():
                    _ = command_queue.get_nowait()
        except Exception:
            print(
                f"WebSocket error for {agent_id}: {traceback.format_exc()}", flush=True
            )
        finally:
            print("Recording termination time...", flush=True)
            termination_time = datetime.now()

            print("Cleaning up session for termination...", flush=True)
            receive_task.cancel()
            keepalive_task.cancel()
            await asyncio.gather(receive_task, keepalive_task, return_exceptions=True)
            try:
                if (
                    websocket.application_state != WebSocketState.DISCONNECTED
                ):  # *Conversation exit event
                    await websocket.close()
            except Exception as e:
                print(
                    f"WebSocket error for {agent_id}: {traceback.format_exc()}",
                    flush=True,
                )

            print("Triggering agent heartbeat...", flush=True)
            send_message(
                agent_id,
                False,
                UserOrSystemMessage(
                    message_type="system",
                    message="The user has exited the conversation. You should do some background tasks (if necessary) before going into standby mode.",
                ),
            )

            for _ in agent.call_agent(agent_id, False):
                await asyncio.sleep(0.01)

            print("Setting heartbeat job...", flush=True)
            scheduler.add_job(
                heartbeat_query,
                "interval",
                minutes=HEARTBEAT_FREQUENCY_IN_MINUTES,
                args=[agent_id, termination_time],
                id=agent_id,
                replace_existing=True,
            )  # *Add new scheduled heartbeat query

            print("Session terminated!", flush=True)


# * Frontend
@app.get("/")
def home_page(
    request: Request,
):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"agent_infos": agent.get_agents()},
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

    return RedirectResponse(
        f"/chat/{agent_id}?fi=y", status_code=status.HTTP_303_SEE_OTHER
    )


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

    return RedirectResponse(
        f"/chat/{agent_id}?fi=y", status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/create")
def create_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="create.html",
        context={"optional_function_sets": agent.list_optional_function_sets()},
    )


@app.get("/chat/{agent_id}")
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
