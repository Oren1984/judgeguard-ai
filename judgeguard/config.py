"""Static configuration and paths. Locations can be overridden through JG_* environment variables."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import __version__

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str) -> dict:
    with open(ROOT / "config" / name, encoding="utf-8") as fh:
        return json.load(fh)


EXPERIMENT = _load("experiment.json")
RUBRIC = _load("rubric.json")
POLICY = _load("review_policy.json")
SANDBOX = EXPERIMENT["sandbox"]
JUDGE_IDS = tuple(EXPERIMENT["judges"])


def _path(env: str, default: Path) -> Path:
    return Path(os.environ.get(env, str(default)))


def fixtures_dir() -> Path:
    return _path("JG_FIXTURES_DIR", ROOT / "fixtures")


def jobs_dir() -> Path:
    return _path("JG_JOBS_DIR", Path("/exchange/jobs"))


def results_dir() -> Path:
    return _path("JG_RESULTS_DIR", Path("/exchange/results"))


def data_dir() -> Path:
    return _path("JG_DATA_DIR", Path("/data"))


def versions(fixtures_version: str) -> dict:
    return {
        "app": __version__,
        "config": EXPERIMENT["config_version"],
        "fixtures": fixtures_version,
        "rubric": RUBRIC["rubric_version"],
        "review_policy": POLICY["policy_version"],
    }
