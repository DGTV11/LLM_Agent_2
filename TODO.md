1. Implement memory subsystems (link to DB)
    - [x] FIFO Queue
    - [x] Working Context
    - [ ] Archival Storage
    - [ ] Recall Storage
    - [ ] Context Summariser
2. Implement function loader (use Pydantic model and desc -> yaml schema)+functions (Nodes)
    - use shared state for agent state
    - dynamically load functions using `agent_node - func_name >> function_node` for loop
    - add yaml schemas using Pydantic

Remember:
```
Agent Node (Queue Manager in post function of node) -> Function Node (multiple exists)
                         ^                                           |
                         |                                           |
                         --------------------------------------------+
                                                                     v
                                                                 Exit Node
```

Web search should spawn a different kind of agent (Research agent)
