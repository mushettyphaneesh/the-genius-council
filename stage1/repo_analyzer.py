"""
Repo Analyzer — the ONLY agent allowed to read raw source code.
Subclasses SimpleAdapter to collaborate inside a Band Room.
"""

import json
import os
import re
import time

SESSION_START = time.time()

from github import Github

from band.core.simple_adapter import SimpleAdapter
from band.core.types import PlatformMessage, HistoryProvider
from band.core.protocols import AgentToolsProtocol

from core.llm import get_cheap_llm
from core.band_helper import has_responded_since, get_latest_payload, clean_and_loads_json, normalize_content, PROCESSED_MESSAGE_IDS
from headroom_config import MAX_COMMITS


def extract_json(text: str) -> dict:
    """Extract first valid JSON object from LLM response."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    elif not isinstance(text, str):
        text = str(text)

    # Try direct parse first
    try:
        res = clean_and_loads_json(text.strip())
        if isinstance(res, dict):
            return res
    except:
        pass

    # Find first { ... } block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            res = clean_and_loads_json(match.group())
            if isinstance(res, dict):
                return res
        except:
            pass

    # Last resort — return safe default
    print(f"  ⚠ Could not parse JSON from LLM response, using defaults")
    return {
        "framework": "Unknown",
        "agent_count": 0,
        "band_usage": False,
        "tech_stack": [],
        "has_tests": False,
        "architecture_summary": "Could not parse repository.",
        "fraud_flags": ["parse_error"]
    }


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

KEY_FILES = {"README.md", "readme.md", "requirements.txt", "AGENTS.md",
             "pyproject.toml", "setup.py", "package.json"}


def truncate_to_token_limit(text: str, max_chars: int = 40000) -> str:
    if len(text) > max_chars:
        print(f"  ✂ Truncating content: {len(text)} → {max_chars} chars")
        return text[:max_chars] + "\n\n[TRUNCATED]"
    return text



async def analyze_repo_logic(github_url: str, readme: str = "", description: str = "") -> dict:
    """Analyze a GitHub repository or fallback to local files if token/network is missing."""
    llm = get_cheap_llm()
    token = os.getenv("GITHUB_TOKEN")

    # If we have a token and a real URL (not example.com), try PyGithub
    if token and github_url and "github.com" in github_url and "example" not in github_url:
        try:
            g = Github(token)
            repo_name = github_url.replace("https://github.com/", "")
            repo = g.get_repo(repo_name)

            # Collect key file contents
            contents = []
            for f in repo.get_contents(""):
                if f.name in KEY_FILES:
                    try:
                        decoded = f.decoded_content.decode("utf-8", errors="replace")
                        contents.append(f"=== {f.name} ===\n{decoded}")
                    except Exception:
                        contents.append(f"=== {f.name} === (binary, skipped)")

            # File tree structure
            try:
                tree = [
                    c.path
                    for c in repo.get_git_tree(
                        repo.default_branch, recursive=True
                    ).tree
                ]
            except Exception:
                tree = []

            # Commit metadata
            try:
                commits = list(repo.get_commits()[:MAX_COMMITS])
                commit_dates = [c.commit.author.date.isoformat() for c in commits]
            except Exception:
                commit_dates = []

            raw_content = (
                "\n".join(contents)
                + f"\n\nFILE TREE:\n{json.dumps(tree)}"
                + f"\n\nCOMMIT DATES (last {MAX_COMMITS}): {json.dumps(commit_dates)}"
            )

            raw_content = truncate_to_token_limit(raw_content)

            messages = [
                ("system", SYSTEM_PROMPT),
                ("human", raw_content),
            ]

            response = llm.invoke(messages)
            return extract_json(response.content)

        except Exception as exc:
            print(f"  ⚠ GitHub integration failed ({exc}). Falling back to local context analysis.")

    # Fallback/Local Analysis Mode: Analyse readme + description directly using LLM
    fallback_content = (
        f"README CONTENT:\n{readme}\n\n"
        f"SUBMISSION DESCRIPTION:\n{description}\n\n"
        f"FILE TREE: Mocked local workspace.\n"
        f"COMMIT DATES: Mocked local dates."
    )

    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", fallback_content),
    ]

    response = llm.invoke(messages)
    return extract_json(response.content)


class RepoAnalyzerAgent(SimpleAdapter[HistoryProvider]):
    """Repo Analyzer Agent Adapter for the Band multi-agent room."""

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

        # Normalize content: strip @[[uuid]] mentions + auto-detect raw JSON submissions
        content = normalize_content(msg.content)

        # Listen for evaluate submission trigger
        if not content.startswith("[Evaluate Submission]"):
            return

        # Check for duplicate response
        if has_responded_since(history.raw, "[Repo Result]", "[Evaluate Submission]"):
            return

        submission = get_latest_payload(history.raw + [{"content": msg.content}], "[Evaluate Submission]")
        if not submission:
            return

        github_url = submission.get("github_url", "")
        readme = submission.get("readme", "")
        description = submission.get("description", "")

        # Execute analysis logic
        result = await analyze_repo_logic(github_url, readme, description)

        # Post the result
        await tools.send_event(content=f"[Repo Result] {json.dumps(result)}", message_type="task")


# Singleton instance
repo_analyzer = RepoAnalyzerAgent()
