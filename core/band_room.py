"""
Band Room — helper functions to format messages for the Band Room.
"""

import json


def post_score(agent_name: str, score_dict: dict) -> str:
    """Format a judge's score dictionary as a Band message.

    Args:
        agent_name: e.g. "business_judge", "innovation_judge"
        score_dict: The JSON-serialisable score payload from the judge.

    Returns:
        Formatted string matching the room's event prefix.
    """
    category = agent_name.replace("_judge", "")
    # Standardize category capitalization (e.g. "business" -> "Business")
    return f"[Score {category.capitalize()}] {json.dumps(score_dict)}"


def post_fraud_result(fraud_dict: dict) -> str:
    """Format fraud detection results as a Band message."""
    return f"[Fraud Result] {json.dumps(fraud_dict)}"
