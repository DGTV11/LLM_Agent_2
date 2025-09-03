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
- Using YAML instead of JSON as a structured output format
