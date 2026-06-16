"""
Hackathon Judge Panel — Main Orchestrator.

Orchestrated fully through the Band multi-agent platform.
All agents communicate and collaborate inside a shared Band Room.
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

# Load .env before any module reads env vars.
load_dotenv()

from core.band_simulator import MockBandRoom
from stage1.intake_agent import intake_agent
from stage1.repo_analyzer import repo_analyzer
from stage1.fraud_detector import fraud_detector
from stage1.kg_builder_agent import kg_builder_agent
from stage2.business_judge import business_judge
from stage2.innovation_judge import innovation_judge
from stage2.band_judge import band_judge
from stage2.demo_judge import demo_judge
from judge.head_judge import head_judge


async def evaluate(submission: dict, use_prod: bool = False) -> dict:
    """Run the multi-agent Band evaluation pipeline.

    Args:
        submission: Dict with github_url, description, video_transcript, and readme.
        use_prod: True if connecting to real Band cloud (requires API keys).

    Returns:
        Final evaluation verdict dict from Head Judge.
    """
    if use_prod:
        print("\n========================================================")
        print("PRODUCTION MODE — Connecting to Band Platform (app.band.ai)")
        print("========================================================\n")
        print("To connect your agents to the real Band service, configure your")
        print(".env with THENVOI_AGENT_ID and THENVOI_API_KEY. For example:\n")
        print("    from band import Agent")
        print("    agent = Agent.create(adapter=business_judge, agent_id='...', api_key='...')")
        print("    await agent.run()\n")
        print("Running in Local Simulation mode instead for local execution...\n")

    print("=" * 60)
    print("HACKATHON JUDGE PANEL — Band Multi-Agent Evaluation")
    print("=" * 60)

    # 1. Initialize local Band Room simulator
    room = MockBandRoom("hackathon-eval-room")

    # 2. Register all 9 agent adapters (Stage 1 + Stage 2 + Final)
    room.register_adapter("IntakeAgent", intake_agent)
    room.register_adapter("RepoAnalyzer", repo_analyzer)
    room.register_adapter("FraudDetector", fraud_detector)
    room.register_adapter("KGBuilderAgent", kg_builder_agent)
    room.register_adapter("BusinessJudge", business_judge)
    room.register_adapter("InnovationJudge", innovation_judge)
    room.register_adapter("BandJudge", band_judge)
    room.register_adapter("DemoJudge", demo_judge)
    room.register_adapter("HeadJudge", head_judge)

    # 3. Send initial trigger message to room to kick off evaluation
    trigger_content = f"[Evaluate Submission] {json.dumps(submission)}"
    await room.send_initial_message(trigger_content)

    # 4. Wait for HeadJudge to post the [Final Judgment] message
    timeout = 60.0
    elapsed = 0.0
    final_msg = None

    while elapsed < timeout:
        for m in room.messages:
            if m["content"].startswith("[Final Judgment]"):
                final_msg = m
                break
        if final_msg:
            break
        await asyncio.sleep(0.1)
        elapsed += 0.1

    if not final_msg:
        print("❌ [Timeout] Evaluation did not complete within the timeout period.")
        return {
            "error": "Evaluation timed out.",
            "final_score": 0,
            "recommendation": "ERROR",
        }

    # 5. Extract and parse result from the Final Judgment message
    try:
        raw_json = final_msg["content"][len("[Final Judgment]"):].strip()
        result = json.loads(raw_json)
    except Exception as e:
        print(f"❌ [Error] Failed to parse Final Judgment payload: {e}")
        result = {
            "error": f"Parse error: {e}",
            "final_score": 0,
            "recommendation": "ERROR",
        }

    print(f"\n{'=' * 60}")
    print(f"FINAL SCORE:      {result.get('final_score', 'N/A')}/100")
    print(f"RECOMMENDATION:   {result.get('recommendation', 'N/A')}")
    print(f"DEBATE TRIGGERED: {result.get('debate_triggered', False)}")
    print(f"CONFIDENCE:       {result.get('confidence', 'N/A')}")
    if result.get("fraud_flags"):
        print(f"FRAUD FLAGS:      {result['fraud_flags']}")
    print(f"{'=' * 60}")

    return result


if __name__ == "__main__":
    sample_submission = {
        "github_url": "https://github.com/example/project",
        "description": (
            "A multi-agent HR workflow automation platform that uses "
            "Band to orchestrate specialised agents for resume screening, "
            "interview scheduling, and candidate ranking."
        ),
        "video_transcript": (
            "Welcome to our demo. We built an HR workflow tool that "
            "automates resume screening using three specialised agents. "
            "The first agent parses resumes, the second matches candidates "
            "to job descriptions, and the third ranks them by fit score. "
            "We use Band for orchestration and deploy on AWS Lambda."
        ),
        "readme": (
            "# HR Agent Suite\n\n"
            "Multi-agent HR automation using Band framework.\n\n"
            "## Agents\n"
            "- ResumeParser: Extracts structured data from resumes\n"
            "- Matcher: Compares candidates to job requirements\n"
            "- Ranker: Produces final ranked list\n\n"
            "## Setup\n"
            "pip install -r requirements.txt\n"
            "python main.py\n"
        ),
    }

    # Parse args
    use_prod = "--prod" in sys.argv

    result = asyncio.run(evaluate(sample_submission, use_prod=use_prod))
    print("\nFinal Result Output:")
    print(json.dumps(result, indent=2))
