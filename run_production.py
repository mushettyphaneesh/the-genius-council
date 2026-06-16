"""
Production Runner for the Hackathon Judge Panel.

Concurrently starts and runs all 9 agents, connecting them to the real 
Band Cloud platform (app.band.ai). Each agent requires its own Agent ID 
and API Key configured in your .env file.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from band import Agent
from band.runtime.tools import AgentTools

# === DEBUG LOGGING PATCH — remove after diagnosing ===
_original_send_event = AgentTools.send_event
_original_send_message = AgentTools.send_message

async def _debug_send_event(self, content: str, message_type: str, metadata=None):
    print(f"[BAND SEND_EVENT] message_type={message_type}")
    print(f"[BAND SEND_EVENT] Content preview: {content[:150]}")
    try:
        result = await _original_send_event(self, content, message_type, metadata)
        print(f"[BAND SEND_EVENT] ✅ Success!")
        return result
    except Exception as e:
        print(f"[BAND SEND_EVENT] ❌ FAILED: {e}")
        raise

async def _debug_send_message(self, content: str, mentions=None):
    print(f"[BAND SEND_MSG] Content preview: {content[:150]}")
    print(f"[BAND SEND_MSG] Mentions: {mentions}")
    try:
        result = await _original_send_message(self, content, mentions)
        print(f"[BAND SEND_MSG] ✅ Success!")
        return result
    except Exception as e:
        print(f"[BAND SEND_MSG] ❌ FAILED: {e}")
        raise

AgentTools.send_event = _debug_send_event
AgentTools.send_message = _debug_send_message
# === END DEBUG LOGGING PATCH ===

# Load environment variables
load_dotenv()

# Import all agent adapters
from stage1.intake_agent import intake_agent
from stage1.repo_analyzer import repo_analyzer
from stage1.fraud_detector import fraud_detector
from stage1.kg_builder_agent import kg_builder_agent
from stage2.business_judge import business_judge
from stage2.innovation_judge import innovation_judge
from stage2.band_judge import band_judge
from stage2.demo_judge import demo_judge
from judge.head_judge import head_judge

AGENT_REGISTRY = [
    ("IntakeAgent", intake_agent, "INTAKE"),
    ("RepoAnalyzer", repo_analyzer, "REPO_ANALYZER"),
    ("FraudDetector", fraud_detector, "FRAUD_DETECTOR"),
    ("KGBuilderAgent", kg_builder_agent, "KG_BUILDER"),
    ("BusinessJudge", business_judge, "BUSINESS_JUDGE"),
    ("InnovationJudge", innovation_judge, "INNOVATION_JUDGE"),
    ("BandJudge", band_judge, "BAND_JUDGE"),
    ("DemoJudge", demo_judge, "DEMO_JUDGE"),
    ("HeadJudge", head_judge, "HEAD_JUDGE"),
]

async def preflight_check():
    """Verify Band connectivity before starting agents."""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://app.band.ai", timeout=5)
            print(f"✅ Band platform reachable (status {r.status_code})")
    except Exception as e:
        print(f"❌ Band platform unreachable: {e}")
        print("   Check your internet connection before starting agents.")
        return False
    return True

class Watchdog:
    """In-process daemon for connection health — mirrors 
    Codeband's approach. Not a Band agent, no API key needed."""
    
    def __init__(self, agents: list):
        self.agents = agents
        self.running = True
    
    async def run(self):
        print("🐕 Watchdog started — monitoring agent connections")
        while self.running:
            await asyncio.sleep(10)
            for agent in self.agents:
                try:
                    # Check if agent's execution context is alive
                    ctx = getattr(agent, '_execution_context', None)
                    if ctx is None:
                        print(f"⚠ Watchdog: {agent.__class__.__name__} has no context")
                        continue
                    # Force a lightweight status check
                    if hasattr(ctx, 'is_connected'):
                        if not ctx.is_connected():
                            print(f"🔄 Watchdog: Reconnecting {agent.__class__.__name__}...")
                except Exception as e:
                    pass  # Watchdog never crashes

async def main():
    print("=====================================================================")
    print("STARTING HACKATHON JUDGING PANEL ON PRODUCTION BAND PLATFORM")
    print("=====================================================================")

    if not await preflight_check():
        sys.exit(1)

    # List to track created agents
    all_agents = []

    # Create each agent that has configured credentials
    for name, adapter, prefix in AGENT_REGISTRY:
        agent_id = os.getenv(f"{prefix}_AGENT_ID")
        api_key = os.getenv(f"{prefix}_API_KEY")

        if not agent_id or not api_key:
            print(f"⚠️  [Skipped] {name} - Missing {prefix}_AGENT_ID or {prefix}_API_KEY in .env")
            continue

        print(f"🚀 [Starting] {name} (Connecting to Band platform)...")
        try:
            agent = Agent.create(adapter=adapter, agent_id=agent_id, api_key=api_key)
            all_agents.append(agent)
        except Exception as e:
            print(f"❌ [Error] Failed creating {name}: {e}")

    if not all_agents:
        print("❌ No agents started. Please configure agent credentials in your .env file.")
        sys.exit(1)

    watchdog = Watchdog(all_agents)
    await asyncio.gather(
        *[agent.run() for agent in all_agents],
        watchdog.run()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Production agents stopped by user.")
