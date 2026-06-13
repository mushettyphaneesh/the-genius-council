"""
Knowledge Graph Builder Agent — Stage 1 coordination agent.
Listens for Intake and Repo results, compiles them, and publishes the compressed Knowledge Graph.
"""

import json

from band.core.simple_adapter import SimpleAdapter
from band.core.types import PlatformMessage, HistoryProvider
from band.core.protocols import AgentToolsProtocol

from core.band_helper import has_responded_since, get_latest_payload_since
from core.knowledge_graph import build_knowledge_graph


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
        # Check if we have already compiled a KG for this evaluation
        if has_responded_since(history.raw, "[Knowledge Graph]", "[Evaluate Submission]"):
            return

        # Check if the trigger even exists in this conversation
        # We need to make sure we're in an active evaluation session
        has_trigger = False
        for m in reversed(history.raw):
            if m.get("content", "").startswith("[Evaluate Submission]"):
                has_trigger = True
                break
        # Also check current message
        if msg.content.startswith("[Evaluate Submission]"):
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
        await tools.send_message(content=f"[Knowledge Graph] {json.dumps(result_payload)}")


# Singleton instance
kg_builder_agent = KGBuilderAgent()
