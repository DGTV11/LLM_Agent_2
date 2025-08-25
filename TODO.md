1. [ ] Create API 
- Agent child process <-spawns-> Agent server (daemon, can also automatically call agent for heartbeat) <-communicates with-> Websocket
- need to be able to query messages between leaving and joining back (because heartbeat)
- websockets used for convo streaming

2. [ ] Create suitable frontend (FastAPI or Gradio)
- modal with messages between leaving and joining back
- Messages   | Consciousness Stream
  \[history] | Last user message
  \[history] | agent/system messages...

2. [ ] Implement optional functions
- Web search (https://github.com/searxng/searxng)
- Python runner (https://github.com/vndee/llm-sandbox)

Remember:
- Web search should spawn a different kind of agent (Research agent)
