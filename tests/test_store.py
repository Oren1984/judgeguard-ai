import pytest

from judgeguard.store import Store, StoreError
from test_gate_and_metrics import case


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def test_cases_are_not_duplicated_on_repeat_append(store):
    rec = case("chunk_list", "position_biased", "PASS", "FAIL")
    assert store.append_cases([rec]) == 1
    assert store.append_cases([rec, rec]) == 0
    assert len(store.cases()) == 1
    assert store.run_ids() == ["run-test"]


def test_review_events_append_and_never_overwrite(store):
    rec = case("chunk_list", "position_biased", "PASS", "FAIL")
    store.append_cases([rec])
    assert store.append_review(rec, "CONFIRM", "chunk_list-c1", "tests agree", "reviewer-1", "tok-1")
    assert store.append_review(rec, "OVERRIDE", "TIE", "second look", "reviewer-2", "tok-2")
    events = store.reviews(rec["case_id"])
    assert [e["action"] for e in events] == ["CONFIRM", "OVERRIDE"]
    assert events[0]["original_decision"] == events[1]["original_decision"] == "chunk_list-c1"
    assert store.cases()[0]["conditions"]["original"]["judgment"]["winner"] == "chunk_list-c1"


def test_same_submission_token_is_recorded_once(store):
    rec = case("chunk_list", "position_biased", "PASS", "FAIL")
    assert store.append_review(rec, "CONFIRM", "chunk_list-c1", "ok", "r", "tok") is True
    assert store.append_review(rec, "CONFIRM", "chunk_list-c1", "ok", "r", "tok") is False
    assert len(store.reviews()) == 1


@pytest.mark.parametrize("action,final,reason,reviewer,token", [
    ("APPROVE", "chunk_list-c1", "ok", "r", "t"),
    ("CONFIRM", "chunk_list-c1", "  ", "r", "t"),
    ("CONFIRM", "chunk_list-c1", "x" * 281, "r", "t"),
    ("CONFIRM", "chunk_list-c1", "ok", "", "t"),
    ("CONFIRM", "chunk_list-c2", "ok", "r", "t"),
    ("OVERRIDE", "chunk_list-c1", "ok", "r", "t"),
    ("OVERRIDE", "clamp-c1", "ok", "r", "t"),
    ("CONFIRM", "chunk_list-c1", "ok", "r", ""),
])
def test_invalid_reviews_are_rejected(store, action, final, reason, reviewer, token):
    rec = case("chunk_list", "position_biased", "PASS", "FAIL")
    with pytest.raises(StoreError):
        store.append_review(rec, action, final, reason, reviewer, token)
    assert store.reviews() == []


def test_partially_written_line_is_skipped(store):
    rec = case("clamp", "rubric_based", "PASS", "FAIL")
    store.append_cases([rec])
    with open(store.cases_path, "a", encoding="utf-8") as fh:
        fh.write('{"case_id": "trunc')
    assert [r["case_id"] for r in store.cases()] == [rec["case_id"]]
