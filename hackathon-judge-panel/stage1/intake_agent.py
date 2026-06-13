"""
Intake Agent — extracts structured submission metadata.

Parses the submission dict (and optionally the README) to produce a
normalised intake record with problem, solution, and track fields.
Uses the cheap LLM only when the submission lacks structured fields.

Compression note:
  HeadroomChatModel automatically compresses context before every
  LLM call, so we don't need manual compress() calls here.
"""

import json

from core.llm import get_cheap_llm


SYSTEM_PROMPT = """\
You are a hackathon submission intake agent.  Extract structured metadata
from the provided submission information and return ONLY valid JSON with
these keys:

- problem: What problem does the submission solve? (1-2 sentences)
- solution: How does it solve it? (1-2 sentences)
- track: Which hackathon track does it target? (string or "general")
- team_size: Number of team members if mentioned (int or null)
- key_features: Up to 5 bullet points (list of strings)
"""


async def extract_intake(submission: dict) -> dict:
    """Extract or infer intake fields from the submission.

    If the submission already has structured `problem`, `solution`, and
    `track` keys, we skip the LLM call entirely — zero tokens spent.

    Args:
        submission: Raw submission dict from the hackathon platform.

    Returns:
        Dict with keys: problem, solution, track, team_size, key_features.
    """
    # Fast path: structured data already present — no LLM needed.
    if all(k in submission for k in ("problem", "solution", "track")):
        return {
            "problem": submission["problem"],
            "solution": submission["solution"],
            "track": submission["track"],
            "team_size": submission.get("team_size"),
            "key_features": submission.get("key_features", []),
        }

    # Slow path: parse from description / README via cheap LLM.
    # HeadroomChatModel auto-compresses before the LLM call.
    llm = get_cheap_llm()
    raw_text = submission.get("description", "")
    if submission.get("readme"):
        raw_text += f"\n\n=== README ===\n{submission['readme']}"

    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", raw_text),
    ]

    response = llm.invoke(messages)

    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        # Fallback — return what we can.
        result = {
            "problem": submission.get("description", "Unknown"),
            "solution": "Could not parse",
            "track": "general",
            "team_size": None,
            "key_features": [],
        }

    return result
