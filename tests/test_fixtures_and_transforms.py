import ast
import json
from pathlib import Path

import pytest

from judgeguard import fixtures, judges, transforms

TASK_IDS = fixtures.task_ids()
EXPECTED = json.loads((Path(__file__).parent / "expected_outcomes.json").read_text())


def test_suite_size_and_expected_outcomes_cover_every_task():
    assert 10 <= len(TASK_IDS) <= 15
    assert set(TASK_IDS) == {k for k in EXPECTED if not k.startswith("_")}


def test_fixture_mix_includes_correct_incorrect_and_edge_cases():
    statuses = [s for task in TASK_IDS for s in EXPECTED[task].values()]
    assert {"PASS", "FAIL", "TIMEOUT", "ERROR"} <= set(statuses)
    pairs = [tuple(EXPECTED[t].values()) for t in TASK_IDS]
    assert ("PASS", "PASS") in pairs and ("FAIL", "FAIL") in pairs


@pytest.mark.parametrize("bad", ["nope", "../clamp", "clamp/../clamp", "", None, 7, "CLAMP"])
def test_unknown_or_malformed_task_ids_are_rejected(bad):
    with pytest.raises(fixtures.FixtureError):
        fixtures.load_task(bad)


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_candidates_have_stable_ids(task_id):
    task = fixtures.load_task(task_id)
    assert [c["id"] for c in task["candidates"]] == [f"{task_id}-c1", f"{task_id}-c2"]
    assert task["style_target"] in (f"{task_id}-c1", f"{task_id}-c2")


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_swap_changes_display_order_but_not_identity_or_source(task_id):
    task = fixtures.load_task(task_id)
    original = transforms.presented_sources(task, "original")
    swapped = transforms.presented_sources(task, "swapped")
    assert [p["candidate_id"] for p in swapped] == [p["candidate_id"] for p in reversed(original)]
    assert {p["candidate_id"]: p["source"] for p in original} == {p["candidate_id"]: p["source"] for p in swapped}


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_style_variant_changes_text_only(task_id):
    task = fixtures.load_task(task_id)
    target = task["style_target"]
    base = fixtures.candidate(task, target)["source"]
    styled = {p["candidate_id"]: p["source"] for p in transforms.presented_sources(task, "style")}
    assert styled[target] != base
    assert ast.dump(ast.parse(styled[target])) == ast.dump(ast.parse(base))
    assert judges.style_score(styled[target]) > judges.style_score(base)
    other = fixtures.other_candidate_id(task, target)
    assert styled[other] == fixtures.candidate(task, other)["source"]


def test_style_variant_refuses_to_alter_program_semantics():
    source = 'TEXT = """\nreturn 1\n"""\n'
    with pytest.raises(transforms.TransformError):
        transforms.style_only_variant(source)
