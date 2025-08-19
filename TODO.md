1. Implement function loader (use Pydantic model and desc -> yaml schema)
- use shared state for agent state
- dynamically load functions using `agent_node - func_name >> function_node` for loop
- add yaml schemas using Pydantic
2. Implement persistent storage
- remember to add summary in separate Message outside of fifo queue (to preserve queue-ness)
3. Implement functions
- remember pagination!
