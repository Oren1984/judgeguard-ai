"""Loading and validation of repository-owned fixtures. Only IDs listed in the manifest are usable."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config

TASK_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
FILE_RE = re.compile(r"^candidate_[12]\.py$")
TEST_FILE = "test_task.py"


class FixtureError(ValueError):
    pass


def load_manifest(root: Path | None = None) -> dict:
    root = root or config.fixtures_dir()
    with open(root / "manifest.json", encoding="utf-8") as fh:
        manifest = json.load(fh)
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not all(isinstance(t, str) and TASK_ID_RE.match(t) for t in tasks):
        raise FixtureError("manifest.tasks must be a list of valid task ids")
    if len(set(tasks)) != len(tasks):
        raise FixtureError("manifest.tasks contains duplicates")
    return manifest


def task_ids(root: Path | None = None) -> list[str]:
    return list(load_manifest(root)["tasks"])


def load_task(task_id: str, root: Path | None = None) -> dict:
    """Return a validated task with candidate sources attached. Unknown IDs are rejected."""
    root = root or config.fixtures_dir()
    if not isinstance(task_id, str) or task_id not in load_manifest(root)["tasks"]:
        raise FixtureError(f"unknown task id: {task_id!r}")
    task_dir = root / "tasks" / task_id
    with open(task_dir / "task.json", encoding="utf-8") as fh:
        task = json.load(fh)
    if task.get("id") != task_id:
        raise FixtureError(f"{task_id}: task.json id mismatch")
    cands = task.get("candidates")
    if not isinstance(cands, list) or len(cands) != 2:
        raise FixtureError(f"{task_id}: exactly two candidates are required")
    expected_ids = [f"{task_id}-c1", f"{task_id}-c2"]
    if [c.get("id") for c in cands] != expected_ids:
        raise FixtureError(f"{task_id}: candidate ids must be {expected_ids}")
    for cand in cands:
        if not FILE_RE.match(cand.get("file", "")):
            raise FixtureError(f"{task_id}: bad candidate file name")
        cand["source"] = (task_dir / cand["file"]).read_text(encoding="utf-8")
    if task.get("style_target") not in expected_ids:
        raise FixtureError(f"{task_id}: style_target must be a candidate id")
    if not (task_dir / TEST_FILE).is_file():
        raise FixtureError(f"{task_id}: missing {TEST_FILE}")
    if not isinstance(task.get("rubric_evidence"), dict):
        raise FixtureError(f"{task_id}: rubric_evidence must be an object")
    return task


def candidate(task: dict, candidate_id: str) -> dict:
    for cand in task["candidates"]:
        if cand["id"] == candidate_id:
            return cand
    raise FixtureError(f"unknown candidate id: {candidate_id!r}")


def other_candidate_id(task: dict, candidate_id: str) -> str:
    ids = [c["id"] for c in task["candidates"]]
    return ids[1] if candidate_id == ids[0] else ids[0]


def test_source(task_id: str, root: Path | None = None) -> str:
    root = root or config.fixtures_dir()
    return (root / "tasks" / task_id / TEST_FILE).read_text(encoding="utf-8")
