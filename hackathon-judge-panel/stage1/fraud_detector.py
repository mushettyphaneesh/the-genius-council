"""
Fraud Detector — runs in parallel with repo_analyzer.

If fraud_score > FRAUD_ABORT_THRESHOLD (default 60), sets
`abort_evaluation = True` which causes main.py to skip all Stage 2
agents — saving their entire token budget.

Compression note:
  HeadroomChatModel automatically compresses context before every
  LLM call, so we don't need manual compress() calls here.
"""

import json

from core.llm import get_cheap_llm
from core.band_room import post_fraud_result
from headroom_config import FRAUD_README_MAX_CHARS, FRAUD_ABORT_THRESHOLD


async def detect_fraud(
    readme: str,
    file_tree: list,
    commit_dates: list,
) -> dict:
    """Run fraud heuristics via cheap LLM.

    Runs in parallel with `repo_analyzer`.  If the fraud score is high
    enough, the main pipeline aborts before Stage 2 — saving all
    downstream tokens.

    Args:
        readme: Raw README content (truncated to FRAUD_README_MAX_CHARS).
        file_tree: List of file paths in the repo.
        commit_dates: ISO date strings of the last N commits.

    Returns:
        Dict with keys: fraud_score (0-100), flags (list), abort_evaluation (bool).
    """
    llm = get_cheap_llm()
    prompt = (
        f"Check this hackathon submission for fraud.\n\n"
        f"README (truncated):\n{readme[:FRAUD_README_MAX_CHARS]}\n\n"
        f"File tree:\n{json.dumps(file_tree)}\n\n"
        f"Commit dates:\n{json.dumps(commit_dates)}\n\n"
        f"Return ONLY valid JSON:\n"
        f'{{\n'
        f'  "fraud_score": <0-100>,\n'
        f'  "flags": ["flag1", ...],\n'
        f'  "abort_evaluation": true/false\n'
        f'}}\n\n'
        f"Set abort_evaluation = true if fraud_score > {FRAUD_ABORT_THRESHOLD}.\n"
        f"\nFraud checks:\n"
        f"- All commits on a single day → 'single-day dump'\n"
        f"- No requirements.txt or env file in tree → 'not runnable'\n"
        f"- README mentions Band but no Band-related files → 'Band faked'\n"
        f"- README claims N agents but tree has fewer agent files → 'agent count mismatch'\n"
        f"- Very few files overall → 'minimal repo'\n"
    )

    # HeadroomChatModel auto-compresses before the LLM call.
    messages = [("human", prompt)]
    response = llm.invoke(messages)

    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {
            "fraud_score": 0,
            "flags": ["llm_parse_error"],
            "abort_evaluation": False,
        }

    # Ensure abort_evaluation is set correctly based on threshold.
    result["abort_evaluation"] = result.get("fraud_score", 0) > FRAUD_ABORT_THRESHOLD

    # Post to band room so head_judge can read it.
    post_fraud_result(result)

    return result
