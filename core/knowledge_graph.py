"""
Knowledge Graph Utility — builds and compresses the KG from Stage 1 results.
Uses SmartCrusher to keep token usage minimal.
"""

import json
from headroom import SmartCrusher

_crusher = SmartCrusher()


def build_knowledge_graph(repo_analysis: dict, intake: dict) -> str:
    """Build and compress Stage 1 outputs into a knowledge graph.

    Args:
        repo_analysis: Output of repo_analyzer — framework, tech_stack, etc.
        intake: Output of intake_agent — problem, solution, track.

    Returns:
        The compressed knowledge graph string content.
    """
    kg = {
        "problem": intake.get("problem", ""),
        "solution": intake.get("solution", ""),
        "track": intake.get("track", ""),
        "framework": repo_analysis.get("framework", ""),
        "agent_count": repo_analysis.get("agent_count", 0),
        "band_usage": repo_analysis.get("band_usage", False),
        "tech_stack": repo_analysis.get("tech_stack", []),
        "has_tests": repo_analysis.get("has_tests", False),
        "architecture_summary": repo_analysis.get("architecture_summary", ""),
        "fraud_flags": repo_analysis.get("fraud_flags", []),
    }

    kg_json = json.dumps(kg, indent=2)

    try:
        crush_result = _crusher.crush(kg_json, query="hackathon submission")
        return crush_result.content
    except Exception:
        return kg_json
