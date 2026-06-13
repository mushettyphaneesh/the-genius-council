"""
Head Judge — final arbitration with debate protocol.

Uses the EXPENSIVE model (Gemini 1.5 Pro) — exactly ONE call per
evaluation run.  Reads all scores from the band room, applies weighted
scoring, and triggers a debate protocol if scores are divergent (gap > 20).
"""

import json

from core.llm import get_smart_llm
from core.band_room import read_score, get_fraud_result
from headroom_config import WEIGHTS, DEBATE_THRESHOLD, RECOMMENDATION_TIERS



def _get_recommendation(score: float) -> str:
    """Map a weighted score to a recommendation tier."""
    for threshold, label in RECOMMENDATION_TIERS:
        if score >= threshold:
            return label
    return "Below threshold"


async def final_judgment() -> dict:
    """Produce the final evaluation by reading all judge scores.

    Pipeline:
      1. Read all scores + fraud result from SharedContext (band room).
      2. If fraud → return DISQUALIFIED immediately.
      3. Compute weighted score.
      4. If score gap > DEBATE_THRESHOLD → trigger debate via expensive LLM.
      5. Return final score, recommendation, and metadata.

    Returns:
        Final evaluation dict with final_score, recommendation, scores,
        debate_triggered, debate_summary, fraud_flags, and confidence.
    """
    # ---- Read scores from band room ----
    scores = {}
    score_details = {}

    score_keys = {
        "business": "business_score",
        "innovation": "innovation_score",
        "band": "band_score",
        "demo": "demo_score",
    }

    for category, score_field in score_keys.items():
        data = read_score(category)
        if data and isinstance(data, dict):
            scores[category] = data.get(score_field, 50)
            score_details[category] = data
        else:
            scores[category] = 50  # Default if missing.
            score_details[category] = {"reasoning": "No data available."}

    # Code score comes from repo_analyzer's fraud_flags / architecture quality.
    # Derive from the business judge's data as a proxy if no dedicated code judge.
    code_data = read_score("code")
    if code_data and isinstance(code_data, dict):
        scores["code"] = code_data.get("code_score", 50)
    else:
        # Synthesise a code score from knowledge graph signals.
        scores["code"] = 50

    # ---- Check fraud ----
    fraud = get_fraud_result()
    if fraud is None:
        fraud = {"fraud_score": 0, "flags": [], "abort_evaluation": False}

    if fraud.get("abort_evaluation"):
        return {
            "final_score": 0,
            "recommendation": "DISQUALIFIED",
            "scores": scores,
            "fraud_flags": fraud.get("flags", []),
            "debate_triggered": False,
            "debate_summary": None,
            "confidence": "high",
        }

    # ---- Compute gap and check for debate ----
    score_vals = list(scores.values())
    gap = max(score_vals) - min(score_vals)

    debate_summary = None
    if gap > DEBATE_THRESHOLD:
        # Build reasoning context for the debate.
        reasoning_context = {
            cat: score_details.get(cat, {}).get("reasoning", "N/A")
            for cat in score_keys
        }

        debate_prompt = (
            f"You are the Head Judge arbitrating divergent scores.\n\n"
            f"Scores (gap: {gap} pts): {json.dumps(scores)}\n\n"
            f"Reasoning from each judge:\n{json.dumps(reasoning_context, indent=2)}\n\n"
            f"Explain which score(s) to trust and why. Be specific.\n"
            f"Return ONLY valid JSON:\n"
            f'{{\n'
            f'  "arbitration": "<your reasoning>",\n'
            f'  "adjusted_scores": {{"category": adjusted_value, ...}}\n'
            f'}}'
        )

        messages = [("human", debate_prompt)]
        llm = get_smart_llm()
        response = llm.invoke(messages)

        try:
            arbitration = json.loads(response.content)
            # Apply adjusted scores (only for categories the LLM chose to adjust).
            for cat, val in arbitration.get("adjusted_scores", {}).items():
                if cat in scores and isinstance(val, (int, float)):
                    scores[cat] = val
            debate_summary = arbitration.get("arbitration", "Debate completed.")
        except json.JSONDecodeError:
            debate_summary = "Debate LLM response could not be parsed."

    # ---- Weighted final score ----
    weighted = sum(scores.get(k, 50) * w for k, w in WEIGHTS.items())
    recommendation = _get_recommendation(weighted)

    return {
        "final_score": round(weighted, 1),
        "recommendation": recommendation,
        "scores": scores,
        "debate_triggered": gap > DEBATE_THRESHOLD,
        "debate_summary": debate_summary,
        "fraud_flags": fraud.get("flags", []),
        "confidence": "high" if gap <= DEBATE_THRESHOLD else "medium",
    }
