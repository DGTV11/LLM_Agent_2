# from debug import printd
from typing import Any, Dict, List, Union, cast

from openai import OpenAI
from transformers import AutoTokenizer  # type: ignore[attr-defined]

from config import (
    HF_LLM_NAME,
    HF_TOKEN,
    LLM_API_BASE_URL,
    LLM_API_KEY,
    LLM_NAME,
    VLM_API_BASE_URL,
    VLM_API_KEY,
    VLM_NAME,
)

llm_client = OpenAI(base_url=LLM_API_BASE_URL, api_key=LLM_API_KEY)
vlm_client = OpenAI(base_url=VLM_API_BASE_URL, api_key=VLM_API_KEY)


def call_llm(messages: List[Dict[str, str]]) -> str:
    completion = llm_client.chat.completions.create(
        model=LLM_NAME,
        messages=cast(Any, messages),
    )
    # printd(prompt.strip() + "," + completion.choices[0].message.content)

    assert completion.choices[0].message.content
    return completion.choices[0].message.content


def call_vlm(messages: List[Dict[str, Union[str, Any]]]) -> str:
    completion = vlm_client.chat.completions.create(
        model=VLM_NAME,
        messages=cast(Any, messages),
    )

    # printd(prompt.strip() + "," + completion.choices[0].message.content)

    assert completion.choices[0].message.content
    return completion.choices[0].message.content

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


def llm_tokenise(messages: List[Dict[str, str]]) -> Union[List[int], Any]:
    tokeniser = AutoTokenizer.from_pretrained(HF_LLM_NAME, token=HF_TOKEN)  # type: ignore[no-untyped-call]
    assert (
        messages[0]["role"] == "system" and messages[1]["role"] == "user"
    ) or messages[0]["role"] == "user"

    if messages[0]["role"] == "system" and messages[1]["role"] == "user":
        sys_prompt = messages.pop(0)["content"]
        messages[0]["content"] = sys_prompt + messages[0]["content"]

    return tokeniser.apply_chat_template(messages, tokenize=True)
