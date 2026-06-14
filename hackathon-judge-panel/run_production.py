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

async def start_agent(name: str, adapter, env_prefix: str):
    """Start a single agent on the live Band platform."""
    agent_id = os.getenv(f"{env_prefix}_AGENT_ID")
    api_key = os.getenv(f"{env_prefix}_API_KEY")

    if not agent_id or not api_key:
        print(f"⚠️  [Skipped] {name} - Missing {env_prefix}_AGENT_ID or {env_prefix}_API_KEY in .env")
        return

    print(f"🚀 [Starting] {name} (Connecting to Band platform)...")
    try:
        agent = Agent.create(adapter=adapter, agent_id=agent_id, api_key=api_key)
        await agent.run()
    except Exception as e:
        print(f"❌ [Error] Failed running {name}: {e}")

async def main():
    print("=====================================================================")
    print("STARTING HACKATHON JUDGING PANEL ON PRODUCTION BAND PLATFORM")
    print("=====================================================================")

    # Create task for each agent that has configured credentials
    tasks = []
    for name, adapter, prefix in AGENT_REGISTRY:
        tasks.append(start_agent(name, adapter, prefix))

    active_tasks = [t for t in tasks if t is not None]
    if not active_tasks:
        print("❌ No agents started. Please configure agent credentials in your .env file.")
        sys.exit(1)

    await asyncio.gather(*active_tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Production agents stopped by user.")
