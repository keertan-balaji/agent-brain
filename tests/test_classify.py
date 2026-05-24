from brain.classify import buckets_for_kind


def test_decision_in_session_gets_episodic_and_semantic() -> None:
    assert sorted(buckets_for_kind("decision", curated=False)) == ["episodic", "semantic"]


def test_decision_promoted_is_semantic_only() -> None:
    assert buckets_for_kind("decision", curated=True) == ["semantic"]


def test_gotcha_is_failure_and_episodic() -> None:
    assert sorted(buckets_for_kind("gotcha", curated=False)) == ["episodic", "failure"]


def test_pattern_is_procedural_only() -> None:
    assert buckets_for_kind("pattern", curated=False) == ["procedural"]


def test_tool_call_output_is_episodic_only() -> None:
    assert buckets_for_kind("tool_call_output", curated=False) == ["episodic"]


def test_paper_is_semantic_only() -> None:
    assert buckets_for_kind("paper", curated=False) == ["semantic"]


def test_session_summary_is_episodic_only() -> None:
    assert buckets_for_kind("session_summary", curated=False) == ["episodic"]
