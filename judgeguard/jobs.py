"""File-based job/result exchange between the app and the sandbox worker.

The app writes one small JSON job file per candidate execution into the jobs directory; the
worker writes one JSON result file with the same name into the results directory. Files are
written to a temporary name and renamed, so readers never observe a half-written file under
its final name.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from . import config, fixtures

SCHEMA_VERSION = 1
JOB_FILE_RE = re.compile(r"^[0-9a-f]{32}\.json$")
VARIANTS = ("base", "style")
JOB_KEYS = {"schema_version", "job_id", "created_at", "task_id", "candidate_id", "variant"}
RESULT_STATUSES = ("PASS", "FAIL", "ERROR", "TIMEOUT", "REJECTED")
HEARTBEAT_FILE = "heartbeat.json"


class JobError(ValueError):
    """A job failed validation. `code` is safe to store in a result record."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def make_job_id(run_id: str, task_id: str, candidate_id: str, variant: str) -> str:
    """Deterministic ID: resubmitting the same execution within a run maps to the same files."""
    raw = "\x1f".join((run_id, task_id, candidate_id, variant))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def build_job(run_id: str, task_id: str, candidate_id: str, variant: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": make_job_id(run_id, task_id, candidate_id, variant),
        "created_at": time.time(),
        "task_id": task_id,
        "candidate_id": candidate_id,
        "variant": variant,
    }


def validate_job(job: object, expected_job_id: str | None = None, now: float | None = None,
                 fixtures_root: Path | None = None) -> dict:
    """Validate schema, allow-listed fixture IDs and freshness. Raises JobError."""
    if not isinstance(job, dict) or set(job) != JOB_KEYS:
        raise JobError("invalid_schema")
    if job["schema_version"] != SCHEMA_VERSION:
        raise JobError("unsupported_schema_version")
    job_id = job["job_id"]
    if not isinstance(job_id, str) or not JOB_FILE_RE.match(job_id + ".json"):
        raise JobError("invalid_job_id")
    if expected_job_id is not None and job_id != expected_job_id:
        raise JobError("job_id_mismatch")
    if job["variant"] not in VARIANTS:
        raise JobError("invalid_variant")
    created = job["created_at"]
    if isinstance(created, bool) or not isinstance(created, (int, float)):
        raise JobError("invalid_created_at")
    try:
        task = fixtures.load_task(job["task_id"], fixtures_root)
    except (fixtures.FixtureError, OSError, ValueError):
        raise JobError("unknown_task_id") from None
    if job["candidate_id"] not in [c["id"] for c in task["candidates"]]:
        raise JobError("unknown_candidate_id")
    if job["variant"] == "style" and job["candidate_id"] != task["style_target"]:
        raise JobError("style_variant_not_defined_for_candidate")
    now = time.time() if now is None else now
    if created > now + 60 or now - created > config.SANDBOX["job_ttl_s"]:
        raise JobError("stale_job")
    return job


def atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def read_json(path: Path, max_bytes: int | None = None) -> object | None:
    """Return parsed JSON, or None if the file is missing, too large, or not valid JSON."""
    try:
        if max_bytes is not None and path.stat().st_size > max_bytes:
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def missing_result(task_id: str, candidate_id: str, variant: str, error: str, job_id: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "job_id": job_id, "task_id": task_id, "candidate_id": candidate_id,
        "variant": variant, "status": "MISSING", "counts": {}, "tests": [], "duration_s": None,
        "output_tail": "", "error": error,
    }


class SandboxClient:
    """App-side access to the exchange directories. It never executes candidate code itself."""

    def __init__(self, jobs_dir: Path | None = None, results_dir: Path | None = None, poll_s: float = 0.1):
        self.jobs_dir = Path(jobs_dir or config.jobs_dir())
        self.results_dir = Path(results_dir or config.results_dir())
        self.poll_s = poll_s
        self.submitted = 0

    def worker_status(self) -> dict:
        beat = read_json(self.results_dir / HEARTBEAT_FILE, 4096)
        if not isinstance(beat, dict) or not isinstance(beat.get("ts"), (int, float)):
            return {"available": False, "age_s": None, "detail": "No heartbeat from the sandbox worker."}
        age = max(0.0, time.time() - beat["ts"])
        ok = age <= config.SANDBOX["heartbeat_stale_s"]
        detail = "Sandbox worker is responding." if ok else "Sandbox worker heartbeat is stale."
        return {"available": ok, "age_s": round(age, 1), "detail": detail,
                "jobs_done": beat.get("jobs_done"), "state": beat.get("state")}

    def prune_stale_jobs(self) -> int:
        """Remove job files (and leftover temp files) older than the job TTL."""
        removed = 0
        try:
            names = os.listdir(self.jobs_dir)
        except OSError:
            return 0
        for name in names:
            path = self.jobs_dir / name
            try:
                if time.time() - path.stat().st_mtime > config.SANDBOX["job_ttl_s"]:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        return removed

    def _read_result(self, job: dict) -> dict | None:
        res = read_json(self.results_dir / f"{job['job_id']}.json", 1_000_000)
        if res is None:
            return None
        if (not isinstance(res, dict) or res.get("job_id") != job["job_id"]
                or res.get("status") not in RESULT_STATUSES):
            return missing_result(job["task_id"], job["candidate_id"], job["variant"],
                                  "invalid_result_file", job["job_id"])
        return res

    def run(self, run_id: str, task_id: str, candidate_id: str, variant: str) -> dict:
        """Submit one execution and wait for its result. Idempotent per (run, task, candidate, variant)."""
        job = build_job(run_id, task_id, candidate_id, variant)
        validate_job(job)
        existing = self._read_result(job)
        if existing is not None:
            return existing
        if not self.worker_status()["available"]:
            return missing_result(task_id, candidate_id, variant, "worker_unavailable", job["job_id"])
        job_path = self.jobs_dir / f"{job['job_id']}.json"
        try:
            if not job_path.exists():
                atomic_write_json(job_path, job)
                self.submitted += 1
            deadline = time.monotonic() + config.SANDBOX["exec_timeout_s"] + config.SANDBOX["result_wait_margin_s"]
            while time.monotonic() < deadline:
                res = self._read_result(job)
                if res is not None:
                    return res
                time.sleep(self.poll_s)
            return missing_result(task_id, candidate_id, variant, "no_result_before_deadline", job["job_id"])
        except OSError as exc:
            return missing_result(task_id, candidate_id, variant, f"exchange_io_error:{type(exc).__name__}",
                                  job["job_id"])
        finally:
            try:
                job_path.unlink()
            except OSError:
                pass
