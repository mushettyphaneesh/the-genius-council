"""
Two-tier LLM routing for the Hackathon Judge Panel.

Cost-optimized provider strategy:

  Cheap tier  → Featherless Premium (unlimited tokens, $25/mo, promo BOA26)
                Used by ALL Stage 1 + Stage 2 agents (8 of 9 agents).
                Falls back to AI/ML API if no Featherless key.

  Smart tier  → AI/ML API Llama-3.3-70B (pay-per-token, $10 credits)
                Used ONLY by Head Judge for debate arbitration (0-1 calls/eval).
                Falls back to Google Gemini if no AIML key.

Why this split works:
  - Featherless charges $0/token (subscription model), so 95% of calls are free.
  - The Head Judge makes at most 1 smart-model call per evaluation (only on debate).
  - At ~2K tokens per arbitration call, $10 in AI/ML credits ≈ 500+ evaluations.

Both tiers are wrapped in HeadroomChatModel for automatic context compression.
"""

import os
from functools import lru_cache

from langchain_openai import ChatOpenAI
from headroom.integrations.langchain import HeadroomChatModel

from headroom_config import (
    FEATHERLESS_BASE_URL,
    FEATHERLESS_MODEL,
    AIML_BASE_URL,
    AIML_CHEAP_MODEL,
    SMART_MODEL_AIML,
    SMART_BASE_URL,
    SMART_MODEL_GOOGLE,
)


@lru_cache(maxsize=1)
def get_cheap_llm() -> HeadroomChatModel:
    """Cheap-tier LLM for all Stage 1 and Stage 2 agents.

    Routing priority:
      1. Featherless Premium → unlimited tokens, $0 per call (preferred).
      2. AI/ML API           → pay-per-token fallback.

    Returns a HeadroomChatModel that automatically compresses context
    before every LLM call, keeping per-agent token usage minimal.
    """
    featherless_key = os.getenv("FEATHERLESS_API_KEY")
    aiml_key = os.getenv("AIMLAPI_API_KEY")

    if featherless_key:
        # Primary: Featherless — unlimited tokens, subscription model
        base = ChatOpenAI(
            base_url=FEATHERLESS_BASE_URL,
            api_key=featherless_key,
            model=FEATHERLESS_MODEL,
        )
    elif aiml_key:
        # Fallback: AI/ML API — pay-per-token
        base = ChatOpenAI(
            base_url=AIML_BASE_URL,
            api_key=aiml_key,
            model=AIML_CHEAP_MODEL,
        )
    else:
        raise RuntimeError(
            "No cheap-model API key found. "
            "Set FEATHERLESS_API_KEY (preferred, unlimited tokens) "
            "or AIMLAPI_API_KEY in your .env file."
        )

    return HeadroomChatModel(base)


@lru_cache(maxsize=1)
def get_smart_llm() -> HeadroomChatModel:
    """Smart-tier LLM — Head Judge ONLY.  At most 1 call per evaluation.

    Routing priority:
      1. AI/ML API  → Llama-3.3-70B-Instruct (preferred, $10 lasts 500+ evals).
      2. Google Gemini 1.5 Pro → fallback if no AIML key.

    Still wrapped in HeadroomChatModel so the already-compressed
    SharedContext payloads stay compact.
    """
    aiml_key = os.getenv("AIMLAPI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")

    if aiml_key:
        # Primary: AI/ML API — only used for Head Judge, very few calls
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
