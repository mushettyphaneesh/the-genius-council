"""
Two-tier LLM routing for the Hackathon Judge Panel.

- get_cheap_llm()  → Featherless Qwen 2.5-72B — used by ALL Stage 1 and
                     Stage 2 agents.  Wrapped in HeadroomChatModel for
                     automatic context compression.
- get_smart_llm()  → Google Gemini 1.5 Pro — used ONLY by the Head Judge.
                     Single call per evaluation run.

Both functions use lazy initialization — the LLM instance is created on
first call (after .env is loaded), then cached for reuse.
"""

import os
from functools import lru_cache

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from headroom.integrations.langchain import HeadroomChatModel

from headroom_config import CHEAP_MODEL, CHEAP_BASE_URL, SMART_MODEL


@lru_cache(maxsize=1)
def get_cheap_llm() -> HeadroomChatModel:
    """Featherless Qwen for all Stage 1 and Stage 2 agents.

    Returns a HeadroomChatModel that automatically compresses context
    before every LLM call, keeping per-agent token usage minimal.

    Lazily initialised on first call (cached via lru_cache).
    """
    base = ChatOpenAI(
        base_url=CHEAP_BASE_URL,
        api_key=os.getenv("FEATHERLESS_API_KEY"),
        model=CHEAP_MODEL,
    )
    return HeadroomChatModel(base)


@lru_cache(maxsize=1)
def get_smart_llm() -> HeadroomChatModel:
    """Expensive model — Head Judge ONLY.  One call per evaluation.

    Uses Gemini 1.5 Pro for the final arbitration / debate protocol.
    Still wrapped in HeadroomChatModel so the already-compressed
    SharedContext payloads stay compact.

    Lazily initialised on first call (cached via lru_cache).
    """
    base = ChatGoogleGenerativeAI(
        model=SMART_MODEL,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
    return HeadroomChatModel(base)
