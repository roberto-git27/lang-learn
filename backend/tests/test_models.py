"""
Unit tests for `app.models.AgentRun.generated_count` — a derived property
(no DB access needed to exercise it, plain attribute access on a
constructed-in-memory ORM instance).
"""
from app.models import AgentRun


def test_generated_count_no_unfilled_specs():
    run = AgentRun(gap_count=3, trace={"unfilled_spec_ids": []})
    assert run.generated_count == 3


def test_generated_count_some_unfilled_specs():
    run = AgentRun(gap_count=5, trace={"unfilled_spec_ids": ["topic-4", "topic-5"]})
    assert run.generated_count == 3


def test_generated_count_missing_unfilled_key_defaults_to_zero():
    run = AgentRun(gap_count=2, trace={"request_params": {}})
    assert run.generated_count == 2


def test_generated_count_no_gap_is_zero():
    run = AgentRun(gap_count=0, trace={})
    assert run.generated_count == 0


def test_generated_count_never_negative():
    # Defensive: shouldn't happen in practice, but unfilled can't exceed gap.
    run = AgentRun(gap_count=1, trace={"unfilled_spec_ids": ["a", "b", "c"]})
    assert run.generated_count == 0


def test_generated_count_handles_non_dict_trace():
    # No unfilled-spec info available when trace isn't a dict -> assume the
    # whole gap was generated (unfilled defaults to 0), same as a run whose
    # trace never mentions unfilled_spec_ids at all.
    run = AgentRun(gap_count=4, trace=[])
    assert run.generated_count == 4
