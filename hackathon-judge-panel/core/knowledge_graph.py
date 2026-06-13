"""
Knowledge Graph — built once after Stage 1, shared with all Stage 2 agents.

Design invariant:
  Raw repository data (source files, README contents, file trees) NEVER
  leaves `build_knowledge_graph()`.  Every downstream consumer reads only
  the compressed representation stored in the shared context.

Compression note:
  HeadroomChatModel already auto-compresses at the LLM boundary.
  Here we additionally use SmartCrusher to pre-compress the KG JSON
  before storing it, so Stage 2 agents receive a minimal payload.
"""

import json

from headroom import SmartCrusher

from core.shared_context import ctx

# SmartCrusher for JSON-aware compression of the knowledge graph.
_crusher = SmartCrusher()


def build_knowledge_graph(repo_analysis: dict, intake: dict) -> dict:
    """Compress Stage 1 outputs into a knowledge graph and store it.

    Called ONCE after Stage 1 completes.  The returned dict is the
    uncompressed KG (useful for logging); Stage 2 agents always read
    the compressed version via `get_knowledge_graph()`.

    Args:
        repo_analysis: Output of repo_analyzer — framework, tech_stack, etc.
        intake: Output of intake_agent — problem, solution, track.

    Returns:
        The raw (uncompressed) knowledge graph dict.
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

    # Compress the KG JSON via SmartCrusher before storing.
    kg_json = json.dumps(kg, indent=2)
    try:
        crush_result = _crusher.crush(kg_json, query="hackathon submission")
        compressed = crush_result.content
    except Exception:
        # Fall back to raw JSON if crushing fails.
        compressed = kg_json

    ctx.put("knowledge_graph", compressed, agent="repo_analyzer")
    return kg


def get_knowledge_graph() -> str:
    """Retrieve the compressed knowledge graph for Stage 2 agents.

    All Stage 2 judges call this.  The data is already compressed
    by `build_knowledge_graph()`, so it's token-efficient by default.
    """
    return ctx.get("knowledge_graph", "")
