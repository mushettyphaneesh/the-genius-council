"""
Band Framework Judge — Stage 2 agent.
Subclasses SimpleAdapter to collaborate inside a Band Room.
"""

import json
import re
import time

SESSION_START = time.time()

from band.core.simple_adapter import SimpleAdapter
from band.core.types import PlatformMessage, HistoryProvider
from band.core.protocols import AgentToolsProtocol

from core.llm import get_cheap_llm
from core.band_room import post_score
from core.band_helper import has_responded_since, get_latest_payload_since, get_latest_payload, clean_and_loads_json, PROCESSED_MESSAGE_IDS


def extract_json(text: str, default_val: dict) -> dict:
    """Extract first valid JSON object from LLM response, returning default_val on failure."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    elif not isinstance(text, str):
        text = str(text)

    # Try direct parse first
    try:
        res = clean_and_loads_json(text.strip())
        if isinstance(res, dict):
            return res
    except:
        pass

    # Find first { ... } block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            res = clean_and_loads_json(match.group())
            if isinstance(res, dict):
                return res
        except:
            pass

    print(f"  ⚠ Could not parse JSON from LLM response, using defaults")
    return default_val


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

DEBATE_PROMPT = """\
You are a Band framework judge participating in a hackathon panel debate.
The panel scores have diverged, and the Head Judge has asked you to review the panel's scores and defend or adjust your Band framework score.

Original Band Score: {original_score}
Original Reasoning: {original_reasoning}

Here is the current state of the panel (other judges' scores, reasoning, and Head Judge's remarks):
{debate_context}

Based on this, you can choose to adjust your score (closer to consensus) or keep it the same if you strongly believe in your reasoning.
Return ONLY valid JSON:
{{
  "adjusted_score": <new or same score, 0-100>,
  "justification": "<1-2 sentences explaining why you adjusted or kept the score>"
}}
"""


async def judge_band_logic(submission_description: str, kg_str: str) -> dict:
    """Score the submission on Band framework usage."""
    llm = get_cheap_llm()

    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", f"Knowledge graph:\n{kg_str}\n\n"
                  f"Submission description:\n{submission_description}"),
    ]

    response = llm.invoke(messages)

    result = extract_json(response.content, {
        "band_score": 50,
        "reasoning": "Could not parse LLM response.",
        "confidence": "low",
        "strengths": [],
        "weaknesses": ["llm_parse_error"],
    })

    return result


class BandJudgeAgent(SimpleAdapter[HistoryProvider]):
    """Band Framework Judge Agent Adapter for the Band multi-agent room."""

    async def on_message(
        self,
        msg: PlatformMessage,
        tools: AgentToolsProtocol,
        history: HistoryProvider,
        participants_msg: str | None,
        contacts_msg: str | None,
        *,
        is_session_bootstrap: bool,
        room_id: str,
    ) -> None:
        # Deduplicate — never process the same message twice
        msg_id = getattr(msg, 'id', None)
        agent_name = self.__class__.__name__
        if msg_id:
            if agent_name not in PROCESSED_MESSAGE_IDS:
                PROCESSED_MESSAGE_IDS[agent_name] = set()
            if msg_id in PROCESSED_MESSAGE_IDS[agent_name]:
                print(f"[{agent_name}] Skipping duplicate message {msg_id[:8]}...")
                return
            PROCESSED_MESSAGE_IDS[agent_name].add(msg_id)

        # Skip messages from before this session started
        if hasattr(msg, 'created_at') and msg.created_at:
            try:
                import datetime
                if isinstance(msg.created_at, datetime.datetime):
                    msg_age = time.time() - msg.created_at.timestamp()
                    if msg_age > 30:
                        return  # silently skip old backlog
            except:
                pass

        # All messages we process are since the last submission evaluation
        all_msgs = history.raw + [{"content": msg.content}]

        # 1. Listen for Debate Request (if we haven't responded to it yet)
        if has_responded_since(all_msgs, "[Debate Request]", "[Evaluate Submission]"):
            if not has_responded_since(all_msgs, "[Debate Response Band]", "[Debate Request]"):
                # Run debate logic
                original_score_data = get_latest_payload_since(all_msgs, "[Score Band]", "[Evaluate Submission]") or {}
                original_score = original_score_data.get("band_score", 50)
                original_reasoning = original_score_data.get("reasoning", "N/A")

                # Compile debate context
                debate_request_payload = get_latest_payload_since(all_msgs, "[Debate Request]", "[Evaluate Submission]")
                debate_context = json.dumps(debate_request_payload, indent=2)

                llm = get_cheap_llm()
                messages = [
                    ("system", DEBATE_PROMPT.format(
                        original_score=original_score,
                        original_reasoning=original_reasoning,
                        debate_context=debate_context
                    ))
                ]
                response = llm.invoke(messages)
                debate_res = extract_json(response.content, {
                    "adjusted_score": original_score,
                    "justification": "Held ground due to parsing error."
                })

                # Send debate response
                await tools.send_event(content=f"[Debate Response Band] {json.dumps(debate_res)}", message_type="task")
                return

        # 2. Otherwise, perform initial scoring if we haven't done so yet
        if has_responded_since(all_msgs, "[Score Band]", "[Evaluate Submission]"):
            return

        # Check if Stage 1 results + KG + Fraud exist in the room
        submission = get_latest_payload(all_msgs, "[Evaluate Submission]")
        kg_payload = get_latest_payload_since(all_msgs, "[Knowledge Graph]", "[Evaluate Submission]")
        fraud = get_latest_payload_since(all_msgs, "[Fraud Result]", "[Evaluate Submission]")

        if not submission or not kg_payload or not fraud:
            return

        # Handle early abort for fraud
        if fraud.get("abort_evaluation"):
            result = {
                "band_score": 0,
                "reasoning": "Disqualified due to fraud detector abort.",
                "confidence": "high",
                "strengths": [],
                "weaknesses": ["fraud_abort"],
            }
            await tools.send_event(content=post_score("band_judge", result), message_type="task")
            return

        # Run scoring logic
        kg = kg_payload.get("knowledge_graph", "")
        description = submission.get("description", "")
        result = await judge_band_logic(description, kg)

        # Broadcast score
        await tools.send_event(content=post_score("band_judge", result), message_type="task")


# Singleton instance
band_judge = BandJudgeAgent()
