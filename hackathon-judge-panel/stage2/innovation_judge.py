"""
Innovation Judge — Stage 2 agent.

Reads ONLY the compressed knowledge graph (never raw code).
Scores on novelty, creative use of AI/agents, and differentiation.
"""

import json

from core.llm import get_cheap_llm
from core.knowledge_graph import get_knowledge_graph
from core.band_room import post_score


SYSTEM_PROMPT = """\
You are an innovation judge on a hackathon judging panel.
Evaluate the submission on these criteria:

1. Novelty — Is this a genuinely new idea or a rehash of existing tools?
2. Creative AI usage — Does it use AI/agents in a clever, non-trivial way?
3. Technical differentiation — What makes this stand out from competitors?
4. Wow factor — Would this impress a technical audience?

Return ONLY valid JSON:
{
  "innovation_score": <0-100>,
  "reasoning": "<2-3 sentences justifying the score>",
  "confidence": "high" | "medium" | "low",
  "strengths": ["..."],
  "weaknesses": ["..."]
}
"""


async def judge_innovation(submission_description: str) -> dict:
    """Score the submission on innovation."""
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
            "innovation_score": 50,
            "reasoning": "Could not parse LLM response.",
            "confidence": "low",
            "strengths": [],
            "weaknesses": ["llm_parse_error"],
        }

    post_score("innovation_judge", result)
    return result
