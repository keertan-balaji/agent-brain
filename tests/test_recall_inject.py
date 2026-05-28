"""Topic extraction + per-session recall cache for PreToolUse hook (v0.10.1)."""

from __future__ import annotations

from brain.hooks.recall_inject import (
    _extract_topic_from_tool,
    RecallCache,
)


def test_extract_topic_from_bash_command() -> None:
    topic = _extract_topic_from_tool("Bash", {"command": "pytest tests/test_x.py -v"})
    assert topic is not None
    assert "pytest" in topic
    assert "test_x" in topic


def test_extract_topic_from_edit_file() -> None:
    topic = _extract_topic_from_tool(
        "Edit",
        {"file_path": "/abs/src/brain/cli.py", "old_string": "x", "new_string": "y"},
    )
    assert topic is not None
    assert "cli.py" in topic


def test_extract_topic_from_write_file() -> None:
    topic = _extract_topic_from_tool(
        "Write",
        {"file_path": "/abs/src/new_thing.py", "content": "..."},
    )
    assert topic == "new_thing.py"


def test_extract_topic_returns_none_for_blocklisted_tool() -> None:
    assert _extract_topic_from_tool("TodoWrite", {"todos": []}) is None
    assert _extract_topic_from_tool("Skill", {"skill": "foo"}) is None
    assert _extract_topic_from_tool("AskUserQuestion", {}) is None


def test_extract_topic_returns_none_for_empty_input() -> None:
    assert _extract_topic_from_tool("Bash", {"command": ""}) is None
    assert _extract_topic_from_tool("Edit", {"file_path": ""}) is None


def test_recall_cache_get_returns_none_for_missing_key() -> None:
    cache = RecallCache(max_size=8)
    assert cache.get("foo") is None


def test_recall_cache_put_then_get() -> None:
    cache = RecallCache(max_size=8)
    cache.put("foo", "results-A")
    cache.put("bar", "results-B")
    assert cache.get("foo") == "results-A"
    assert cache.get("bar") == "results-B"


def test_recall_cache_evicts_oldest_when_full() -> None:
    cache = RecallCache(max_size=2)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("c", "3")  # evicts "a"
    assert cache.get("a") is None
    assert cache.get("b") == "2"
    assert cache.get("c") == "3"


def test_recall_cache_put_same_key_updates_value_and_recency() -> None:
    cache = RecallCache(max_size=2)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("a", "updated")  # should keep "a" + "b" both; "b" becomes oldest
    assert cache.get("a") == "updated"
    cache.put("c", "3")  # evicts "b" since "a" was just touched
    assert cache.get("b") is None
    assert cache.get("a") == "updated"
    assert cache.get("c") == "3"
