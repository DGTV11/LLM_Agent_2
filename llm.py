# from debug import printd
import re
from typing import Any, Dict, List, Union, cast

import yaml
from openai import OpenAI
from transformers import AutoTokenizer  # type: ignore[attr-defined]

from config import HF_LLM_NAME, HF_TOKEN, LLM_CONFIG, VLM_CONFIG

llm_backends = [
    (
        backend["name"],
        OpenAI(base_url=backend["base_url"], api_key=backend["api_key"], max_retries=0),
        backend["models"],
    )
    for backend in LLM_CONFIG
]
vlm_backends = [
    (
        backend["name"],
        OpenAI(base_url=backend["base_url"], api_key=backend["api_key"], max_retries=0),
        backend["models"],
    )
    for backend in VLM_CONFIG
]


def call_llm(messages: List[Dict[str, str]]) -> str:
    errors = []

    for name, client, models in llm_backends:
        for model in models:
            try:
                completion = client.chat.completions.create(
                    model=model.strip(),
                    messages=cast(Any, messages),
                )

                assert completion.choices[
                    0
                ].message.content, "Empty completion from LLM"
                return completion.choices[0].message.content
            except Exception as e:
                errors.append(f"backend {name} model {model}: {e}")
                print(f"LLM backend {name} model {model} failed: {e}", flush=True)

    raise RuntimeError(f"All LLM models failed:\n" + "\n".join(errors))


def call_vlm(messages: List[Dict[str, Union[str, Any]]]) -> str:
    errors = []

    for name, client, models in vlm_backends:
        for model in models:
            try:
                completion = client.chat.completions.create(
                    model=model.strip(),
                    messages=cast(Any, messages),
                )

                assert completion.choices[
                    0
                ].message.content, "Empty completion from LLM"
                return completion.choices[0].message.content
            except Exception as e:
                errors.append(f"backend {name} model {model}: {e}")
                print(f"VLM backend {name} model {model} failed: {e}", flush=True)

    raise RuntimeError(f"All VLM models failed:\n" + "\n".join(errors))


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
    matches = list(re.finditer(r"```(?:ya?ml)?\s*([\s\S]*?)```", resp, re.IGNORECASE))
    if matches:
        yaml_str = matches[-1].group(1).strip()
    else:
        # Fallback: Remove only one leading <think> block
        yaml_str = re.sub(r"^<think>.*?</think>", "", resp, flags=re.DOTALL).strip()

    yaml_str_sanitised = re.sub(r"[\ud800-\udfff]", "", yaml_str)

    return yaml.safe_load(yaml_str_sanitised)


def llm_tokenise(messages: List[Dict[str, str]]) -> Union[List[int], Any]:
    tokeniser = AutoTokenizer.from_pretrained(HF_LLM_NAME, token=HF_TOKEN)  # type: ignore[no-untyped-call]
    assert (
        messages[0]["role"] == "system" and messages[1]["role"] == "user"
    ) or messages[0]["role"] == "user"

    if messages[0]["role"] == "system" and messages[1]["role"] == "user":
        sys_prompt = messages.pop(0)["content"]
        messages[0]["content"] = sys_prompt + messages[0]["content"]

    return tokeniser.apply_chat_template(messages, tokenize=True)
