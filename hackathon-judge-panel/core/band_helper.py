"""
Band Helper — utilities for history analysis and JSON payload parsing.
"""

import json
from typing import Any


def has_responded_since(history_raw: list[dict], target_prefix: str, marker_prefix: str) -> bool:
    """Scan history backwards.

    Returns True if target_prefix is found before marker_prefix.
    If marker_prefix is encountered first, or target_prefix is not found, returns False.
    """
    for m in reversed(history_raw):
        content = m.get("content", "")
        if content.startswith(marker_prefix):
            return False
        if content.startswith(target_prefix):
            return True
    return False


def get_latest_payload(history_raw: list[dict], prefix: str) -> Any | None:
    """Scan history backwards for the latest message starting with prefix.

    Parses the message content (excluding the prefix) as JSON.
    """
    for m in reversed(history_raw):
        content = m.get("content", "")
        if content.startswith(prefix):
            try:
                json_str = content[len(prefix):].strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                return None
    return None


def get_latest_payload_since(history_raw: list[dict], prefix: str, marker_prefix: str) -> Any | None:
    """Scan history backwards for the latest message starting with prefix since marker_prefix."""
    for m in reversed(history_raw):
        content = m.get("content", "")
        if content.startswith(marker_prefix):
            return None
        if content.startswith(prefix):
            try:
                json_str = content[len(prefix):].strip()
                return json.loads(json_str)
            except json.JSONDecodeError:
                return None
    return None
