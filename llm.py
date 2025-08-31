# from debug import printd
import re
from typing import Any, Dict, List, Union, cast

import yaml
from openai import OpenAI
from transformers import AutoTokenizer  # type: ignore[attr-defined]

from config import (
    HF_LLM_NAME,
    HF_TOKEN,
    LLM_API_BASE_URL,
    LLM_API_KEY,
    LLM_MODELS,
    VLM_API_BASE_URL,
    VLM_API_KEY,
    VLM_MODELS,
)

llm_client = OpenAI(base_url=LLM_API_BASE_URL, api_key=LLM_API_KEY)
vlm_client = OpenAI(base_url=VLM_API_BASE_URL, api_key=VLM_API_KEY)


def call_llm(messages: List[Dict[str, str]]) -> str:
    last_error = None

    for model in LLM_MODELS:
        try:
            completion = llm_client.chat.completions.create(
                model=model.strip(),
                messages=cast(Any, messages),
            )

            assert completion.choices[0].message.content
            return completion.choices[0].message.content
        except Exception as e:
            last_error = e
            print(f"{model} failed: {e}")

    raise RuntimeError(f"All models failed: {last_error}")


def call_vlm(messages: List[Dict[str, Union[str, Any]]]) -> str:
    last_error = None

    for model in LLM_MODELS:
        try:
            completion = vlm_client.chat.completions.create(
                model=model.strip(),
                messages=cast(Any, messages),
            )

            assert completion.choices[0].message.content
            return completion.choices[0].message.content
        except Exception as e:
            last_error = e
            print(f"{model} failed: {e}")

    raise RuntimeError(f"All models failed: {last_error}")


# *FOR IMAGES
# {
#     "role": "user",
#     "content": [
#         {"type": "text", "text": prompt.strip()},
#         {
#             "type": "image_url",
#             "image_url": {
#                 "url": f"data:image/{img_type};base64,{b64_image}"
#             },
#         },
#     ],
# },


def extract_yaml(resp: str) -> Dict[str, Any]:
    match = re.search(r"```(?:ya?ml)?\s*([\s\S]*?)```", resp, re.IGNORECASE)
    if match:
        yaml_str = match.group(1).strip()
    else:
        # fallback: maybe whole response is YAML
        yaml_str = resp.strip()

    return yaml.safe_load(yaml_str)


def llm_tokenise(messages: List[Dict[str, str]]) -> Union[List[int], Any]:
    tokeniser = AutoTokenizer.from_pretrained(HF_LLM_NAME, token=HF_TOKEN)  # type: ignore[no-untyped-call]
    assert (
        messages[0]["role"] == "system" and messages[1]["role"] == "user"
    ) or messages[0]["role"] == "user"

    if messages[0]["role"] == "system" and messages[1]["role"] == "user":
        sys_prompt = messages.pop(0)["content"]
        messages[0]["content"] = sys_prompt + messages[0]["content"]

    return tokeniser.apply_chat_template(messages, tokenize=True)
