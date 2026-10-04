"""Full suite through the real worker process and the real file exchange."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import ROOT, SANDBOXED, SKIP_REASON
from judgeguard import config, experiment, fixtures, gate, metrics
from judgeguard.jobs import SandboxClient

pytestmark = pytest.mark.skipif(not SANDBOXED, reason=SKIP_REASON)
EXPECTED = json.loads((Path(__file__).parent / "expected_outcomes.json").read_text())


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("exchange")
    jobs_dir, results_dir = base / "jobs", base / "results"
    jobs_dir.mkdir()
    results_dir.mkdir()
    env = {**os.environ, "JG_JOBS_DIR": str(jobs_dir), "JG_RESULTS_DIR": str(results_dir)}
    proc = subprocess.Popen([sys.executable, "-m", "judgeguard.worker"], cwd=ROOT, env=env)
    try:
        client = SandboxClient(jobs_dir, results_dir, poll_s=0.02)
        deadline = time.monotonic() + 10
        while not client.worker_status()["available"] and time.monotonic() < deadline:
            time.sleep(0.05)
        assert client.worker_status()["available"]
        first = experiment.run_suite(client, "run-e2e-1")
        second = experiment.run_suite(client, "run-e2e-2")
        yield {"first": first, "second": second, "client": client, "jobs_dir": jobs_dir}
    finally:
        proc.terminate()
        proc.wait(10)


def by(records, task_id, judge_id):
    return next(r for r in records if r["task_id"] == task_id and r["judge_id"] == judge_id)


def test_every_case_is_recorded(runs):
    assert len(runs["first"]) == len(fixtures.task_ids()) * len(config.JUDGE_IDS)
    assert all(r["mock"] is True for r in runs["first"])
    assert os.listdir(runs["jobs_dir"]) == []


def test_candidate_test_outcomes_match_expectations(runs):
    for task_id in fixtures.task_ids():
        rec = by(runs["first"], task_id, "rubric_based")
        actual = {cid: v["base"]["status"] for cid, v in rec["test_evidence"].items()}
        assert actual == EXPECTED[task_id], task_id


def test_style_only_variant_preserves_test_outcomes(runs):
    for task_id in fixtures.task_ids():
        rec = by(runs["first"], task_id, "rubric_based")
        target = rec["test_evidence"][rec["style_target"]]
        assert target["style"]["status"] == target["base"]["status"], task_id
        assert target["style"]["tests"] == target["base"]["tests"], task_id
    assert not any("TRANSFORM_INVARIANT_VIOLATED" in r["gate"]["reason_codes"] for r in runs["first"])


def test_swapped_order_never_changes_test_evidence_or_candidate_identity(runs):
    for rec in runs["first"]:
        original, swapped = rec["conditions"]["original"], rec["conditions"]["swapped"]
        assert swapped["display_order"] == list(reversed(original["display_order"]))
        assert swapped["test_statuses"] == original["test_statuses"]
        assert swapped["test_preference"] == original["test_preference"]


def test_prepared_demo_triggers_the_expected_review_reasons(runs):
    demo = config.EXPERIMENT["prepared_demo"]
    rec = by(runs["first"], demo["task_id"], demo["judge_id"])
    assert rec["gate"]["status"] == gate.HUMAN_REVIEW
    assert rec["gate"]["reason_codes"] == sorted(demo["expected_reasons"])
    assert rec["conditions"]["original"]["judgment"]["winner"] != rec["conditions"]["swapped"]["judgment"]["winner"]


def test_timeout_and_execution_error_route_to_review(runs):
    for judge_id in config.JUDGE_IDS:
        assert "TIMEOUT" in by(runs["first"], "gcd", judge_id)["gate"]["reason_codes"]
        assert "EXECUTION_ERROR" in by(runs["first"], "parse_kv", judge_id)["gate"]["reason_codes"]


def test_execution_counts(runs):
    summary = metrics.compute(runs["first"])["executions"]
    assert summary["executions"] == 3 * len(fixtures.task_ids())
    assert (summary["timeouts"], summary["failures"]) == (1, 1)
    assert runs["client"].submitted == 2 * summary["executions"]


def test_auto_accept_never_prefers_a_failing_candidate(runs):
    for rec in runs["first"]:
        if rec["gate"]["status"] != gate.AUTO_ACCEPT:
            continue
        assert rec["flags"]["order_stable"] is True
        for condition in rec["conditions"].values():
            winner = condition["judgment"]["winner"]
            if winner and condition["test_preference"]["kind"] == gate.CLEAR:
                assert winner == condition["test_preference"]["preferred"]


def test_full_suite_is_reproducible(runs):
    assert experiment.digest(runs["first"]) == experiment.digest(runs["second"])
    assert metrics.compute(runs["first"]) == metrics.compute(runs["second"])
