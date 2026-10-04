"""Append-only JSONL records for cases and human-review events. Ordinary audit files, not tamper-proof."""
from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from . import config
from .experiment import utc_now

ACTIONS = ("CONFIRM", "OVERRIDE")
MAX_REASON_CHARS = 280
MAX_REVIEWER_CHARS = 40
_lock = threading.Lock()


class StoreError(ValueError):
    pass


class Store:
    def __init__(self, data_dir: Path | None = None):
        self.dir = Path(data_dir or config.data_dir())
        self.cases_path = self.dir / "cases.jsonl"
        self.reviews_path = self.dir / "reviews.jsonl"

    @staticmethod
    def _read(path: Path) -> list[dict]:
        rows = []
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue  # a partially written line is skipped, never repaired in place
                    if isinstance(row, dict):
                        rows.append(row)
        except FileNotFoundError:
            pass
        return rows

    @staticmethod
    def _append(path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def cases(self, run_id: str | None = None) -> list[dict]:
        rows = self._read(self.cases_path)
        return rows if run_id is None else [r for r in rows if r.get("run_id") == run_id]

    def append_cases(self, records: list[dict]) -> int:
        """Append records whose case_id is not stored yet. Returns the number written."""
        with _lock:
            known = {r.get("case_id") for r in self._read(self.cases_path)}
            fresh = []
            for rec in records:
                if rec["case_id"] not in known:
                    known.add(rec["case_id"])
                    fresh.append(rec)
            if fresh:
                self._append(self.cases_path, fresh)
            return len(fresh)

    def run_ids(self) -> list[str]:
        """Run IDs, newest first."""
        seen = {}
        for rec in self.cases():
            seen[rec["run_id"]] = rec.get("created_at", "")
        return sorted(seen, key=lambda r: seen[r], reverse=True)

    def reviews(self, case_id: str | None = None) -> list[dict]:
        rows = self._read(self.reviews_path)
        return rows if case_id is None else [r for r in rows if r.get("case_id") == case_id]

    def append_review(self, case: dict, action: str, final_decision: str, reason: str, reviewer: str,
                      token: str) -> bool:
        """Append one review event. Returns False if this submission token was already recorded."""
        reason, reviewer = reason.strip(), reviewer.strip()
        allowed = list(case["candidate_ids"]) + ["TIE", "NO_DECISION"]
        if action not in ACTIONS:
            raise StoreError("action must be CONFIRM or OVERRIDE")
        if not reason or len(reason) > MAX_REASON_CHARS:
            raise StoreError(f"a reason of 1-{MAX_REASON_CHARS} characters is required")
        if not reviewer or len(reviewer) > MAX_REVIEWER_CHARS:
            raise StoreError(f"a reviewer label of 1-{MAX_REVIEWER_CHARS} characters is required")
        if final_decision not in allowed:
            raise StoreError("final decision must be a candidate of this case, TIE or NO_DECISION")
        original = case["conditions"]["original"]["judgment"]
        original_key = original["winner"] or original["outcome"]
        if action == "CONFIRM" and final_decision != original_key:
            raise StoreError("CONFIRM must keep the original judgment")
        if action == "OVERRIDE" and final_decision == original_key:
            raise StoreError("OVERRIDE must change the original judgment")
        if not token:
            raise StoreError("missing submission token")
        with _lock:
            if any(r.get("token") == token for r in self._read(self.reviews_path)):
                return False
            self._append(self.reviews_path, [{
                "record_type": "review", "review_id": uuid.uuid4().hex, "token": token,
                "case_id": case["case_id"], "run_id": case["run_id"], "created_at": utc_now(),
                "policy_version": case["gate"]["policy_version"], "gate_status": case["gate"]["status"],
                "original_decision": original_key, "action": action, "final_decision": final_decision,
                "reason": reason, "reviewer": reviewer,
            }])
            return True
