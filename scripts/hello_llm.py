"""Sanity check: call the LLM and get validated structured output via forced tool use."""

import sys

from anthropic import Anthropic
from pydantic import BaseModel

from p2p.config import settings


class Greeting(BaseModel):
    message: str
    vendor_example: str


def main() -> None:
    if not settings.anthropic_api_key or not settings.anthropic_model:
        sys.exit("Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL in .env first.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=200,
        tools=[
            {
                "name": "return_greeting",
                "description": "Return a greeting and an example luxury-goods vendor name.",
                "input_schema": Greeting.model_json_schema(),
            }
        ],
        tool_choice={"type": "tool", "name": "return_greeting"},
        messages=[{"role": "user", "content": "Say hello and invent one leather supplier name."}],
    )
    block = next(b for b in response.content if b.type == "tool_use")
    greeting = Greeting.model_validate(block.input)
    print(greeting)
    print(f"tokens in/out: {response.usage.input_tokens}/{response.usage.output_tokens}")


if __name__ == "__main__":
    main()
