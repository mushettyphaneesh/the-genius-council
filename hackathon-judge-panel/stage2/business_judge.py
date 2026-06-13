"""
Business Value Judge — Stage 2 agent.

Reads ONLY the compressed knowledge graph (never raw code).
Scores on market size, ROI, enterprise applicability, and time saved.
"""

import json

from core.llm import get_cheap_llm
from core.knowledge_graph import get_knowledge_graph
from core.band_room import post_score


SYSTEM_PROMPT = """\
You are a business value judge on a hackathon judging panel.
Evaluate the submission on these criteria:

1. Market size — How large is the addressable market?
2. ROI potential — How much value does this create for users/enterprises?
3. Enterprise applicability — Could a real company deploy this?
4. Time saved — Does this meaningfully reduce manual work?

Return ONLY valid JSON:
{
  "business_score": <0-100>,
  "reasoning": "<2-3 sentences justifying the score>",
  "confidence": "high" | "medium" | "low",
  "strengths": ["..."],
  "weaknesses": ["..."]
}
"""


async def judge_business(submission_description: str) -> dict:
    """Score the submission on business value."""
    llm = get_cheap_llm()
    kg = get_knowledge_graph()

    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", f"Knowledge graph:\n{kg}\n\n"
                  f"Submission description:\n{submission_description}"),
    ]

    response = llm.invoke(messages)

    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        result = {
            "business_score": 50,
            "reasoning": "Could not parse LLM response.",
            "confidence": "low",
            "strengths": [],
            "weaknesses": ["llm_parse_error"],
        }

    # Post score to band room for head_judge.
    post_score("business_judge", result)
    return result
