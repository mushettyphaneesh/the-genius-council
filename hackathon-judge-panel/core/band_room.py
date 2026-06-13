"""
Band Room — convenience wrapper around SharedContextStore for score exchange.

Provides a domain-specific API for agents to post and read scores
without needing to know the key naming convention.
"""

from core.shared_context import ctx


def post_score(agent_name: str, score_dict: dict) -> None:
    """Post a judge's score to the shared band room.

    Args:
        agent_name: e.g. "business_judge", "innovation_judge"
        score_dict: The JSON-serialisable score payload from the judge.
    """
    key = f"score_{agent_name.replace('_judge', '')}"
    ctx.put(key, score_dict, agent=agent_name)


def read_score(category: str) -> dict | None:
    """Read a single category's score from the band room.

    Args:
        category: e.g. "business", "innovation", "band", "demo", "code"

    Returns:
        The score dict posted by the corresponding judge, or None.
    """
    return ctx.get(f"score_{category}")


def read_all_scores() -> dict:
    """Read all judge scores from the band room.

    Returns:
        Dict mapping category name → score dict.
    """
    categories = ["business", "innovation", "band", "demo", "code"]
    scores = {}
    for cat in categories:
        data = ctx.get(f"score_{cat}")
        if data is not None:
            scores[cat] = data
    return scores


def post_fraud_result(fraud_dict: dict) -> None:
    """Store fraud detection results in the band room."""
    ctx.put("fraud_result", fraud_dict, agent="fraud_detector")


def get_fraud_result() -> dict | None:
    """Retrieve fraud detection results from the band room."""
    return ctx.get("fraud_result")
