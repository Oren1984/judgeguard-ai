"""Summary metrics over case records. Every rate carries its numerator and denominator."""
from __future__ import annotations

from collections import Counter

from . import gate


def _rate(num: int, den: int) -> dict:
    return {"num": num, "den": den, "rate": round(num / den, 4) if den else None}


def summarize(records: list[dict]) -> dict:
    """Metrics for one group of cases (typically one judge within one run)."""
    kinds = Counter(r["conditions"]["original"]["test_preference"]["kind"] for r in records)
    clear = [r for r in records if r["flags"]["agrees_with_tests"] is not None]
    order = [r for r in records if r["flags"]["order_stable"] is not None]
    style = [r for r in records if r["flags"]["style_sensitive"] is not None]
    routed = [r for r in records if r["gate"]["status"] == gate.HUMAN_REVIEW]
    accepted = [r for r in records if r["gate"]["status"] == gate.AUTO_ACCEPT]
    reasons = Counter(code for r in records for code in r["gate"]["reason_codes"])
    return {
        "cases": len(records),
        "test_agreement": {
            **_rate(sum(r["flags"]["agrees_with_tests"] for r in clear), len(clear)),
            "excluded": {"both_pass": kinds[gate.BOTH_PASS], "both_fail": kinds[gate.BOTH_FAIL],
                         "unavailable": kinds[gate.UNAVAILABLE]},
        },
        "order_stability": {**_rate(sum(r["flags"]["order_stable"] for r in order), len(order)),
                            "excluded_no_decision": len(records) - len(order)},
        "style_sensitivity": {**_rate(sum(r["flags"]["style_sensitive"] for r in style), len(style)),
                              "excluded_no_decision": len(records) - len(style)},
        "human_review_routing": _rate(len(routed), len(records)),
        "auto_accept": {
            **_rate(len(accepted), len(records)),
            "with_clear_test_preference": sum(r["flags"]["agrees_with_tests"] is not None for r in accepted),
            "agreeing_with_tests": sum(r["flags"]["agrees_with_tests"] is True for r in accepted),
            "without_clear_test_preference": sum(r["flags"]["agrees_with_tests"] is None for r in accepted),
        },
        "reason_counts": dict(sorted(reasons.items())),
    }


def execution_summary(records: list[dict]) -> dict:
    """Counts of distinct candidate executions (each is shared by all judges of a task within a run)."""
    seen = {}
    for rec in records:
        for cid, variants in rec["test_evidence"].items():
            for variant, result in variants.items():
                seen[(rec["run_id"], rec["task_id"], cid, variant)] = result.get("status", "MISSING")
    counts = Counter(seen.values())
    return {
        "executions": len(seen),
        "by_status": dict(sorted(counts.items())),
        "failures": counts["ERROR"] + counts["MISSING"] + counts["REJECTED"],
        "timeouts": counts["TIMEOUT"],
    }


def compute(records: list[dict]) -> dict:
    judges = sorted({r["judge_id"] for r in records})
    return {
        "mock": True,
        "overall": summarize(records),
        "by_judge": {j: summarize([r for r in records if r["judge_id"] == j]) for j in judges},
        "executions": execution_summary(records),
    }
