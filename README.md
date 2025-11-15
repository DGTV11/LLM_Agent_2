# LLM Agent 2

A rewrite of LLM_Agent

Based on [MemGPT](https://arxiv.org/abs/2310.08560)

SPR prompt taken from [here](https://github.com/daveshap/SparsePrimingRepresentations/blob/main/system.md)

Recursive summary prompt adapted from [here](https://github.com/daveshap/SparsePrimingRepresentations/blob/main/system.md)

Run chroma using `chroma run` in separate process before `uv run fastapi run/dev`

## Architectural Changes

- Using PocketFlow framework 
    - Functions use a modified Node and Pydantic Model validator
- Split agent `thoughts` string to `emotions` tuple list and `thoughts` string list to encourage emotional reasoning and CoT
- Switched from JSON to YAML for LLM structured output
- Added optional goal-based Agent Persona generator
- Added Task Queue to Working Context memory module (for more explicit short/long-horizon planning)
- Added Chat Log (user-agent-system message history to preserve conversational coherence)
