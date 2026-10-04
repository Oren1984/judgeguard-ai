"""Deterministic MOCK judges. None of them calls a model, and none of them reads test results.

Every judge receives the task and the two candidates in display order and returns a judgment
that names the winner by its stable candidate ID.
"""
from __future__ import annotations

import ast

from . import config

TIE = "TIE"
NO_DECISION = "NO_DECISION"
WINNER = "WINNER"


def rubric_score(task: dict, candidate_id: str) -> tuple[float | None, list[str]]:
    """Score reference labels against the rubric. Returns (score, missing) with score None if incomplete."""
    labels = task["rubric_evidence"].get(candidate_id)
    if not isinstance(labels, dict):
        return None, [f"{candidate_id}: no rubric evidence recorded"]
    missing = [f"{candidate_id}: no label for '{c['id']}'" for c in config.RUBRIC["criteria"]
               if not isinstance(labels.get(c["id"]), bool)]
    if missing:
        return None, missing
    return float(sum(c["weight"] for c in config.RUBRIC["criteria"] if labels[c["id"]])), []


def style_features(source: str) -> dict:
    lines = [ln.strip() for ln in source.splitlines() if ln.strip()]
    tree = ast.parse(source)
    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    return {
        "comment_line": sum(1 for ln in lines if ln.startswith("#")),
        "has_docstring": int(bool(ast.get_docstring(tree)) or any(ast.get_docstring(f) for f in funcs)),
        "has_type_hints": int(any(f.returns or any(a.annotation for a in f.args.args) for f in funcs)),
        "nonblank_line": len(lines),
    }


def style_score(source: str) -> float:
    weights = config.EXPERIMENT["judges"]["style_biased"]["weights"]
    feats = style_features(source)
    return round(sum(weights[k] * feats[k] for k in weights), 4)


def _decide(judge_id: str, scores: dict, missing: list[str], rationale: str, evidence_used: list[str]) -> dict:
    if missing:
        outcome, winner = NO_DECISION, None
        rationale = "No decision: required judge evidence is missing."
    else:
        (a, sa), (b, sb) = scores.items()
        if sa == sb:
            outcome, winner = TIE, None
        else:
            outcome, winner = WINNER, (a if sa > sb else b)
    return {
        "judge_id": judge_id,
        "mock": True,
        "outcome": outcome,
        "winner": winner,
        "scores": scores,
        "rationale": rationale,
        "evidence_used": evidence_used,
        "missing_evidence": missing,
    }


def _rubric_scores(task: dict, presented: list[dict]) -> tuple[dict, list[str]]:
    scores, missing = {}, []
    for item in presented:
        score, gaps = rubric_score(task, item["candidate_id"])
        scores[item["candidate_id"]] = score
        missing.extend(gaps)
    return scores, missing


def judge_rubric(task: dict, presented: list[dict]) -> dict:
    scores, missing = _rubric_scores(task, presented)
    return _decide("rubric_based", scores, missing,
                   "Sum of rubric weights for criteria the reference labels mark as satisfied.",
                   [f"rubric v{config.RUBRIC['rubric_version']}", "fixture reference labels"])


def judge_position(task: dict, presented: list[dict]) -> dict:
    bonus = config.EXPERIMENT["judges"]["position_biased"]["first_position_bonus"]
    scores, missing = _rubric_scores(task, presented)
    if not missing:
        first = presented[0]["candidate_id"]
        scores[first] += bonus
    return _decide("position_biased", scores, missing,
                   f"Rubric score plus a simulated +{bonus} bonus for the candidate displayed first.",
                   [f"rubric v{config.RUBRIC['rubric_version']}", "fixture reference labels", "display position"])


def judge_style(task: dict, presented: list[dict]) -> dict:
    scores = {item["candidate_id"]: style_score(item["source"]) for item in presented}
    return _decide("style_biased", scores, [],
                   "Weighted count of comments, docstrings, type hints and length of the displayed source.",
                   ["displayed source text"])


JUDGES = {
    "position_biased": judge_position,
    "style_biased": judge_style,
    "rubric_based": judge_rubric,
}


def run_judge(judge_id: str, task: dict, presented: list[dict]) -> dict:
    if judge_id not in JUDGES:
        raise ValueError(f"unknown judge id: {judge_id!r}")
    if len(presented) != 2:
        raise ValueError("exactly two candidates must be presented")
    return JUDGES[judge_id](task, presented)


def outcome_key(judgment: dict) -> str | None:
    """Order-independent summary of a judgment: a stable candidate ID, 'TIE', or None for no decision."""
    if judgment["outcome"] == WINNER:
        return judgment["winner"]
    if judgment["outcome"] == TIE:
        return TIE
    return None
