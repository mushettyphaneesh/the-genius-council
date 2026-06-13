"""
Hackathon Judge Panel — Main Orchestrator.

Two-stage pipeline designed to minimize LLM token costs (~12k total):

  Stage 1 (parallel, cheap model):
    - intake_agent:   Extracts problem/solution/track from submission
    - repo_analyzer:  ONLY agent that reads raw source code
    - fraud_detector: Early abort if submission is fraudulent

  Knowledge Graph:
    - Built ONCE from Stage 1 outputs, compressed via Headroom

  Stage 2 (parallel, cheap model):
    - business_judge:   Market size, ROI, enterprise value
    - innovation_judge: Novelty, creative AI usage
    - band_judge:       Band framework integration quality
    - demo_judge:       Presentation and prototype evidence

  Final (single expensive call):
    - head_judge:  Weighted scoring + debate protocol if scores diverge

Usage:
    python main.py
"""

import asyncio
import json
import sys

from dotenv import load_dotenv

# Load .env before any module reads env vars.
load_dotenv()

from stage1.intake_agent import extract_intake
from stage1.repo_analyzer import analyze_repo
from stage1.fraud_detector import detect_fraud
from core.knowledge_graph import build_knowledge_graph
from stage2.business_judge import judge_business
from stage2.innovation_judge import judge_innovation
from stage2.band_judge import judge_band
from stage2.demo_judge import judge_demo
from judge.head_judge import final_judgment


async def evaluate(submission: dict) -> dict:
    """Run the full two-stage evaluation pipeline.

    Args:
        submission: Dict with at least:
            - github_url (str): Full GitHub URL
            - description (str): Human-readable project summary
            Optional:
            - video_transcript (str): Demo video transcript
            - readme (str): Pre-fetched README content
            - problem, solution, track (str): Structured intake fields

    Returns:
        Final evaluation dict from the head judge.
    """
    print("=" * 60)
    print("HACKATHON JUDGE PANEL — Evaluation Starting")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Stage 1 — intake + repo + fraud in parallel (cheap models)
    # ------------------------------------------------------------------
    print("\n[Stage 1] Running intake, repo analysis, and fraud detection...")

    intake, repo_data, fraud = await asyncio.gather(
        extract_intake(submission),
        analyze_repo(submission["github_url"]),
        detect_fraud(
            submission.get("readme", ""),
            [],  # file_tree — populated by repo_analyzer in production
            [],  # commit_dates — populated by repo_analyzer in production
        ),
    )

    print(f"  ✓ Intake: track={intake.get('track', 'N/A')}")
    print(f"  ✓ Repo:   framework={repo_data.get('framework', 'N/A')}, "
          f"agents={repo_data.get('agent_count', '?')}")
    print(f"  ✓ Fraud:  score={fraud.get('fraud_score', 0)}, "
          f"flags={fraud.get('flags', [])}")

    # ------------------------------------------------------------------
    # Early abort if fraud detected — saves ALL Stage 2 tokens.
    # ------------------------------------------------------------------
    if fraud.get("abort_evaluation"):
        print("\n⚠ FRAUD DETECTED — aborting evaluation.")
        return {
            "final_score": 0,
            "recommendation": "DISQUALIFIED",
            "fraud_flags": fraud.get("flags", []),
            "debate_triggered": False,
            "debate_summary": None,
            "confidence": "high",
            "scores": {},
        }

    # ------------------------------------------------------------------
    # Build compressed knowledge graph — ONCE.
    # ------------------------------------------------------------------
    print("\n[Knowledge Graph] Building compressed context...")
    kg = build_knowledge_graph(repo_data, intake)
    print(f"  ✓ KG keys: {list(kg.keys())}")

    # ------------------------------------------------------------------
    # Stage 2 — all judges run in parallel (cheap models, read KG only)
    # ------------------------------------------------------------------
    print("\n[Stage 2] Running domain judges in parallel...")

    biz, innov, band, demo = await asyncio.gather(
        judge_business(submission.get("description", "")),
        judge_innovation(submission.get("description", "")),
        judge_band(submission.get("description", "")),
        judge_demo(submission.get("video_transcript", "")),
    )

    print(f"  ✓ Business:   {biz.get('business_score', '?')}/100")
    print(f"  ✓ Innovation: {innov.get('innovation_score', '?')}/100")
    print(f"  ✓ Band:       {band.get('band_score', '?')}/100")
    print(f"  ✓ Demo:       {demo.get('demo_score', '?')}/100")

    # ------------------------------------------------------------------
    # Head Judge — single expensive model call.
    # ------------------------------------------------------------------
    print("\n[Head Judge] Final arbitration...")
    result = await final_judgment()

    print(f"\n{'=' * 60}")
    print(f"FINAL SCORE:      {result.get('final_score', 'N/A')}/100")
    print(f"RECOMMENDATION:   {result.get('recommendation', 'N/A')}")
    print(f"DEBATE TRIGGERED: {result.get('debate_triggered', False)}")
    print(f"CONFIDENCE:       {result.get('confidence', 'N/A')}")
    if result.get("fraud_flags"):
        print(f"FRAUD FLAGS:      {result['fraud_flags']}")
    print(f"{'=' * 60}")

    return result


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------
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

    result = asyncio.run(evaluate(sample_submission))
    print("\n" + json.dumps(result, indent=2))
