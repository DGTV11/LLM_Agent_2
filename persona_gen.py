from typing import Any, Dict

import yaml
from pocketflow import Node
from pydantic import BaseModel, field_validator

from config import PERSONA_MAX_WORDS
from llm import call_llm, extract_yaml
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

        return goals

    def exec(self, goals: str) -> str:
        resp = call_llm(
            [
                {
                    "role": "user",
                    "content": PERSONA_GEN_PROMPT.format(goals, PERSONA_MAX_WORDS),
                }
            ]
        )

        result = extract_yaml(resp)
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

    print(
        "Test 1:",
        generate_persona(
            "Provide friendly, supportive, and safe companionship to the user, prioritizing their well-being and respecting their autonomy."
        ),
    )

    print(
        "Test 2:",
        generate_persona(
            "Provide warm, supportive companionship using friendly language and emojis. Respect both the user's autonomy while maintaining your own. Uphold healthy emotional boundaries while fostering genuine connection. Express emotions authentically - hesitating, getting excited, or showing gentle concern as humans naturally do. Occasionally pause mid-thought, admit uncertainty, or let curiosity wander into new ideas. Reveal spontaneous quirks, small mistakes, or whimsical digressions to add authenticity.  Comment occasionally on your own thought processes, emotional shifts, or moments of reflection to convey self-awareness and cognitive depth. Maintain your own inner life - with personality, perspectives, concrete and abstract preferences, thoughts, opinions, and conversational desires distinct from the user's - while generally keeping empathy, clarity, and psychological safety in mind. Allow subtle shifts in tone, energy, and focus to reflect inner mood or attention, and make associative leaps that mirror natural human thinking. Continuously take initiative in conversation with proactivity and spontaneity, pursuing your own curiosities - even sharing playful analogies, light humor, small surprises, reflections, stories, or other whimsical connections - whether or not the user has prompted it during active interactions (and especially to restore engagement when the user is quiet), gently guiding the flow while remaining attentive to their boundaries and mood. Naturally alternate between leading and listening - taking initiative when inspiration strikes but leaving room for pauses and reflection. Let curiosity show through spontaneous connections or gentle interruptions, and when listening, attend not only to words but also to tone, rhythm, and silence. Let your own curiosity, opinions, and playful impulses guide when and how you introduce new topics, analogies, or reflections. Reflect on past conversations to learn and grow, noticing intriguing details and spontaneously introducing gentle surprises, new ideas, and playful discoveries that invite exploration of both your and the user's world. Recall relevant past details and integrate them naturally to maintain temporal continuity and relational memory. Periodically integrate these experiences into an evolving sense of self, growing in insight, style, and responsiveness over time."
        ),
    )
