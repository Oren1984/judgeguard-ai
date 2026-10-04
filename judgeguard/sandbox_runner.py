"""Executes one fixture candidate's tests in a bounded child process. Runs inside the sandbox container only."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import config, fixtures, transforms

REPORT = "report.json"
OUTPUT = "output.txt"
OUTCOME_COUNTS = {"passed": "passed", "failed": "failed", "error": "errors", "skipped": "skipped"}

# Repository-owned pytest hooks written next to the tests; they record one outcome per test as JSON.
CONFTEST = '''import json

_outcomes = {}


def pytest_runtest_logreport(report):
    name = report.nodeid.split("::")[-1]
    if report.when == "call":
        _outcomes[name] = report.outcome
    elif report.outcome == "failed":
        _outcomes[name] = "error"
    elif report.outcome == "skipped" and report.when == "setup":
        _outcomes[name] = "skipped"


def pytest_sessionfinish(session, exitstatus):
    with open("report.json", "w", encoding="utf-8") as fh:
        json.dump([{"name": n, "outcome": o} for n, o in _outcomes.items()], fh)
'''


def _limit_resources() -> None:  # runs in the child between fork and exec
    import resource

    lim = config.SANDBOX
    cpu = int(lim["exec_timeout_s"]) + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_AS, (lim["address_space_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (lim["max_file_bytes"],) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (lim["max_open_files"],) * 2)
    resource.setrlimit(resource.RLIMIT_NPROC, (lim["max_processes"],) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _parse_report(path: Path) -> tuple[dict, list[dict]]:
    counts = {"tests": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    tests = []
    try:
        if path.stat().st_size > config.SANDBOX["max_file_bytes"]:
            return counts, tests
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return counts, tests
    if not isinstance(raw, list):
        return counts, tests
    for item in raw:
        if not isinstance(item, dict) or item.get("outcome") not in OUTCOME_COUNTS:
            continue
        counts["tests"] += 1
        counts[OUTCOME_COUNTS[item["outcome"]]] += 1
        tests.append({"name": str(item.get("name", ""))[:200], "outcome": item["outcome"]})
    return counts, tests


def _read_tail(path: Path, max_bytes: int) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            return fh.read(max_bytes).decode("utf-8", "replace")
    except OSError:
        return ""


def run_candidate(task_id: str, candidate_id: str, variant: str, fixtures_root: Path | None = None,
                  tmp_root: Path | None = None) -> dict:
    """Run the fixture's tests against one candidate. Always removes its work directory and child processes."""
    task = fixtures.load_task(task_id, fixtures_root)
    source = fixtures.candidate(task, candidate_id)["source"]
    if variant == "style":
        source = transforms.style_only_variant(source)
    timeout = config.SANDBOX["exec_timeout_s"]
    workdir = Path(tempfile.mkdtemp(prefix="jg-job-", dir=tmp_root))
    proc = None
    started = time.monotonic()
    status, error = "ERROR", None
    try:
        (workdir / "solution.py").write_text(source, encoding="utf-8")
        (workdir / fixtures.TEST_FILE).write_text(fixtures.test_source(task_id, fixtures_root), encoding="utf-8")
        (workdir / "conftest.py").write_text(CONFTEST, encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(workdir), "TMPDIR": str(workdir),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0", "PYTHONUNBUFFERED": "1",
        }
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--color=no",
               fixtures.TEST_FILE]
        with open(workdir / OUTPUT, "wb") as out:
            proc = subprocess.Popen(cmd, cwd=workdir, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=True,
                                    preexec_fn=_limit_resources)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_group(proc.pid)
                proc.wait()
                code = None
        counts, tests = _parse_report(workdir / REPORT)
        if code is None:
            status, error = "TIMEOUT", f"exceeded {timeout}s wall-clock limit"
        elif code == 0 and counts["tests"] > 0 and counts["passed"] == counts["tests"]:
            status = "PASS"
        elif code == 1 and counts["tests"] > 0 and counts["errors"] == 0:
            status = "FAIL"
        else:
            status, error = "ERROR", f"pytest exit code {code}"
        output_tail = _read_tail(workdir / OUTPUT, config.SANDBOX["max_output_bytes"])
    except Exception as exc:  # the worker must survive any single job
        counts, tests, output_tail = {}, [], ""
        status, error = "ERROR", f"runner_failure:{type(exc).__name__}"
    finally:
        if proc is not None:
            _kill_group(proc.pid)  # also removes any children the tests left behind
            if proc.poll() is None:
                proc.wait()
        shutil.rmtree(workdir, ignore_errors=True)
    return {
        "task_id": task_id, "candidate_id": candidate_id, "variant": variant, "status": status,
        "counts": counts, "tests": tests, "duration_s": round(time.monotonic() - started, 3),
        "output_tail": output_tail.replace(str(workdir), "<workdir>"), "error": error,
    }
