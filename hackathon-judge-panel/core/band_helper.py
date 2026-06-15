"""
Band Helper — utilities for history analysis and JSON payload parsing.
"""

import json
import re
from typing import Any


def strip_band_mentions(content: str) -> str:
    """Strip Band @[[uuid]] mention patterns from the beginning of message content.

    Band prepends @[[agent-uuid]] to messages when agents are mentioned.
    This must be stripped before checking message prefixes like [Evaluate Submission].
    """
    return re.sub(r'^(\s*@\[\[[a-f0-9-]+\]\]\s*)+', '', content).strip()


def normalize_content(content: str) -> str:
    """Strip Band mentions and auto-detect raw JSON submissions.

    Band requires @mentions on every user message, so content always starts
    with @[[uuid]]... The user cannot prepend [Evaluate Submission] before
    the mentions. This function:
    1. Strips @[[uuid]] mention patterns
    2. If the remaining content is raw JSON containing 'github_url',
       prepends [Evaluate Submission] so all downstream prefix checks work.
    """
    stripped = strip_band_mentions(content)
    # Auto-detect raw JSON submissions (user can't type the prefix before @mentions)
    if stripped.startswith("{") and "github_url" in stripped:
        return f"[Evaluate Submission] {stripped}"
    return stripped


def extract_all_json_objects(s: str) -> list[dict]:
    """Find and parse all individual JSON objects in the string."""
    results = []
    brace_count = 0
    start_idx = -1
    for i, char in enumerate(s):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            if brace_count > 0:
                brace_count -= 1
                if brace_count == 0 and start_idx != -1:
                    candidate = s[start_idx:i+1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            results.append(obj)
                    except Exception:
                        pass
    return results


def merge_json_objects(objects: list[dict]) -> dict:
    """Merge multiple parsed JSON objects into a single dictionary."""
    merged = {
        "reasoning": "",
        "strengths": [],
        "weaknesses": [],
        "confidence": "medium"
    }

    scores = []
    reasonings = []

    for obj in objects:
        for k, v in obj.items():
            # If the value is a score (numeric)
            if isinstance(v, (int, float)) and any(x in k.lower() for x in ["score", "size", "potential", "applicability", "time", "novelty", "usage", "differentiation", "wow", "clarity", "quality", "persuasiveness", "completeness"]):
                scores.append(v)
            elif k in ["business_score", "innovation_score", "band_score", "demo_score", "score"]:
                if isinstance(v, (int, float)):
                    scores.append(v)

            # Reasoning
            if k == "reasoning" and isinstance(v, str):
                reasonings.append(v)

            # Strengths
            if k == "strengths" and isinstance(v, list):
                merged["strengths"].extend(v)

            # Weaknesses
            if k == "weaknesses" and isinstance(v, list):
                merged["weaknesses"].extend(v)

            # Confidence
            if k == "confidence" and isinstance(v, str):
                merged["confidence"] = v

    # Average any scores we found
    if scores:
        avg_score = round(sum(scores) / len(scores), 1)
        # Populate all variants so the caller will find the one they expect
        merged["score"] = avg_score
        merged["business_score"] = avg_score
        merged["innovation_score"] = avg_score
        merged["band_score"] = avg_score
        merged["demo_score"] = avg_score
    else:
        merged["score"] = 50
        merged["business_score"] = 50
        merged["innovation_score"] = 50
        merged["band_score"] = 50
        merged["demo_score"] = 50

    if reasonings:
        merged["reasoning"] = " ".join(reasonings)
    else:
        # Fallback to concatenate all string values that look like reasoning
        all_strs = []
        for obj in objects:
            for k, v in obj.items():
                if k != "confidence" and isinstance(v, str) and len(v) > 20:
                    all_strs.append(v)
        if all_strs:
            merged["reasoning"] = " ".join(all_strs)

    return merged


def standardize_score_dict(obj: dict) -> dict:
    """Standardize score keys in a dictionary."""
    score_val = None
    for k in ["business_score", "innovation_score", "band_score", "demo_score", "score"]:
        if k in obj and isinstance(obj[k], (int, float)):
            score_val = obj[k]
            break

    if score_val is None:
        # Look for any numeric value that might be the score
        for k, v in obj.items():
            if isinstance(v, (int, float)) and "score" in k.lower():
                score_val = v
                break

    if score_val is not None:
        obj["score"] = score_val
        obj["business_score"] = score_val
        obj["innovation_score"] = score_val
        obj["band_score"] = score_val
        obj["demo_score"] = score_val

    return obj


def clean_and_loads_json(content: str | bytes) -> Any:
    """Clean markdown backticks, outer text, and parse as JSON."""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    elif not isinstance(content, str):
        content = str(content)

    s = content.strip()

    # Strip markdown code blocks if present
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()

    # Try standard single JSON load first
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return standardize_score_dict(obj)
        return obj
    except Exception:
        pass

    # Try extracting all individual JSON objects and merging them
    objects = extract_all_json_objects(s)
    if objects:
        if len(objects) == 1:
            return standardize_score_dict(objects[0])
        return merge_json_objects(objects)

    # Fallback to single outer brace extraction
    first_brace = s.find("{")
    last_brace = s.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        s = s[first_brace:last_brace + 1]
    else:
        first_bracket = s.find("[")
        last_bracket = s.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            s = s[first_bracket:last_bracket + 1]

    obj = json.loads(s)
    if isinstance(obj, dict):
        return standardize_score_dict(obj)
    return obj


def has_responded_since(history_raw: list[dict], target_prefix: str, marker_prefix: str) -> bool:
    """Scan history backwards.

    Returns True if target_prefix is found before marker_prefix.
    If marker_prefix is encountered first, or target_prefix is not found, returns False.
    """
    for m in reversed(history_raw):
        content = normalize_content(m.get("content", ""))
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
        content = normalize_content(m.get("content", ""))
        if content.startswith(prefix):
            try:
                json_str = content[len(prefix):].strip()
                return clean_and_loads_json(json_str)
            except Exception:
                return None
    return None


def get_latest_payload_since(history_raw: list[dict], prefix: str, marker_prefix: str) -> Any | None:
    """Scan history backwards for the latest message starting with prefix since marker_prefix."""
    for m in reversed(history_raw):
        content = normalize_content(m.get("content", ""))
        if content.startswith(marker_prefix):
            return None
        if content.startswith(prefix):
            try:
                json_str = content[len(prefix):].strip()
                return clean_and_loads_json(json_str)
            except Exception:
                return None
    return None
