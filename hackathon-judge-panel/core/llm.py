"""
Two-tier LLM routing for the Hackathon Judge Panel.

- get_cheap_llm()  → AI/ML API  Qwen 2.5-72B — used by ALL Stage 1 and
                     Stage 2 agents.  Wrapped in HeadroomChatModel for
                     automatic context compression.
- get_smart_llm()  → AI/ML API  Llama-3.3-70B (primary) or Google Gemini
                     1.5 Pro (fallback) — used ONLY by the Head Judge.
                     Single call per evaluation run.

Routing priority for the smart model:
  1. If AIMLAPI_API_KEY is set → use AI/ML API (keeps the entire pipeline
     on a single provider, qualifying for the hackathon sponsor reward).
  2. Else if GOOGLE_API_KEY is set → use Google Gemini 1.5 Pro.
  3. Else → raise a clear error.

Both functions use lazy initialization — the LLM instance is created on
first call (after .env is loaded), then cached for reuse.
"""

import os
from functools import lru_cache

from langchain_openai import ChatOpenAI
from headroom.integrations.langchain import HeadroomChatModel

from headroom_config import (
    CHEAP_MODEL,
    CHEAP_BASE_URL,
    SMART_MODEL_AIML,
    SMART_BASE_URL,
    SMART_MODEL_GOOGLE,
)


@lru_cache(maxsize=1)
def get_cheap_llm() -> HeadroomChatModel:
    """AI/ML API Qwen for all Stage 1 and Stage 2 agents.

    Returns a HeadroomChatModel that automatically compresses context
    before every LLM call, keeping per-agent token usage minimal.

    Lazily initialised on first call (cached via lru_cache).
    """
    base = ChatOpenAI(
        base_url=CHEAP_BASE_URL,
        api_key=os.getenv("AIMLAPI_API_KEY") or os.getenv("FEATHERLESS_API_KEY"),
        model=CHEAP_MODEL,
    )
    return HeadroomChatModel(base)


@lru_cache(maxsize=1)
def get_smart_llm() -> HeadroomChatModel:
    """Smart model — Head Judge ONLY.  One call per evaluation.

    Routing priority:
      1. AI/ML API  → Llama-3.3-70B-Instruct (preferred, keeps entire
         pipeline on a single provider for the hackathon sponsor reward).
      2. Google Gemini 1.5 Pro → fallback if no AIMLAPI key is configured.

    Still wrapped in HeadroomChatModel so the already-compressed
    SharedContext payloads stay compact.

    Lazily initialised on first call (cached via lru_cache).
    """
    aiml_key = os.getenv("AIMLAPI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")

    if aiml_key:
        # Primary: AI/ML API — keeps entire pipeline on one provider
        base = ChatOpenAI(
            base_url=SMART_BASE_URL,
            api_key=aiml_key,
            model=SMART_MODEL_AIML,
        )
    elif google_key:
        # Fallback: Google Gemini
        from langchain_google_genai import ChatGoogleGenerativeAI

        base = ChatGoogleGenerativeAI(
            model=SMART_MODEL_GOOGLE,
            google_api_key=google_key,
        )
    else:
        raise RuntimeError(
            "No smart-model API key found. "
            "Set AIMLAPI_API_KEY (preferred) or GOOGLE_API_KEY in your .env file."
        )

    return HeadroomChatModel(base)
