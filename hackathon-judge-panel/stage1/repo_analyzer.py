"""
Repo Analyzer — the ONLY agent allowed to read raw source code.

Design invariant:
  No other agent in the system ever sees repository file contents.
  This agent reads README, requirements.txt, AGENTS.md, the file tree,
  and commit metadata, then sends it to the LLM for structured analysis.
  HeadroomChatModel auto-compresses before the LLM call.
  Its structured JSON output feeds `build_knowledge_graph()`.
"""

import json
import os

from github import Github

from core.llm import get_cheap_llm
from headroom_config import MAX_COMMITS


SYSTEM_PROMPT = """\
You are a code analysis agent.  Analyze the repository information and
return ONLY valid JSON with these keys:

- framework: Primary framework used (string)
- agent_count: Number of distinct AI agents found (int)
- band_usage: Whether the Band framework is genuinely used (bool)
- tech_stack: List of technologies/libraries used (list of strings)
- has_tests: Whether the project has test files (bool)
- architecture_summary: High-level architecture in max 3 sentences (string)
- fraud_flags: List of issues found (list of strings, empty if clean)

Fraud checks to perform:
- README claims N agents but code has fewer agent files → flag it
- All commits on one day → flag "single-day dump"
- No requirements.txt or env file → flag "not runnable"
- Band mentioned in README but no Band import in code → flag "Band faked"
"""

# Files we want to read in full (everything else is tree-only).
KEY_FILES = {"README.md", "readme.md", "requirements.txt", "AGENTS.md",
             "pyproject.toml", "setup.py", "package.json"}


async def analyze_repo(github_url: str) -> dict:
    """Analyze a GitHub repository and return structured metadata.

    This is the ONLY function in the system that touches raw source code.
    HeadroomChatModel automatically compresses context before the LLM call.

    Args:
        github_url: Full GitHub URL, e.g. "https://github.com/org/repo"

    Returns:
        Structured dict consumed by `build_knowledge_graph()`.
    """
    llm = get_cheap_llm()
    g = Github(os.getenv("GITHUB_TOKEN"))
    repo_name = github_url.replace("https://github.com/", "")
    repo = g.get_repo(repo_name)

    # ---- Collect key file contents (NOT all source files) ----
    contents = []
    try:
        for f in repo.get_contents(""):
            if f.name in KEY_FILES:
                try:
                    decoded = f.decoded_content.decode("utf-8", errors="replace")
                    contents.append(f"=== {f.name} ===\n{decoded}")
                except Exception:
                    contents.append(f"=== {f.name} === (binary, skipped)")
    except Exception as exc:
        contents.append(f"(Error listing root: {exc})")

    # ---- File tree (structure only, no contents) ----
    try:
        tree = [
            c.path
            for c in repo.get_git_tree(
                repo.default_branch, recursive=True
            ).tree
        ]
    except Exception:
        tree = []

    # ---- Commit date metadata (not diffs) ----
    try:
        commits = list(repo.get_commits()[:MAX_COMMITS])
        commit_dates = [c.commit.author.date.isoformat() for c in commits]
    except Exception:
        commit_dates = []

    # ---- Assemble raw context string ----
    raw_content = (
        "\n".join(contents)
        + f"\n\nFILE TREE:\n{json.dumps(tree)}"
        + f"\n\nCOMMIT DATES (last {MAX_COMMITS}): {json.dumps(commit_dates)}"
    )

    # ---- Send to LLM — HeadroomChatModel auto-compresses ----
    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", raw_content),
    ]

    response = llm.invoke(messages)

    try:
        analysis = json.loads(response.content)
    except json.JSONDecodeError:
        analysis = {
            "framework": "unknown",
            "agent_count": 0,
            "band_usage": False,
            "tech_stack": [],
            "has_tests": False,
            "architecture_summary": "Could not parse LLM response.",
            "fraud_flags": ["llm_parse_error"],
        }

    return analysis
