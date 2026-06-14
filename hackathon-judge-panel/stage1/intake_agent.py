"""
Intake Agent — extracts structured submission metadata.
Subclasses SimpleAdapter to collaborate inside a Band Room.
"""

import json

from band.core.simple_adapter import SimpleAdapter
from band.core.types import PlatformMessage, HistoryProvider
from band.core.protocols import AgentToolsProtocol

from core.llm import get_cheap_llm
from core.band_helper import has_responded_since, get_latest_payload, clean_and_loads_json, normalize_content


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


async def extract_intake_logic(submission: dict) -> dict:
    """Extract or infer intake fields from the submission."""
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
        result = clean_and_loads_json(response.content)
    except Exception:
        result = {
            "problem": submission.get("description", "Unknown"),
            "solution": "Could not parse",
            "track": "general",
            "team_size": None,
            "key_features": [],
        }

    return result


class IntakeAgent(SimpleAdapter[HistoryProvider]):
    """Intake Agent Adapter for the Band multi-agent room."""

    async def on_message(
        self,
        msg: PlatformMessage,
        tools: AgentToolsProtocol,
        history: HistoryProvider,
        participants_msg: str | None,
        contacts_msg: str | None,
        *,
        is_session_bootstrap: bool,
        room_id: str,
    ) -> None:
        # Normalize content: strip @[[uuid]] mentions + auto-detect raw JSON submissions
        content = normalize_content(msg.content)

        # === DEBUG LOGGING — remove after diagnosing ===
        print(f"[IntakeAgent] ✅ on_message triggered!")
        print(f"[IntakeAgent] Raw: {msg.content[:100]}")
        print(f"[IntakeAgent] Normalized: {content[:100]}")
        print(f"[IntakeAgent] Match: {content.startswith('[Evaluate Submission]')}")
        # === END DEBUG LOGGING ===

        # Listen for evaluate submission trigger
        if not content.startswith("[Evaluate Submission]"):
            return

        # Check for duplicate response
        if has_responded_since(history.raw, "[Intake Result]", "[Evaluate Submission]"):
            return

        # Fetch payload from current message (since history doesn't include current msg)
        submission = get_latest_payload(history.raw + [{"content": msg.content}], "[Evaluate Submission]")
        if not submission:
            return

        # Run extraction logic
        result = await extract_intake_logic(submission)

        # Broadcast the result back to the room
        await tools.send_event(content=f"[Intake Result] {json.dumps(result)}", message_type="task")


# Singleton instance
intake_agent = IntakeAgent()
