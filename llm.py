# from debug import printd
from openai import OpenAI

from config import (
    LLM_API_BASE_URL,
    LLM_API_KEY,
    LLM_NAME,
    VLM_API_BASE_URL,
    VLM_API_KEY,
    VLM_NAME,
)

llm_client = OpenAI(base_url=LLM_API_BASE_URL, api_key=LLM_API_KEY)
vlm_client = OpenAI(base_url=VLM_API_BASE_URL, api_key=VLM_API_KEY)


def call_llm(messages):
    completion = llm_client.chat.completions.create(
        model=LLM_NAME,
        messages=messages,
    )
    # printd(prompt.strip() + "," + completion.choices[0].message.content)

    return completion.choices[0].message.content


def call_vlm(messages):
    completion = vlm_client.chat.completions.create(
        model=VLM_NAME,
        messages=messages,
    )

    # printd(prompt.strip() + "," + completion.choices[0].message.content)

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
