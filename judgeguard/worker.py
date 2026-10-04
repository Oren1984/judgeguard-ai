"""Sandbox worker loop: picks up validated job files one at a time and writes result files."""
from __future__ import annotations

import os
import shutil
import signal
import tempfile
import time
from pathlib import Path

from . import config, jobs, sandbox_runner

PARTIAL_GRACE_S = 2.0


class Worker:
    def __init__(self, jobs_dir: Path | None = None, results_dir: Path | None = None,
                 fixtures_root: Path | None = None, tmp_root: Path | None = None):
        self.jobs_dir = Path(jobs_dir or config.jobs_dir())
        self.results_dir = Path(results_dir or config.results_dir())
        self.fixtures_root = fixtures_root
        self.tmp_root = Path(tmp_root or tempfile.gettempdir())
        self.jobs_done = 0
        self.stopping = False

    def heartbeat(self, state: str) -> None:
        jobs.atomic_write_json(self.results_dir / jobs.HEARTBEAT_FILE,
                               {"ts": time.time(), "state": state, "jobs_done": self.jobs_done})

    def clean_tmp(self) -> None:
        """Remove work directories left behind by an interrupted job."""
        for path in self.tmp_root.glob("jg-job-*"):
            shutil.rmtree(path, ignore_errors=True)

    def prune_results(self) -> None:
        now = time.time()
        for path in self.results_dir.iterdir():
            if path.name == jobs.HEARTBEAT_FILE:
                continue
            try:
                if now - path.stat().st_mtime > config.SANDBOX["result_ttl_s"]:
                    path.unlink()
            except OSError:
                pass

    def _write_result(self, job_id: str, body: dict) -> None:
        body = {"schema_version": jobs.SCHEMA_VERSION, "job_id": job_id, "finished_at": time.time(), **body}
        jobs.atomic_write_json(self.results_dir / f"{job_id}.json", body)
        self.jobs_done += 1

    def _reject(self, job_id: str, code: str) -> None:
        self._write_result(job_id, {"task_id": None, "candidate_id": None, "variant": None, "status": "REJECTED",
                                    "counts": {}, "tests": [], "duration_s": None, "output_tail": "", "error": code})

    def process_one(self) -> bool:
        """Handle at most one pending job. Returns True if a result was written."""
        try:
            names = sorted(os.listdir(self.jobs_dir))
        except OSError:
            return False
        for name in names:
            if not jobs.JOB_FILE_RE.match(name):
                continue  # temp files and anything unexpected are ignored
            job_id = name[:-5]
            if (self.results_dir / name).exists():
                continue
            path = self.jobs_dir / name
            raw = jobs.read_json(path, config.SANDBOX["max_job_file_bytes"])
            if raw is None:
                try:
                    age = time.time() - path.stat().st_mtime
                except OSError:
                    continue  # removed by the app in the meantime
                if age < PARTIAL_GRACE_S:
                    continue  # possibly still being written; look again next pass
                self._reject(job_id, "unreadable_job_file")
                return True
            try:
                job = jobs.validate_job(raw, expected_job_id=job_id, fixtures_root=self.fixtures_root)
            except jobs.JobError as exc:
                self._reject(job_id, exc.code)
                return True
            self.heartbeat("busy")
            result = sandbox_runner.run_candidate(job["task_id"], job["candidate_id"], job["variant"],
                                                  fixtures_root=self.fixtures_root, tmp_root=self.tmp_root)
            self._write_result(job_id, result)
            return True
        return False

    def run_forever(self, idle_sleep_s: float = 0.1) -> None:
        self.clean_tmp()
        while not self.stopping:
            self.heartbeat("idle")
            self.prune_results()
            if not self.process_one():
                time.sleep(idle_sleep_s)


def main() -> None:
    worker = Worker()

    def stop(_signum, _frame):
        worker.stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print("judgeguard sandbox worker started", flush=True)
    worker.run_forever()
    print("judgeguard sandbox worker stopped", flush=True)


if __name__ == "__main__":
    main()
