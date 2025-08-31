1. [x] Create API 
- Agent child process <-spawns-> Agent server (daemon, can also automatically call agent for heartbeat) <-communicates with-> Websocket
- need to be able to query messages between leaving and joining back (because heartbeat)
- websockets used for convo streaming

2. [x] Create semaphores and make the stream endpt `send msg+stream`
```
import asyncio
from collections import defaultdict

# Dictionary to store semaphores per ID
id_semaphores = defaultdict(lambda: asyncio.Semaphore(1)) # Default limit of 1 per ID
```

2. [x] Create heartbeat system (bg daemon using https://apscheduler.readthedocs.io/en/3.x/)

3. [x] Create suitable frontend (FastAPI or Gradio)
- modal with messages between leaving and joining back
- Messages   | Consciousness Stream
  \[history] | Last user message
  \[history] | agent/system messages...

4. [ ] Implement optional functions
- Web search (https://github.com/searxng/searxng)
- Python runner (https://github.com/vndee/llm-sandbox)

5. [ ] Add file upload using the ConceptCycle file upload system

6. [ ] Switch from sqlite to postgres (optional)

Remember:
- Web search should spawn a different kind of agent (Research agent)
