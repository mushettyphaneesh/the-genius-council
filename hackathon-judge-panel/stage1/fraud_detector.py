"""
Fraud Detector — runs in parallel with repo_analyzer.
Subclasses SimpleAdapter to collaborate inside a Band Room.
"""

import json
import re
import time

SESSION_START = time.time()

from band.core.simple_adapter import SimpleAdapter
from band.core.types import PlatformMessage, HistoryProvider
from band.core.protocols import AgentToolsProtocol

from core.llm import get_cheap_llm
from core.band_room import post_fraud_result
from core.band_helper import has_responded_since, get_latest_payload, clean_and_loads_json, normalize_content
from headroom_config import FRAUD_README_MAX_CHARS, FRAUD_ABORT_THRESHOLD


def extract_json(text: str) -> dict:
    """Extract first valid JSON object from LLM response."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    elif not isinstance(text, str):
        text = str(text)

    # Try direct parse first
    try:
        res = clean_and_loads_json(text.strip())
        if isinstance(res, dict):
            return res
    except:
        pass

    # Find first { ... } block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            res = clean_and_loads_json(match.group())
            if isinstance(res, dict):
                return res
        except:
            pass

    # Last resort — return safe default
    print(f"  ⚠ Could not parse JSON from LLM response, using defaults")
    return {
        "fraud_score": 0,
        "flags": ["llm_parse_error"],
        "abort_evaluation": False,
    }


async def detect_fraud_logic(submission: dict) -> dict:
    """Run fraud heuristics via cheap LLM."""
    llm = get_cheap_llm()
    readme = submission.get("readme", "")
    description = submission.get("description", "")

    prompt = (
        f"Check this hackathon submission for early signs of fraud, template copy-paste, or faked features.\n\n"
        f"README (truncated):\n{readme[:FRAUD_README_MAX_CHARS]}\n\n"
        f"Description:\n{description}\n\n"
        f"Return ONLY valid JSON:\n"
        f'{{\n'
        f'  "fraud_score": <0-100>,\n'
        f'  "flags": ["flag1", ...],\n'
        f'  "abort_evaluation": true/false\n'
        f'}}\n\n'
        f"Set abort_evaluation = true if fraud_score > {FRAUD_ABORT_THRESHOLD}.\n"
        f"\nFraud checks:\n"
        f"- Description looks completely generated/faked\n"
        f"- README has no instructions/details\n"
        f"- Claims Band usage but description mentions alternative or no agent orchestration\n"
    )

    messages = [("human", prompt)]
    response = llm.invoke(messages)
    result = extract_json(response.content)

    result["abort_evaluation"] = result.get("fraud_score", 0) > FRAUD_ABORT_THRESHOLD
    return result


class FraudDetectorAgent(SimpleAdapter[HistoryProvider]):
    """Fraud Detector Agent Adapter for the Band multi-agent room."""

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
        # Skip messages from before this session started
        if hasattr(msg, 'created_at') and msg.created_at:
            try:
                import datetime
                if isinstance(msg.created_at, datetime.datetime):
                    msg_age = time.time() - msg.created_at.timestamp()
                    if msg_age > 30:
                        return  # silently skip old backlog
            except:
                pass

        # Normalize content: strip @[[uuid]] mentions + auto-detect raw JSON submissions
        content = normalize_content(msg.content)

        # Listen for evaluate submission trigger
        if not content.startswith("[Evaluate Submission]"):
            return

        # Check for duplicate response
        if has_responded_since(history.raw, "[Fraud Result]", "[Evaluate Submission]"):
            return

        submission = get_latest_payload(history.raw + [{"content": msg.content}], "[Evaluate Submission]")
        if not submission:
            return

        # Execute fraud logic
        result = await detect_fraud_logic(submission)

        # Broadcast the result as [Fraud Result] json
        await tools.send_event(content=post_fraud_result(result), message_type="task")


# Singleton instance
fraud_detector = FraudDetectorAgent()
