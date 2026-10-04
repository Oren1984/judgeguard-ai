import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SANDBOXED = os.environ.get("JG_SANDBOXED") == "1"
SKIP_REASON = "executes fixture code; only runs inside the sandboxed test container (JG_SANDBOXED=1)"


@pytest.fixture
def require_sandbox():
    if not SANDBOXED:
        pytest.skip(SKIP_REASON)


@pytest.fixture
def exchange(tmp_path):
    jobs_dir, results_dir = tmp_path / "jobs", tmp_path / "results"
    jobs_dir.mkdir()
    results_dir.mkdir()
    return jobs_dir, results_dir


def make_fixture_root(root: Path, task_id: str, c1: str, c2: str, test: str) -> Path:
    """Build a throwaway fixtures directory holding one test-owned task."""
    task_dir = root / "tasks" / task_id
    task_dir.mkdir(parents=True)
    ids = [f"{task_id}-c1", f"{task_id}-c2"]
    (root / "manifest.json").write_text(json.dumps({"fixtures_version": "test", "tasks": [task_id]}))
    (task_dir / "task.json").write_text(json.dumps({
        "id": task_id, "title": task_id, "function": "f", "spec": "test fixture",
        "candidates": [{"id": ids[0], "file": "candidate_1.py", "summary": ""},
                       {"id": ids[1], "file": "candidate_2.py", "summary": ""}],
        "style_target": ids[0], "rubric_evidence": {}, "evidence_notes": "",
        "covered_cases": [], "not_covered": [],
    }))
    (task_dir / "candidate_1.py").write_text(c1)
    (task_dir / "candidate_2.py").write_text(c2)
    (task_dir / "test_task.py").write_text(test)
    return root
