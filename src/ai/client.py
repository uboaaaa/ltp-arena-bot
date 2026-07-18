""" Communicates with AI gateway """

import os 

from openai import OpenAI

from bot.config import (
    AI_BASE_URL,
    AI_MAX_TOKENS,
    AI_MODEL,
    AI_TIMEOUT
)

_client: OpenAI | None = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ["AI_API_KEY"],
            base_url=AI_BASE_URL,
            timeout=AI_TIMEOUT
        )
    return _client

def ask_llm(prompt: str) -> str:
    """ Send one prompt, then return the raw reply text. """
    response = _get_client().chat.completions.create(
        model=AI_MODEL,
        messages=[{"role":"user", "content":prompt}],
        max_tokens=AI_MAX_TOKENS,
    )
    return response.choices[0].message.content or ""