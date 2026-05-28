"""PreToolUse recall injection helpers (v0.10.1).

Before a substantive tool fires (Bash, Edit, Write, MultiEdit), extract a topic
from the tool input and run a quick brain recall. Inject the top hits as
additionalContext so the agent sees prior captures BEFORE acting.

Heuristic topic extraction + per-session LRU cache prevents recall spam.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path


_TRIGGER_TOOLS: frozenset[str] = frozenset({"Bash", "Edit", "Write", "MultiEdit"})


def _extract_topic_from_tool(tool_name: str, tool_input: dict) -> str | None:
    """Return a short topic string for recall, or None if no recall worth running.

    Heuristic:
      - Bash: take first 4 non-flag tokens from the command.
      - Edit/Write/MultiEdit: take the file basename.
      - Anything else: None (skip).
    Empty / blank topic also returns None.
    """
    if tool_name not in _TRIGGER_TOOLS:
        return None
    if tool_name == "Bash":
        cmd = str(tool_input.get("command", ""))
        if not cmd.strip():
            return None
        tokens = [t for t in cmd.split() if not t.startswith("-")][:4]
        topic = " ".join(tokens).strip()
        return topic or None
    if tool_name in {"Edit", "Write", "MultiEdit"}:
        path = str(tool_input.get("file_path", ""))
        if not path.strip():
            return None
        name = Path(path).name
        return name or None
    return None


class RecallCache:
    """LRU cache for recall results within a single CC subprocess hook
    invocation. Bounded; oldest entries are evicted when full."""

    def __init__(self, max_size: int = 32) -> None:
        self._max = max_size
        self._data: OrderedDict[str, str] = OrderedDict()

    def get(self, key: str) -> str | None:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: str, value: str) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self._max:
            self._data.popitem(last=False)
