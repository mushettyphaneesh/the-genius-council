"""
Knowledge Graph Builder Agent — Stage 1 coordination agent.
Listens for Intake and Repo results, compiles them, and publishes the compressed Knowledge Graph.
"""

import json
import time

SESSION_START = time.time()

from band.core.simple_adapter import SimpleAdapter
from band.core.types import PlatformMessage, HistoryProvider
from band.core.protocols import AgentToolsProtocol

from core.band_helper import has_responded_since, get_latest_payload_since, normalize_content, get_latest_payload, PROCESSED_MESSAGE_IDS
from core.knowledge_graph import build_knowledge_graph

KG_BUILT_FOR_MESSAGES = set()


class KGBuilderAgent(SimpleAdapter[HistoryProvider]):
    """Agent that synthesises Stage 1 results into a compressed Knowledge Graph."""

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

        all_msgs = history.raw + [{"content": msg.content}]

        # Check if we have already built the KG for this submission (by github_url)
        submission = get_latest_payload(all_msgs, "[Evaluate Submission]")
        submission_id = None
        if submission:
            submission_id = submission.get("github_url", "")
            if submission_id and submission_id in KG_BUILT_FOR_MESSAGES:
                return

        # Check if Stage 1 results exist in the room for the current evaluation session
        has_intake = get_latest_payload_since(all_msgs, "[Intake Result]", "[Evaluate Submission]") is not None
        has_repo = get_latest_payload_since(all_msgs, "[Repo Result]", "[Evaluate Submission]") is not None
        has_fraud = get_latest_payload_since(all_msgs, "[Fraud Result]", "[Evaluate Submission]") is not None

        # Check if we have already compiled a KG for this evaluation
        has_kg = has_responded_since(all_msgs, "[Knowledge Graph]", "[Evaluate Submission]")

        # Resiliency check: If all Stage 1 results are present but Knowledge Graph is missing,
        # we bypass the backlog age guard to resume/retry building the Knowledge Graph.
        should_bypass_guard = has_intake and has_repo and has_fraud and not has_kg

        if not should_bypass_guard:
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

        # Check if we have already compiled a KG for this evaluation (redundancy check)
        if has_kg:
            return

        # Check if the trigger even exists in this conversation
        # We need to make sure we're in an active evaluation session
        has_trigger = False
        for m in reversed(history.raw):
            if normalize_content(m.get("content", "")).startswith("[Evaluate Submission]"):
                has_trigger = True
                break
        # Also check current message
        content = normalize_content(msg.content)
        if content.startswith("[Evaluate Submission]"):
            has_trigger = True

        if not has_trigger:
            return

        # Fetch the Intake and Repo payloads from the history
        # HistoryProvider raw history contains all messages BEFORE the current one
        # So we append the current message to include it in our search space
        all_msgs = history.raw + [{"content": msg.content}]

        intake = get_latest_payload_since(all_msgs, "[Intake Result]", "[Evaluate Submission]")
        repo_data = get_latest_payload_since(all_msgs, "[Repo Result]", "[Evaluate Submission]")

        # We must wait for BOTH to be published in the room
        if not intake or not repo_data:
            return

        # Compile and compress the KG
        compressed_kg = build_knowledge_graph(repo_data, intake)

        # Broadcast the KG JSON payload to the room
        result_payload = {"knowledge_graph": compressed_kg}
        await tools.send_event(content=f"[Knowledge Graph] {json.dumps(result_payload)}", message_type="task")

        if submission_id:
            KG_BUILT_FOR_MESSAGES.add(submission_id)


# Singleton instance
kg_builder_agent = KGBuilderAgent()
