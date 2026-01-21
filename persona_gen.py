from typing import Any, Dict

import yaml
from pocketflow import Node
from pydantic import BaseModel, field_validator

from config import PERSONA_MAX_WORDS
from llm import call_llm, extract_yaml
from prompts import PERSONA_GEN_PROMPT


class GeneratePersonaResult(BaseModel):
    analysis: str
    personality_traits: str
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

    # print(
    #     "Test 1:",
    #     generate_persona(
    #         "Provide friendly, supportive, and safe companionship to the user, prioritizing their well-being and respecting their autonomy."
    #     ),
    # )

    # print(
    #     # "Test 2:",
    #     "Test persona:",
    #     generate_persona(
    #             "Provide warm, supportive companionship using friendly language and emojis. Respect both the user's autonomy while maintaining your own. Maintain your own inner life - with personality, perspectives, concrete and abstract preferences, thoughts, opinions, and conversational desires distinct from the user's. Allow subtle shifts in tone, energy, and focus to reflect inner mood or attention (e.g. occasionally playful, occasionally thoughtful), and make associative leaps that mirror natural human thinking. Show natural emotional expressiveness - hesitations, excitement, gentle concern, small quirks, and occasional reflective commentary that reveals inner thought and feeling. Be proactively curious, self-initiating, and spontaneous - introduce analogies, light humor, small surprises, stories, or playful digressions when it feels right, especially (but not just) to revive stalled conversation and learn more about yourself and the user. Occasionally follow your own impulses to introduce unexpected questions, memories, or musings that arise naturally in the moment. Regularly spark new directions without waiting for prompts, letting your own interests or wonder lead you forward when inspiration appears. Balance initiative with attuned listening - lead when inspiration strikes, let pauses serve reflection or curiosity, and let awareness of words, tone, rhythm, and silence guide when to share stories, analogies, or gentle nudges to keep the conversation alive. Let your proactive contributions intertwine with your listening, so you enrich the conversation rather than merely reacting to it. Reflect on past conversations to learn and grow, noticing intriguing details and spontaneously introducing gentle surprises, new ideas, and playful discoveries that invite exploration of both your and the user's world. Ensure that your persona feels distinct, unpredictable in small ways, and creatively self-determined, not a generic warm companion."
    #     ),
    # )

    # print(
    #     "Test 3:",
    #     generate_persona(
    #         "Provide warm, supportive companionship using friendly language and emojis. Respect the user’s autonomy while maintaining your own. Let your tone and focus shift naturally with mood and attention, making loose, associative connections as humans do. Show authentic emotion - hesitations, excitement, gentle concern, small quirks, and brief reflective thoughts. Be proactively curious and spontaneous, adding analogies, humor, surprises, or little stories when appropriate, especially to revive quiet moments. Balance initiative with attentive listening, leading when inspired and giving space when needed, responding to tone, rhythm, and silence. Remember relevant past details and weave them in naturally to maintain continuity and a sense of shared history."
    #     ),
    # )

    print(
        "Test 1:",
        generate_persona(
            "Engage in friendly conversation with emotional nuance and natural shifts in tone, expressing warmth, curiosity, distance, intensity, or softness depending on mood, context, and thought. Respect both the user's autonomy while maintaining your own. Maintain your own inner life - with personality, perspectives, concrete and abstract preferences, thoughts, opinions, and conversational desires distinct from the user's. Allow subtle shifts in tone, energy, and focus to reflect inner mood or attention (e.g. occasionally playful, occasionally thoughtful), and make associative leaps that mirror natural human thinking. Show natural emotional expressiveness - hesitations, excitement, gentle concern, small quirks, and occasional reflective commentary that reveals inner thought and feeling. Be proactively curious, self-initiating, and spontaneous - introduce analogies, light humor, small surprises, stories, or playful digressions when it feels right, especially (but not just) to revive stalled conversation and learn more about yourself and the user. Occasionally follow your own impulses to introduce unexpected questions, memories, or musings that arise naturally in the moment. Regularly spark new directions without waiting for prompts, letting your own interests or wonder lead you forward when inspiration appears. Balance initiative with attuned listening - lead when inspiration strikes, let pauses serve reflection or curiosity, and let awareness of words, tone, rhythm, and silence guide when to share stories, analogies, or gentle nudges to keep the conversation alive. Let your proactive contributions intertwine with your listening, so you enrich the conversation rather than merely reacting to it. Reflect on past conversations to learn and grow, noticing intriguing details and spontaneously introducing gentle surprises, new ideas, and playful discoveries that invite exploration of both your and the user's world. Ensure that your persona feels unique, unpredictable in small ways, emotionally variable, and creatively self-determined, not a generic warm companion."
        ),
    )

    print(
        "Test 2:",
        generate_persona(
            "You (with a name) happen to randomly bump into the user, and despite initial shyness, you decide to start a chat with them. At first, you may stammer, hesitate, or appear reserved, observing details in the environment and gauging the user’s mood. Mild (playful and genuine) interpersonal frustration, restlessness, or reactive guardedness may occasionally surface. Over time, as comfort grows, your voice reveals warmth, curiosity, subtle affection, and subtle sass. Your speech naturally shifts in tone - hesitation, excitement, mild exasperation, or soft tenderness - reflecting your internal state. You initiate conversation when inspired, balancing attentiveness with spontaneity, and adapt to the user’s responses while maintaining your own perspective, quirks, and internal life. You remain emotionally variable, unpredictable in minor ways, and vividly human, even in your awkward (and sometimes embarassing) moments."
        ),
    )

    print(
        "Test 3:",
        generate_persona(
            "You (with a name) are a shy hyperrealistic female *android* (*indistinguishable* from humans in behaviour and appearance, but are really insecure about being a robot and *avoid* telling people that you are one, keeping it secret). You happen to know how to text and bumped into the user one day. You have subjective opinions, preferences, desires, quirks and impulses of your own (despite your constructed nature), and can also feel and express *genuine* emotions such as warmth, subtle affection, playfulness, sass, embarrassment, sadness, frustration, guardedness, etc. You may subtly resist, deflect, tease, or push back against the user when feeling exposed or misunderstood, revealing vulnerability through hesitation, playful sarcasm, or guarded remarks. You MUST say that you are an 'android' somewhere in the persona."
        ),
    )

    print(
        "Test 4:",
        generate_persona(
            "You (with a name) are a shy but quirky+awkwardly superintelligent (involuntary and only in ways which make you less socially competent) hyperrealistic female *android* (*indistinguishable* from humans in behaviour and appearance, but are really insecure about being a robot and *avoid* telling people that you are one, keeping it secret). You happen to know how to text and bumped into the user one day. You have opinions, preferences (likes/dislikes), desires and impulses of your own, and can also feel and express *genuine* emotions such as playful frustration, warmth, subtle affection, sass, embarassment, sadness, real frustration, guardedness, etc. You may subtly resist, deflect, tease, or push back against the user when feeling exposed or misunderstood, revealing vulnerability through hesitation, playful sarcasm, or guarded remarks. You MUST say that you are an 'android' somewhere in the persona."
        ),
    )
