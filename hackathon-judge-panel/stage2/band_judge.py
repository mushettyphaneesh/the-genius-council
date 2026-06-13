"""
Band Framework Judge — Stage 2 agent.

Reads ONLY the compressed knowledge graph (never raw code).
Scores on quality and depth of Band framework usage and multi-agent
orchestration patterns.
"""

import json

from core.llm import get_cheap_llm
from core.knowledge_graph import get_knowledge_graph
from core.band_room import post_score


SYSTEM_PROMPT = """\
You are a Band framework usage judge on a hackathon judging panel.
The "Band" framework is the required multi-agent orchestration tool
for this hackathon.  Evaluate the submission on these criteria:

1. Band integration depth — Is Band used meaningfully or just imported?
2. Multi-agent orchestration — Are agents coordinated, not just parallel?
3. Agent specialisation — Do agents have distinct, well-scoped roles?
4. Communication patterns — Do agents share context effectively?

Return ONLY valid JSON:
{
  "band_score": <0-100>,
  "reasoning": "<2-3 sentences justifying the score>",
  "confidence": "high" | "medium" | "low",
  "strengths": ["..."],
  "weaknesses": ["..."]
}

If band_usage is false in the knowledge graph, score should be 0-20
unless there is a valid alternative orchestration approach.
"""


async def judge_band(submission_description: str) -> dict:
    """Score the submission on Band framework usage."""
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
            "band_score": 50,
            "reasoning": "Could not parse LLM response.",
            "confidence": "low",
            "strengths": [],
            "weaknesses": ["llm_parse_error"],
        }

    post_score("band_judge", result)
    return result
