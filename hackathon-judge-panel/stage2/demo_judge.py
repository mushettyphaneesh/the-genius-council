"""
Demo / Presentation Judge — Stage 2 agent.

Unlike other Stage 2 judges, this one reads the video transcript and
slide content instead of the knowledge graph.  Scores on demo clarity,
presentation quality, and evidence of a working prototype.

Compression note:
  HeadroomChatModel automatically compresses context before every
  LLM call, so we don't need manual compress() calls here.
  This is especially important for demo_judge since video transcripts
  can be very long.
"""

import json

from core.llm import get_cheap_llm
from core.knowledge_graph import get_knowledge_graph
from core.band_room import post_score


SYSTEM_PROMPT = """\
You are a demo and presentation judge on a hackathon judging panel.
Evaluate the submission's demo/presentation on these criteria:

1. Clarity — Is the problem and solution communicated clearly?
2. Demo quality — Does the demo show a working prototype, not just slides?
3. Persuasiveness — Would this convince a non-technical stakeholder?
4. Completeness — Does the demo cover the end-to-end user journey?

Return ONLY valid JSON:
{
  "demo_score": <0-100>,
  "reasoning": "<2-3 sentences justifying the score>",
  "confidence": "high" | "medium" | "low",
  "strengths": ["..."],
  "weaknesses": ["..."]
}

If no video transcript or slides are provided, score based on whatever
context is available and set confidence to "low".
"""


async def judge_demo(video_transcript: str) -> dict:
    """Score the submission's demo / presentation.

    Args:
        video_transcript: Transcript of the demo video, or empty string.

    Returns:
        Dict with demo_score, reasoning, confidence, strengths, weaknesses.
    """
    llm = get_cheap_llm()
    kg = get_knowledge_graph()

    # Build context — transcript is the primary signal here.
    user_content = f"Knowledge graph (for background):\n{kg}\n\n"

    if video_transcript and video_transcript.strip():
        user_content += f"Video transcript:\n{video_transcript}"
    else:
        user_content += (
            "No video transcript or slides were provided. "
            "Score based on available context and set confidence to 'low'."
        )

    # HeadroomChatModel auto-compresses — important here since
    # video transcripts can be very long.
    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", user_content),
    ]

    response = llm.invoke(messages)

    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {
            "demo_score": 50,
            "reasoning": "Could not parse LLM response.",
            "confidence": "low",
            "strengths": [],
            "weaknesses": ["llm_parse_error"],
        }

    post_score("demo_judge", result)
    return result
