"""
Shared Context Store — in-process key-value store for inter-agent data.

Replaces the spec's `SharedContext` (not available in headroom 0.2.15)
with a simple thread-safe dict.  This works because all agents run in
the same process via `asyncio.gather`.

For persistent / cross-process scenarios, swap this for
`headroom.memory.SQLiteMemoryStore` or Redis.
"""

import threading
from typing import Any


class SharedContextStore:
    """Thread-safe in-process key-value store for agent communication.

    Usage:
        ctx = SharedContextStore()
        ctx.put("score_business", {"business_score": 85}, agent="business_judge")
        data = ctx.get("score_business")
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._provenance: dict[str, str] = {}  # key → agent that wrote it
        self._lock = threading.Lock()

    def put(self, key: str, value: Any, agent: str = "unknown") -> None:
        """Store a value with provenance tracking."""
        with self._lock:
            self._data[key] = value
            self._provenance[key] = agent

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key."""
        with self._lock:
            return self._data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists."""
        with self._lock:
            return key in self._data

    def who_wrote(self, key: str) -> str | None:
        """Return the agent name that stored this key."""
        with self._lock:
            return self._provenance.get(key)

    def keys(self) -> list[str]:
        """Return all stored keys."""
        with self._lock:
            return list(self._data.keys())

    def clear(self) -> None:
        """Clear all stored data."""
        with self._lock:
            self._data.clear()
            self._provenance.clear()


# Singleton instance — shared across all agents in this process.
ctx = SharedContextStore()
