"""
Head Judge — final arbitration with debate protocol.
Subclasses SimpleAdapter to collaborate inside a Band Room.
"""

import json

from band.core.simple_adapter import SimpleAdapter
from band.core.types import PlatformMessage, HistoryProvider
from band.core.protocols import AgentToolsProtocol

from core.llm import get_smart_llm
from core.band_helper import has_responded_since, get_latest_payload_since, clean_and_loads_json
from headroom_config import WEIGHTS, DEBATE_THRESHOLD, RECOMMENDATION_TIERS


def _get_recommendation(score: float) -> str:
    """Map a weighted score to a recommendation tier."""
    for threshold, label in RECOMMENDATION_TIERS:
        if score >= threshold:
            return label
    return "Below threshold"


class HeadJudgeAgent(SimpleAdapter[HistoryProvider]):
    """Head Judge Agent Adapter for the Band multi-agent room."""

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
        all_msgs = history.raw + [{"content": msg.content}]

        # Skip if Final Judgment is already rendered
        if has_responded_since(all_msgs, "[Final Judgment]", "[Evaluate Submission]"):
            return

        # Check for early abort due to fraud
        fraud = get_latest_payload_since(all_msgs, "[Fraud Result]", "[Evaluate Submission]")
        if fraud and fraud.get("abort_evaluation"):
            result = {
                "final_score": 0,
                "recommendation": "DISQUALIFIED",
                "scores": {},
                "debate_triggered": False,
                "debate_summary": "Evaluation aborted by fraud detector.",
                "fraud_flags": fraud.get("flags", []),
                "confidence": "high",
            }
            await tools.send_event(content=f"[Final Judgment] {json.dumps(result)}", message_type="task")
            return

        # Check if all Stage 2 scores are present in the room
        biz_score = get_latest_payload_since(all_msgs, "[Score Business]", "[Evaluate Submission]")
        innov_score = get_latest_payload_since(all_msgs, "[Score Innovation]", "[Evaluate Submission]")
        band_score_data = get_latest_payload_since(all_msgs, "[Score Band]", "[Evaluate Submission]")
        demo_score_data = get_latest_payload_since(all_msgs, "[Score Demo]", "[Evaluate Submission]")

        # We must wait for all 4 Stage 2 scores to be posted
        if not biz_score or not innov_score or not band_score_data or not demo_score_data:
            return

        # Gather base scores
        scores = {
            "business": biz_score.get("business_score", 50),
            "innovation": innov_score.get("innovation_score", 50),
            "band": band_score_data.get("band_score", 50),
            "demo": demo_score_data.get("demo_score", 50),
            "code": 50,  # default code score placeholder
        }

        # Check if repo flags can influence code score
        repo_data = get_latest_payload_since(all_msgs, "[Repo Result]", "[Evaluate Submission]")
        if repo_data:
            scores["code"] = 90 if not repo_data.get("fraud_flags") else 50
            if repo_data.get("has_tests"):
                scores["code"] += 10
            scores["code"] = min(scores["code"], 100)

        # ---- Case A: Debate Request not sent yet ----
        if not has_responded_since(all_msgs, "[Debate Request]", "[Evaluate Submission]"):
            score_vals = [scores["business"], scores["innovation"], scores["band"], scores["demo"]]
            gap = max(score_vals) - min(score_vals)

            if gap <= DEBATE_THRESHOLD:
                # No debate needed — calculate final score and render judgment
                weighted = sum(scores.get(k, 50) * w for k, w in WEIGHTS.items())
                recommendation = _get_recommendation(weighted)

                result = {
                    "final_score": round(weighted, 1),
                    "recommendation": recommendation,
                    "scores": scores,
                    "debate_triggered": False,
                    "debate_summary": None,
                    "fraud_flags": fraud.get("flags", []) if fraud else [],
                    "confidence": "high",
                }
                await tools.send_event(content=f"[Final Judgment] {json.dumps(result)}", message_type="task")
                return
            else:
                # Divergence found! Send Debate Request message to trigger judges
                reasoning_context = {
                    "business": biz_score.get("reasoning", "N/A"),
                    "innovation": innov_score.get("reasoning", "N/A"),
                    "band": band_score_data.get("reasoning", "N/A"),
                    "demo": demo_score_data.get("reasoning", "N/A"),
                }
                debate_request = {
                    "scores": scores,
                    "reasoning": reasoning_context,
                    "msg": "Judges, our scores diverge significantly! Please review and adjust."
                }
                await tools.send_event(content=f"[Debate Request] {json.dumps(debate_request)}", message_type="task")
                return

        # ---- Case B: Debate Request sent, checking for responses ----
        # Wait for all debate responses to be posted
        biz_debate = get_latest_payload_since(all_msgs, "[Debate Response Business]", "[Debate Request]")
        innov_debate = get_latest_payload_since(all_msgs, "[Debate Response Innovation]", "[Debate Request]")
        band_debate = get_latest_payload_since(all_msgs, "[Debate Response Band]", "[Debate Request]")
        demo_debate = get_latest_payload_since(all_msgs, "[Debate Response Demo]", "[Debate Request]")

        if not biz_debate or not innov_debate or not band_debate or not demo_debate:
            return

        # Compile debate responses
        debate_responses = {
            "business": biz_debate,
            "innovation": innov_debate,
            "band": band_debate,
            "demo": demo_debate,
        }

        # Call expensive model for final arbitration over debate
        llm = get_smart_llm()
        arbitration_prompt = (
            f"You are the Head Judge arbitrating divergent scores after a multi-agent debate.\n\n"
            f"Original scores: {json.dumps(scores)}\n\n"
            f"Debate responses from each judge:\n{json.dumps(debate_responses, indent=2)}\n\n"
            f"Explain which score(s) to trust and why. Be specific.\n"
            f"Return ONLY valid JSON:\n"
            f'{{\n'
            f'  "arbitration": "<your reasoning>",\n'
            f'  "adjusted_scores": {{"category": adjusted_value, ...}}\n'
            f'}}'
        )

        response = llm.invoke([("human", arbitration_prompt)])

        try:
            arbitration = clean_and_loads_json(response.content)
            # Apply adjusted scores
            for cat, val in arbitration.get("adjusted_scores", {}).items():
                if cat in scores and isinstance(val, (int, float)):
                    scores[cat] = val
            debate_summary = arbitration.get("arbitration", "Debate completed.")
        except json.JSONDecodeError:
            debate_summary = "Debate LLM response could not be parsed."

        # Compute final weighted score
        weighted = sum(scores.get(k, 50) * w for k, w in WEIGHTS.items())
        recommendation = _get_recommendation(weighted)

        result = {
            "final_score": round(weighted, 1),
            "recommendation": recommendation,
            "scores": scores,
            "debate_triggered": True,
            "debate_summary": debate_summary,
            "fraud_flags": fraud.get("flags", []) if fraud else [],
            "confidence": "medium",
        }
        await tools.send_event(content=f"[Final Judgment] {json.dumps(result)}", message_type="task")


# Singleton instance
head_judge = HeadJudgeAgent()
