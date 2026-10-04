"""Command-line checks that run through the sandbox worker (never on the caller's interpreter).

    python -m judgeguard.cli suite   # full fixture suite, metrics and a reproducibility digest
    python -m judgeguard.cli demo    # prepared example; exits non-zero unless the expected reasons fire
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config, experiment, metrics
from .jobs import SandboxClient
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="judgeguard.cli")
    parser.add_argument("command", choices=("suite", "demo"))
    parser.add_argument("--save", action="store_true", help="append the case records to the JSONL store")
    args = parser.parse_args(argv)

    client = SandboxClient()
    status = client.worker_status()
    if not status["available"]:
        print(json.dumps({"error": "sandbox worker unavailable", "worker": status}))
        return 2
    run_id = experiment.new_run_id()
    if args.command == "suite":
        records = experiment.run_suite(client, run_id)
        out = {"run_id": run_id, "digest": experiment.digest(records), "metrics": metrics.compute(records),
               "cases": [{"task": r["task_id"], "judge": r["judge_id"], "status": r["gate"]["status"],
                          "reasons": r["gate"]["reason_codes"]} for r in records]}
        code = 0
    else:
        demo = config.EXPERIMENT["prepared_demo"]
        records = experiment.run_experiment(client, run_id, [demo["task_id"]], [demo["judge_id"]], "demo")
        rec = records[0]
        ok = rec["gate"]["reason_codes"] == sorted(demo["expected_reasons"])
        out = {"run_id": run_id, "task": rec["task_id"], "judge": rec["judge_id"],
               "winners": {c: v["judgment"]["winner"] for c, v in rec["conditions"].items()},
               "test_statuses": rec["conditions"]["original"]["test_statuses"],
               "gate": rec["gate"], "expected_reasons_fired": ok}
        code = 0 if ok else 1
    if args.save:
        out["saved"] = Store().append_cases(records)
    print(json.dumps(out, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
