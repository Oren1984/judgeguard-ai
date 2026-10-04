import json
import os
import threading
import time

import pytest

from judgeguard import config, jobs, sandbox_runner
from judgeguard.worker import Worker


def canned(task_id, candidate_id, variant, **_):
    canned.calls.append((task_id, candidate_id, variant))
    return {"task_id": task_id, "candidate_id": candidate_id, "variant": variant, "status": "PASS",
            "counts": {"tests": 1, "passed": 1}, "tests": [], "duration_s": 0.0, "output_tail": "", "error": None}


@pytest.fixture
def stub_runner(monkeypatch):
    """Replace real execution so these tests exercise only the exchange protocol."""
    canned.calls = []
    monkeypatch.setattr(sandbox_runner, "run_candidate", canned)
    return canned


@pytest.fixture
def worker(exchange, tmp_path, stub_runner):
    return Worker(*exchange, tmp_root=tmp_path)


@pytest.fixture
def running_worker(worker):
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            worker.heartbeat("idle")
            if not worker.process_one():
                time.sleep(0.02)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    time.sleep(0.1)
    yield worker
    stop.set()
    thread.join(2)


def put_job(jobs_dir, job, name=None):
    path = jobs_dir / (name or f"{job['job_id']}.json")
    path.write_text(json.dumps(job))
    return path


def result_of(results_dir, job_id):
    return json.loads((results_dir / f"{job_id}.json").read_text())


def age(path, seconds):
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_job_ids_are_deterministic_and_distinct():
    a = jobs.make_job_id("run-1", "clamp", "clamp-c1", "base")
    assert a == jobs.make_job_id("run-1", "clamp", "clamp-c1", "base")
    assert a != jobs.make_job_id("run-2", "clamp", "clamp-c1", "base")
    assert a != jobs.make_job_id("run-1", "clamp", "clamp-c1", "style")
    assert jobs.JOB_FILE_RE.match(a + ".json")


@pytest.mark.parametrize("mutate,code", [
    (lambda j: j.update(extra=1), "invalid_schema"),
    (lambda j: j.pop("variant"), "invalid_schema"),
    (lambda j: j.update(schema_version=99), "unsupported_schema_version"),
    (lambda j: j.update(job_id="../../etc/passwd"), "invalid_job_id"),
    (lambda j: j.update(variant="shell"), "invalid_variant"),
    (lambda j: j.update(created_at="now"), "invalid_created_at"),
    (lambda j: j.update(task_id="not_a_fixture"), "unknown_task_id"),
    (lambda j: j.update(task_id="../clamp"), "unknown_task_id"),
    (lambda j: j.update(task_id=["clamp"]), "unknown_task_id"),
    (lambda j: j.update(candidate_id="gcd-c1"), "unknown_candidate_id"),
    (lambda j: j.update(candidate_id="clamp-c1", variant="style"), "style_variant_not_defined_for_candidate"),
    (lambda j: j.update(created_at=time.time() - 10_000), "stale_job"),
    (lambda j: j.update(created_at=time.time() + 10_000), "stale_job"),
])
def test_job_validation_rejects_bad_jobs(mutate, code):
    job = jobs.build_job("run-1", "clamp", "clamp-c2", "base")
    mutate(job)
    with pytest.raises(jobs.JobError) as err:
        jobs.validate_job(job)
    assert err.value.code == code


def test_validation_rejects_non_objects_and_filename_mismatch():
    with pytest.raises(jobs.JobError):
        jobs.validate_job(["not", "a", "job"])
    job = jobs.build_job("run-1", "clamp", "clamp-c1", "base")
    with pytest.raises(jobs.JobError) as err:
        jobs.validate_job(job, expected_job_id="0" * 32)
    assert err.value.code == "job_id_mismatch"


def test_worker_runs_valid_job_once(worker, exchange, stub_runner):
    jobs_dir, results_dir = exchange
    job = jobs.build_job("run-1", "clamp", "clamp-c1", "base")
    put_job(jobs_dir, job)
    assert worker.process_one() is True
    assert result_of(results_dir, job["job_id"])["status"] == "PASS"
    assert worker.process_one() is False        # result exists: the job is not executed again
    assert stub_runner.calls == [("clamp", "clamp-c1", "base")]


def test_worker_rejects_invalid_jobs_without_executing(worker, exchange, stub_runner):
    jobs_dir, results_dir = exchange
    unknown = jobs.build_job("run-1", "clamp", "clamp-c1", "base")
    unknown["task_id"] = "not_a_fixture"
    stale = jobs.build_job("run-2", "clamp", "clamp-c1", "base")
    stale["created_at"] -= 10_000
    for job in (unknown, stale):
        put_job(jobs_dir, job)
    assert worker.process_one() and worker.process_one()
    assert result_of(results_dir, unknown["job_id"])["error"] == "unknown_task_id"
    assert result_of(results_dir, stale["job_id"])["error"] == "stale_job"
    assert result_of(results_dir, stale["job_id"])["status"] == "REJECTED"
    assert stub_runner.calls == []


def test_worker_ignores_unexpected_file_names(worker, exchange, stub_runner):
    jobs_dir, results_dir = exchange
    job = jobs.build_job("run-1", "clamp", "clamp-c1", "base")
    for name in ("notes.txt", f".{job['job_id']}.json.123.tmp", "abc.json", f"{job['job_id']}.JSON"):
        put_job(jobs_dir, job, name)
    assert worker.process_one() is False
    assert os.listdir(results_dir) == [] and stub_runner.calls == []


def test_partial_job_file_is_given_time_then_rejected(worker, exchange, stub_runner):
    jobs_dir, results_dir = exchange
    job_id = "a" * 32
    path = jobs_dir / f"{job_id}.json"
    path.write_text('{"schema_version": 1, "job_id": "aaaa')
    assert worker.process_one() is False                      # fresh: may still be mid-write
    age(path, 30)
    assert worker.process_one() is True
    assert result_of(results_dir, job_id)["error"] == "unreadable_job_file"
    assert stub_runner.calls == []


def test_oversized_job_file_is_rejected(worker, exchange):
    jobs_dir, results_dir = exchange
    path = jobs_dir / f"{'b' * 32}.json"
    path.write_text(json.dumps({"pad": "x" * 10_000}))
    age(path, 30)
    assert worker.process_one() is True
    assert result_of(results_dir, "b" * 32)["status"] == "REJECTED"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    jobs.atomic_write_json(tmp_path / "x.json", {"a": 1})
    assert os.listdir(tmp_path) == ["x.json"]


def test_old_results_are_pruned_but_heartbeat_is_kept(worker, exchange):
    _, results_dir = exchange
    worker.heartbeat("idle")
    stale = results_dir / f"{'c' * 32}.json"
    stale.write_text("{}")
    age(stale, config.SANDBOX["result_ttl_s"] + 5)
    age(results_dir / jobs.HEARTBEAT_FILE, config.SANDBOX["result_ttl_s"] + 5)
    worker.prune_results()
    assert os.listdir(results_dir) == [jobs.HEARTBEAT_FILE]


def test_client_round_trip_is_idempotent(running_worker, exchange, stub_runner):
    client = jobs.SandboxClient(*exchange, poll_s=0.02)
    first = client.run("run-1", "clamp", "clamp-c1", "base")
    second = client.run("run-1", "clamp", "clamp-c1", "base")
    assert first["status"] == second["status"] == "PASS"
    assert client.submitted == 1
    assert stub_runner.calls == [("clamp", "clamp-c1", "base")]
    assert os.listdir(exchange[0]) == []                       # job file removed after the result arrived


def test_client_refuses_unknown_fixtures(exchange):
    client = jobs.SandboxClient(*exchange)
    with pytest.raises(jobs.JobError):
        client.run("run-1", "not_a_fixture", "x-c1", "base")
    assert os.listdir(exchange[0]) == []


def test_client_reports_missing_when_worker_is_down(exchange):
    client = jobs.SandboxClient(*exchange)
    assert client.worker_status()["available"] is False
    result = client.run("run-1", "clamp", "clamp-c1", "base")
    assert (result["status"], result["error"]) == ("MISSING", "worker_unavailable")
    assert os.listdir(exchange[0]) == []


def test_client_times_out_and_withdraws_the_job(worker, exchange, monkeypatch):
    monkeypatch.setitem(config.SANDBOX, "exec_timeout_s", 0)
    monkeypatch.setitem(config.SANDBOX, "result_wait_margin_s", 0.3)
    worker.heartbeat("idle")                                   # alive, but never processes anything
    client = jobs.SandboxClient(*exchange, poll_s=0.02)
    result = client.run("run-1", "clamp", "clamp-c1", "base")
    assert (result["status"], result["error"]) == ("MISSING", "no_result_before_deadline")
    assert os.listdir(exchange[0]) == []


def test_client_treats_malformed_result_as_missing(worker, exchange):
    worker.heartbeat("idle")
    job_id = jobs.make_job_id("run-1", "clamp", "clamp-c1", "base")
    (exchange[1] / f"{job_id}.json").write_text(json.dumps({"job_id": "someone-else", "status": "PASS"}))
    result = jobs.SandboxClient(*exchange).run("run-1", "clamp", "clamp-c1", "base")
    assert (result["status"], result["error"]) == ("MISSING", "invalid_result_file")


def test_stale_job_files_are_pruned_by_the_client(exchange):
    path = exchange[0] / f"{'d' * 32}.json"
    path.write_text("{}")
    age(path, config.SANDBOX["job_ttl_s"] + 5)
    assert jobs.SandboxClient(*exchange).prune_stale_jobs() == 1
    assert os.listdir(exchange[0]) == []
