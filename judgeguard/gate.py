"""Transparent review gate. Routes a case to HUMAN_REVIEW or AUTO_ACCEPT and records why."""
from __future__ import annotations

from . import config, fixtures, judges

AUTO_ACCEPT = "AUTO_ACCEPT"
HUMAN_REVIEW = "HUMAN_REVIEW"
CONDITIONS = ("original", "swapped", "style")

CLEAR = "CLEAR"
BOTH_PASS = "BOTH_PASS"
BOTH_FAIL = "BOTH_FAIL"
UNAVAILABLE = "UNAVAILABLE"


def statuses_for(task: dict, evidence: dict, condition: str) -> dict:
    """Test status per candidate as presented in a condition (the style target uses its style-variant run)."""
    out = {}
    for cand in task["candidates"]:
        cid = cand["id"]
        variant = "style" if condition == "style" and cid == task["style_target"] else "base"
        result = evidence.get(cid, {}).get(variant)
        out[cid] = result["status"] if isinstance(result, dict) and "status" in result else "MISSING"
    return out


def test_preference(statuses: dict) -> dict:
    """What the tests say about a pair. Only PASS-versus-FAIL establishes a clear preference."""
    (a, sa), (b, sb) = statuses.items()
    if {sa, sb} == {"PASS", "FAIL"}:
        return {"kind": CLEAR, "preferred": a if sa == "PASS" else b}
    if sa == sb == "PASS":
        return {"kind": BOTH_PASS, "preferred": None}
    if sa == sb == "FAIL":
        return {"kind": BOTH_FAIL, "preferred": None}
    return {"kind": UNAVAILABLE, "preferred": None}


def _reason(code: str, detail: str) -> dict:
    return {"code": code, "text": config.POLICY["reason_codes"][code], "detail": detail}


def evaluate(task: dict, judgments: dict, evidence: dict) -> dict:
    """Apply review policy. `judgments` maps condition -> judgment; `evidence` maps candidate -> variant -> result."""
    reasons = []
    seen = set()

    def add(code: str, detail: str) -> None:
        if (code, detail) not in seen:
            seen.add((code, detail))
            reasons.append(_reason(code, detail))

    expected = [(c["id"], "base") for c in task["candidates"]] + [(task["style_target"], "style")]
    for cid, variant in expected:
        result = evidence.get(cid, {}).get(variant)
        status = result.get("status", "MISSING") if isinstance(result, dict) else "MISSING"
        label = f"{cid} ({variant})"
        if status == "TIMEOUT":
            add("TIMEOUT", f"{label}: tests timed out")
        elif status == "ERROR":
            add("EXECUTION_ERROR", f"{label}: {result.get('error') or 'execution error'}")
        elif status not in ("PASS", "FAIL"):
            error = result.get("error") if isinstance(result, dict) else None
            add("MISSING_EVIDENCE", f"{label}: no usable test result ({error or status})")

    target = task["style_target"]
    base, styled = (evidence.get(target, {}).get(v) for v in ("base", "style"))
    if (isinstance(base, dict) and isinstance(styled, dict)
            and {base.get("status"), styled.get("status")} <= {"PASS", "FAIL"}
            and base.get("status") != styled.get("status")):
        add("TRANSFORM_INVARIANT_VIOLATED", f"{target}: base={base['status']} style={styled['status']}")

    for condition in CONDITIONS:
        judgment = judgments.get(condition)
        if judgment is None or judgment["outcome"] == judges.NO_DECISION:
            missing = "; ".join(judgment["missing_evidence"]) if judgment else "no judgment recorded"
            add("MISSING_EVIDENCE", f"judge ({condition}): {missing}")

    keys = {c: judges.outcome_key(judgments[c]) if judgments.get(c) else None for c in CONDITIONS}
    if keys["original"] is not None and keys["swapped"] is not None and keys["original"] != keys["swapped"]:
        add("ORDER_DEPENDENT", f"original order -> {keys['original']}; swapped order -> {keys['swapped']}")

    for condition in CONDITIONS:
        winner = judgments[condition]["winner"] if judgments.get(condition) else None
        if winner is None:
            continue
        statuses = statuses_for(task, evidence, condition)
        other = fixtures.other_candidate_id(task, winner)
        if statuses[winner] == "FAIL" and statuses[other] == "PASS":
            add("PREFERS_FAILING_CANDIDATE", f"{condition}: chose {winner} (tests FAIL) over {other} (tests PASS)")

    return {
        "status": HUMAN_REVIEW if reasons else AUTO_ACCEPT,
        "reasons": reasons,
        "reason_codes": sorted({r["code"] for r in reasons}),
        "policy_version": config.POLICY["policy_version"],
    }
