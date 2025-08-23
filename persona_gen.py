from typing import Any, Dict

import yaml
from pocketflow import Node
from pydantic import BaseModel, field_validator

from config import PERSONA_MAX_WORDS
from llm import call_llm
from prompts import PERSONA_GEN_PROMPT


class GeneratePersonaResult(BaseModel):
    analysis: str
    persona: str

    @field_validator("persona")
    @classmethod
    def validate_persona(cls, p):
        persona_length = len(p.split())
        if persona_length > PERSONA_MAX_WORDS:
            raise ValueError(
                f"New persona too long (maximum length {PERSONA_MAX_WORDS}, requested length {persona_length})"
            )
        return p


class GeneratePersona(Node):
    def prep(self, shared: Dict[str, Any]) -> str:
        goals = shared["goals"]
        assert isinstance(goals, str)

        return shared["goals"]

    def exec(self, goals: str) -> str:
        resp = call_llm(
            [
                {
                    "role": "user",
                    "content": PERSONA_GEN_PROMPT.format(goals, PERSONA_MAX_WORDS),
                }
            ]
        )

        yaml_str = resp.split("```yaml")[1].split("```")[0].strip()
        result = yaml.safe_load(yaml_str)
        result_validated = GeneratePersonaResult.model_validate(result)

        return result_validated.persona

    def post(self, shared: Dict[str, Any], prep_res: str, exec_res: str) -> None:
        shared["persona"] = exec_res


generate_persona_node = GeneratePersona(max_retries=10)


def generate_persona(goals: str) -> str:
    shared = {"goals": goals}

    generate_persona_node.run(shared)

    return shared["persona"]


if __name__ == "__main__":
    print("THIS IS A TEST FOR persona_gen.py")

    assert input("DO YOU WISH TO PROCEED? (y/n) ").strip() == "y", "abort"

    goals = (
        input(
            'Input goals (if blank, default "Provide companionship to the user" will be used): '
        ).strip()
        or "Provide companionship to the user"
    )

    print(generate_persona(goals))
