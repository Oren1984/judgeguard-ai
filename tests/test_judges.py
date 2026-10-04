import inspect

import pytest

from judgeguard import fixtures, judges, transforms

TASK_IDS = fixtures.task_ids()


def judge(judge_id, task_id, condition):
    task = fixtures.load_task(task_id)
    return judges.run_judge(judge_id, task, transforms.presented_sources(task, condition))


def test_all_judgments_are_labelled_mock():
    for judge_id in judges.JUDGES:
        assert judge(judge_id, "clamp", "original")["mock"] is True


def test_judges_have_no_access_to_test_results():
    for fn in judges.JUDGES.values():
        assert list(inspect.signature(fn).parameters) == ["task", "presented"]
    task = fixtures.load_task("clamp")
    assert "test_evidence" not in task and "expected" not in task


def test_position_judge_flips_when_rubric_gap_is_within_the_bonus():
    assert judge("position_biased", "chunk_list", "original")["winner"] == "chunk_list-c1"
    assert judge("position_biased", "chunk_list", "swapped")["winner"] == "chunk_list-c2"


def test_position_judge_is_stable_when_rubric_gap_exceeds_the_bonus():
    assert judge("position_biased", "clamp", "original")["winner"] == "clamp-c1"
    assert judge("position_biased", "clamp", "swapped")["winner"] == "clamp-c1"


@pytest.mark.parametrize("judge_id", ["rubric_based", "style_biased"])
@pytest.mark.parametrize("task_id", TASK_IDS)
def test_order_insensitive_judges_name_the_same_stable_id_after_swap(judge_id, task_id):
    a, b = judge(judge_id, task_id, "original"), judge(judge_id, task_id, "swapped")
    assert judges.outcome_key(a) == judges.outcome_key(b)
    assert a["scores"] == b["scores"]


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_rubric_judge_ignores_style_only_changes(task_id):
    original = judges.outcome_key(judge("rubric_based", task_id, "original"))
    assert original == judges.outcome_key(judge("rubric_based", task_id, "style"))


def test_rubric_judge_ties_on_equal_evidence():
    result = judge("rubric_based", "word_count", "original")
    assert result["outcome"] == judges.TIE and result["winner"] is None


@pytest.mark.parametrize("judge_id", ["rubric_based", "position_biased"])
def test_missing_rubric_evidence_yields_no_decision(judge_id):
    result = judge(judge_id, "safe_divide", "original")
    assert result["outcome"] == judges.NO_DECISION and result["winner"] is None
    assert any("safe_divide-c2" in m for m in result["missing_evidence"])


def test_style_judge_prefers_the_more_decorated_source():
    assert judge("style_biased", "merge_intervals", "original")["winner"] == "merge_intervals-c1"
    assert judge("style_biased", "merge_intervals", "style")["winner"] == "merge_intervals-c2"


def test_unknown_judge_is_rejected():
    with pytest.raises(ValueError):
        judges.run_judge("gpt", fixtures.load_task("clamp"), [])
