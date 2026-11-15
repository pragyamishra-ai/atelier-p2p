"""Sanity check: call the LLM via Poe (OpenAI-compatible) and get validated structured output."""

import json
import sys

from openai import OpenAI
from pydantic import BaseModel

from p2p.config import settings


class Greeting(BaseModel):
    message: str
    vendor_example: str


def main() -> None:
    if not settings.poe_api_key or not settings.llm_model:
        sys.exit("Set POE_API_KEY and LLM_MODEL in .env first.")

    client = OpenAI(api_key=settings.poe_api_key, base_url=settings.llm_base_url)
    response = client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=200,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "return_greeting",
                    "description": "Return a greeting and an example luxury-goods vendor name.",
                    "parameters": Greeting.model_json_schema(),
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "return_greeting"}},
        messages=[{"role": "user", "content": "Say hello and invent one leather supplier name."}],
    )
    call = response.choices[0].message.tool_calls[0]
    greeting = Greeting.model_validate(json.loads(call.function.arguments))
    print(greeting)
    if response.usage:
        print(f"tokens in/out: {response.usage.prompt_tokens}/{response.usage.completion_tokens}")


if __name__ == "__main__":
    main()
