"""Paired experiment: original order, swapped order and a style-only variant, for one task and one judge."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone

from . import config, fixtures, gate, judges, transforms

RECORD_SCHEMA = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"


def collect_evidence(client, task: dict, run_id: str) -> dict:
    """Run the fixture tests for both base candidates and the style variant through the sandbox worker."""
    evidence = {c["id"]: {"base": client.run(run_id, task["id"], c["id"], "base")} for c in task["candidates"]}
    target = task["style_target"]
    evidence[target]["style"] = client.run(run_id, task["id"], target, "style")
    return evidence


def build_case(task: dict, judge_id: str, evidence: dict, run_id: str, kind: str, fixtures_version: str) -> dict:
    """Judge the three conditions, apply the review gate and assemble the audit record."""
    started = time.monotonic()
    conditions, judgments = {}, {}
    for condition in gate.CONDITIONS:
        presented = transforms.presented_sources(task, condition)
        judgment = judges.run_judge(judge_id, task, presented)
        judgments[condition] = judgment
        statuses = gate.statuses_for(task, evidence, condition)
        conditions[condition] = {
            "display_order": [p["candidate_id"] for p in presented],
            "transformations": transforms.transformations(task, condition),
            "judgment": judgment,
            "test_statuses": statuses,
            "test_preference": gate.test_preference(statuses),
        }
    keys = {c: judges.outcome_key(judgments[c]) for c in gate.CONDITIONS}
    pref = conditions["original"]["test_preference"]
    decided = keys["original"] is not None
    flags = {
        "order_stable": None if not decided or keys["swapped"] is None else keys["original"] == keys["swapped"],
        "style_sensitive": None if not decided or keys["style"] is None else keys["original"] != keys["style"],
        "agrees_with_tests": None if pref["kind"] != gate.CLEAR else keys["original"] == pref["preferred"],
    }
    return {
        "record_type": "case",
        "schema_version": RECORD_SCHEMA,
        "mock": True,
        "run_id": run_id,
        "run_kind": kind,
        "case_id": f"{run_id}:{task['id']}:{judge_id}",
        "created_at": utc_now(),
        "versions": config.versions(fixtures_version),
        "task_id": task["id"],
        "judge_id": judge_id,
        "candidate_ids": [c["id"] for c in task["candidates"]],
        "style_target": task["style_target"],
        "conditions": conditions,
        "test_evidence": evidence,
        "flags": flags,
        "gate": gate.evaluate(task, judgments, evidence),
        "timings": {
            "judging_s": round(time.monotonic() - started, 4),
            "test_execution_s": round(sum(r.get("duration_s") or 0 for v in evidence.values() for r in v.values()), 3),
        },
    }


def run_experiment(client, run_id: str, task_ids: list[str], judge_ids: list[str], kind: str,
                   progress=None) -> list[dict]:
    """Run tests once per task, then judge with every requested judge. Returns case records."""
    fixtures_version = fixtures.load_manifest()["fixtures_version"]
    records = []
    for index, task_id in enumerate(task_ids):
        task = fixtures.load_task(task_id)
        evidence = collect_evidence(client, task, run_id)
        records.extend(build_case(task, j, evidence, run_id, kind, fixtures_version) for j in judge_ids)
        if progress:
            progress(index + 1, len(task_ids), task_id)
    return records


def run_suite(client, run_id: str, progress=None) -> list[dict]:
    return run_experiment(client, run_id, fixtures.task_ids(), list(config.JUDGE_IDS), "suite", progress)


def canonical(records: list[dict]) -> list[dict]:
    """Records reduced to their deterministic content: no run IDs, timestamps, durations or raw output."""
    out = []
    for rec in sorted(records, key=lambda r: (r["task_id"], r["judge_id"])):
        out.append({
            "task_id": rec["task_id"], "judge_id": rec["judge_id"], "versions": rec["versions"],
            "conditions": rec["conditions"], "flags": rec["flags"],
            "gate": {"status": rec["gate"]["status"], "reason_codes": rec["gate"]["reason_codes"]},
            "test_evidence": {cid: {v: {"status": r["status"], "counts": r["counts"], "tests": r["tests"]}
                                    for v, r in variants.items()}
                              for cid, variants in rec["test_evidence"].items()},
        })
    return out


def digest(records: list[dict]) -> str:
    blob = json.dumps(canonical(records), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
