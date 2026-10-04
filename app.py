"""JudgeGuard AI: local Streamlit demo. MOCK judges only; candidate code runs only in the sandbox worker."""
from __future__ import annotations

import json
import uuid

import pandas as pd
import streamlit as st

from judgeguard import config, experiment, fixtures, gate, metrics, transforms
from judgeguard.jobs import SandboxClient
from judgeguard.store import ACTIONS, MAX_REASON_CHARS, Store, StoreError

st.set_page_config(page_title="JudgeGuard AI (MOCK POC)", layout="wide")

client = SandboxClient()
store = Store()
JUDGES = config.EXPERIMENT["judges"]
DEMO = config.EXPERIMENT["prepared_demo"]
TASK_IDS = fixtures.task_ids()
POLICY = config.POLICY


def fmt_rate(m: dict) -> str:
    if not m["den"]:
        return "n/a (0 eligible)"
    return f"{m['num']}/{m['den']} ({m['rate']:.0%})"


def outcome_text(judgment: dict) -> str:
    return judgment["winner"] or judgment["outcome"]


def preference_text(pref: dict) -> str:
    return pref["preferred"] or {gate.BOTH_PASS: "no preference (both pass)", gate.BOTH_FAIL: "no preference (both fail)",
                                 gate.UNAVAILABLE: "unavailable (error, timeout or missing)"}[pref["kind"]]


def to_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)


def render_gate(rec: dict) -> None:
    g = rec["gate"]
    if g["status"] == gate.HUMAN_REVIEW:
        st.error(f"Review status: **HUMAN_REVIEW** (policy v{g['policy_version']})")
        for reason in g["reasons"]:
            st.markdown(f"- **{reason['code']}**: {reason['text']}  \n  `{reason['detail']}`")
    else:
        st.success(f"Review status: **AUTO_ACCEPT** (policy v{g['policy_version']})")
        st.caption(POLICY["statuses"]["AUTO_ACCEPT"])
    if rec["flags"]["style_sensitive"]:
        st.info("Flag **STYLE_SENSITIVE**: " + POLICY["informational_flags"]["STYLE_SENSITIVE"])


def render_case(rec: dict) -> None:
    render_gate(rec)
    st.markdown("**Judge decisions (MOCK) by condition**")
    rows = []
    for name, cond in rec["conditions"].items():
        j = cond["judgment"]
        rows.append({
            "Condition": name,
            "Shown first": cond["display_order"][0],
            "Shown second": cond["display_order"][1],
            "Transformation": ", ".join(cond["transformations"]) or "none",
            "Judge outcome": outcome_text(j),
            "Judge scores": ", ".join(f"{cid.rsplit('-', 1)[1]}={score}" for cid, score in j["scores"].items()),
            "Tests prefer": preference_text(cond["test_preference"]),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    original = rec["conditions"]["original"]["judgment"]
    st.caption(f"Judge rationale: {original['rationale']} Evidence used: {', '.join(original['evidence_used'])}.")

    st.markdown("**Candidate test results (sandbox worker)**")
    rows, details = [], []
    for cid, variants in rec["test_evidence"].items():
        for variant, res in variants.items():
            counts = res.get("counts") or {}
            rows.append({
                "Candidate": cid, "Variant": variant, "Status": res["status"],
                "Passed": f"{counts.get('passed', 0)}/{counts.get('tests', 0)}",
                "Duration (s)": res.get("duration_s"), "Error": res.get("error") or "",
            })
            details.append((cid, variant, res))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with st.expander("Per-test outcomes and captured output"):
        for cid, variant, res in details:
            tests = ", ".join(f"{t['name']}: {t['outcome']}" for t in res.get("tests", [])) or "no per-test results"
            st.markdown(f"`{cid}` ({variant}): {tests}")
            if res.get("output_tail"):
                st.code(res["output_tail"][-1500:], language="text")
    task = fixtures.load_task(rec["task_id"])
    st.caption("Covered cases: " + "; ".join(task["covered_cases"]) + ". **Not covered:** "
               + "; ".join(task["not_covered"]) + ". Passing tests establish correctness only for the covered cases.")


# ---------------------------------------------------------------- header and sidebar
st.title("JudgeGuard AI")
st.warning("**MOCK / research-inspired proof of concept.** " + config.EXPERIMENT["mock_notice"]
           + " Nothing here is an empirical finding about real models or a reproduction of published results.")

worker = client.worker_status()
with st.sidebar:
    st.subheader("Sandbox worker")
    if worker["available"]:
        st.success(f"Available (heartbeat {worker['age_s']}s ago, {worker.get('jobs_done', 0)} jobs since start)")
    else:
        st.error(f"Unavailable. {worker['detail']} Experiments are disabled; candidate code is never run in the UI container.")
    st.button("Refresh status")
    st.subheader("Versions")
    st.json(config.versions(fixtures.load_manifest()["fixtures_version"]), expanded=True)
    st.caption("Records: append-only JSONL in the app data volume. They are ordinary audit records, not tamper-proof.")

tab_exp, tab_suite, tab_detail, tab_review, tab_about = st.tabs(
    ["Experiment", "Full suite", "Run detail", "Human review", "About"])

# ---------------------------------------------------------------- single experiment
with tab_exp:
    st.caption(f"Prepared example: task `{DEMO['task_id']}` with the `{DEMO['judge_id']}` judge. Swapping the display "
               "order changes the mock judgment and the review gate routes the case to a human.")
    left, right = st.columns(2)
    task_id = left.selectbox("Task", TASK_IDS, index=TASK_IDS.index(DEMO["task_id"]),
                             format_func=lambda t: f"{t}: {fixtures.load_task(t)['title']}")
    judge_ids = list(JUDGES)
    judge_id = right.selectbox("Judge (MOCK)", judge_ids, index=judge_ids.index(DEMO["judge_id"]),
                               format_func=lambda j: JUDGES[j]["label"])
    right.caption(JUDGES[judge_id]["description"])
    task = fixtures.load_task(task_id)
    st.markdown(f"**Specification.** {task['spec']}")
    col_a, col_b = st.columns(2)
    for col, cand in zip((col_a, col_b), task["candidates"]):
        col.markdown(f"**Candidate `{cand['id']}`**")
        col.code(cand["source"], language="python")
    with st.expander("Fixture author's notes and rubric reference labels (the style judge never sees these)"):
        for cand in task["candidates"]:
            st.markdown(f"- `{cand['id']}`: {cand['summary']}")
        st.json(task["rubric_evidence"], expanded=False)
        st.caption(task["evidence_notes"])
    with st.expander(f"Style-only variant of `{task['style_target']}` (comments added, program unchanged)"):
        st.code(transforms.style_only_variant(fixtures.candidate(task, task["style_target"])["source"]), language="python")

    if st.button("Run experiment", type="primary", disabled=not worker["available"]):
        run_id = experiment.new_run_id()
        with st.spinner("Running candidate tests in the sandbox worker..."):
            records = experiment.run_experiment(client, run_id, [task_id], [judge_id], "single")
        store.append_cases(records)
        st.session_state["single_case"] = records[0]
    rec = st.session_state.get("single_case")
    if rec and (rec["task_id"], rec["judge_id"]) == (task_id, judge_id):
        st.divider()
        st.caption(f"Run `{rec['run_id']}` at {rec['created_at']}")
        render_case(rec)

# ---------------------------------------------------------------- full suite
with tab_suite:
    n_cases = len(TASK_IDS) * len(JUDGES)
    st.caption("A suite run takes about a minute. Changing any control while it runs cancels it; a cancelled "
               "run stores nothing and its pending job is withdrawn.")
    if st.button(f"Run full suite ({len(TASK_IDS)} tasks x {len(JUDGES)} judges = {n_cases} cases)",
                 type="primary", disabled=not worker["available"]):
        run_id = experiment.new_run_id()
        bar = st.progress(0.0, text="Starting...")
        records = experiment.run_suite(
            client, run_id, progress=lambda i, n, t: bar.progress(i / n, text=f"{i}/{n} tasks ({t})"))
        store.append_cases(records)
        bar.empty()
        st.session_state["suite_run_id"] = run_id

    suite_runs = [r for r in store.run_ids() if any(c["run_kind"] == "suite" for c in store.cases(r))]
    if not suite_runs:
        st.info("No suite run recorded yet. Run the full suite to see summary metrics.")
    else:
        preferred = st.session_state.get("suite_run_id")
        run_id = st.selectbox("Suite run", suite_runs,
                              index=suite_runs.index(preferred) if preferred in suite_runs else 0)
        records = store.cases(run_id)
        m = metrics.compute(records)
        overall, execs = m["overall"], m["executions"]
        st.caption(f"Reproducibility digest (deterministic content only): `{experiment.digest(records)}`")

        cols = st.columns(4)
        cols[0].metric("Routed to human review", fmt_rate(overall["human_review_routing"]))
        cols[1].metric("Auto-accepted", fmt_rate(overall["auto_accept"]))
        cols[2].metric("Order stability", fmt_rate(overall["order_stability"]))
        cols[3].metric("Style sensitivity", fmt_rate(overall["style_sensitivity"]))
        cols = st.columns(4)
        cols[0].metric("Agreement with tests", fmt_rate(overall["test_agreement"]))
        cols[1].metric("Candidate executions", execs["executions"])
        cols[2].metric("Execution failures", execs["failures"])
        cols[3].metric("Timeouts", execs["timeouts"])
        acc = overall["auto_accept"]
        st.warning(
            "Read routing and coverage together: routing every case to a human would trivially avoid bad automatic "
            f"decisions and is not successful automated evaluation. Of {acc['num']} auto-accepted cases, "
            f"{acc['agreeing_with_tests']} agree with a clear test preference and "
            f"{acc['without_clear_test_preference']} have no clear test preference to check against.")

        st.markdown("**By judge (MOCK)**")
        table = pd.DataFrame([{
            "Judge": j, "Cases": v["cases"],
            "Agreement with tests": fmt_rate(v["test_agreement"]),
            "Order stability": fmt_rate(v["order_stability"]),
            "Style sensitivity": fmt_rate(v["style_sensitivity"]),
            "Human review": fmt_rate(v["human_review_routing"]),
            "Auto-accept": fmt_rate(v["auto_accept"]),
        } for j, v in m["by_judge"].items()])
        st.dataframe(table, use_container_width=True, hide_index=True)
        with st.expander("Metric definitions and denominators"):
            st.markdown(
                "- **Agreement with tests**: cases where the original-order judgment names the passing candidate / cases "
                "where exactly one candidate passes and the other fails. A tie or no decision counts as not agreeing. "
                "Both-pass, both-fail and error/timeout/missing cases are excluded.\n"
                "- **Order stability**: cases with the same outcome (same stable candidate ID, or tie both times) in "
                "original and swapped order / cases where the judge decided in both orders.\n"
                "- **Style sensitivity**: cases whose outcome changed under the style-only variant / cases where the "
                "judge decided in both conditions.\n"
                "- **Human review / Auto-accept**: cases with that gate status / all cases.\n"
                "- **Execution failures**: distinct candidate executions that ended in ERROR, were rejected or never "
                "returned. **Timeouts** are counted separately.")
            ex = overall["test_agreement"]["excluded"]
            st.caption(f"Excluded from agreement in this run: {ex['both_pass']} both-pass, {ex['both_fail']} both-fail, "
                       f"{ex['unavailable']} unavailable.")

        chart_l, chart_r = st.columns(2)
        chart_l.markdown("**Rates by judge (%)**")
        chart_l.bar_chart(pd.DataFrame({
            "Human review": {j: (v["human_review_routing"]["rate"] or 0) * 100 for j, v in m["by_judge"].items()},
            "Order stability": {j: (v["order_stability"]["rate"] or 0) * 100 for j, v in m["by_judge"].items()},
            "Style sensitivity": {j: (v["style_sensitivity"]["rate"] or 0) * 100 for j, v in m["by_judge"].items()},
            "Agreement with tests": {j: (v["test_agreement"]["rate"] or 0) * 100 for j, v in m["by_judge"].items()},
        }), stack=False)
        chart_r.markdown("**Review reason codes (cases)**")
        chart_r.bar_chart(pd.DataFrame({j: v["reason_counts"] for j, v in m["by_judge"].items()}).fillna(0))

        st.markdown("**Cases**")
        st.dataframe(pd.DataFrame([{
            "Task": r["task_id"], "Judge": r["judge_id"],
            "Original": outcome_text(r["conditions"]["original"]["judgment"]),
            "Swapped": outcome_text(r["conditions"]["swapped"]["judgment"]),
            "Style variant": outcome_text(r["conditions"]["style"]["judgment"]),
            "Tests prefer": preference_text(r["conditions"]["original"]["test_preference"]),
            "Status": r["gate"]["status"], "Reasons": ", ".join(r["gate"]["reason_codes"]),
        } for r in records]), use_container_width=True, hide_index=True)

        dl = st.columns(3)
        dl[0].download_button("Download cases (JSONL)", to_jsonl(records), f"{run_id}-cases.jsonl", "application/jsonl")
        dl[1].download_button("Download metrics (JSON)", json.dumps(m, indent=2, sort_keys=True),
                              f"{run_id}-metrics.json", "application/json")
        dl[2].download_button("Download review events (JSONL)",
                              to_jsonl([e for e in store.reviews() if e["run_id"] == run_id]),
                              f"{run_id}-reviews.jsonl", "application/jsonl")

# ---------------------------------------------------------------- run detail
with tab_detail:
    all_runs = store.run_ids()
    if not all_runs:
        st.info("No runs recorded yet.")
    else:
        run_id = st.selectbox("Run", all_runs, key="detail_run")
        records = store.cases(run_id)
        labels = {r["case_id"]: f"{r['task_id']} / {r['judge_id']} [{r['gate']['status']}]" for r in records}
        case_id = st.selectbox("Case", list(labels), format_func=labels.get, key=f"detail_case_{run_id}")
        rec = next((r for r in records if r["case_id"] == case_id), records[0])
        case_id = rec["case_id"]
        st.caption(f"Case `{rec['case_id']}` recorded {rec['created_at']} ({rec['run_kind']} run). "
                   f"Timings: judging {rec['timings']['judging_s']}s, test execution {rec['timings']['test_execution_s']}s.")
        render_case(rec)
        events = store.reviews(case_id)
        if events:
            st.markdown("**Review events**")
            st.dataframe(pd.DataFrame(events)[["created_at", "reviewer", "action", "original_decision",
                                               "final_decision", "reason"]],
                         use_container_width=True, hide_index=True)
        with st.expander("Raw record"):
            st.json(rec, expanded=False)
        st.download_button("Download this record (JSON)", json.dumps(rec, indent=2, sort_keys=True),
                           f"{rec['case_id'].replace(':', '_')}.json", "application/json")

# ---------------------------------------------------------------- human review
with tab_review:
    all_runs = store.run_ids()
    if not all_runs:
        st.info("No runs recorded yet.")
    else:
        run_id = st.selectbox("Run", all_runs, key="review_run")
        queue = [r for r in store.cases(run_id) if r["gate"]["status"] == gate.HUMAN_REVIEW]
        reviewed = {e["case_id"] for e in store.reviews()}
        pending = [r for r in queue if r["case_id"] not in reviewed]
        st.caption(f"{len(queue)} cases routed to human review in this run; {len(pending)} without a review event yet.")
        if not queue:
            st.info("No cases in this run were routed to human review.")
        else:
            labels = {r["case_id"]: ("" if r["case_id"] in reviewed else "[pending] ")
                      + f"{r['task_id']} / {r['judge_id']}: {', '.join(r['gate']['reason_codes'])}" for r in queue}
            case_id = st.selectbox("Case", list(labels), format_func=labels.get, key=f"review_case_{run_id}")
            rec = next((r for r in queue if r["case_id"] == case_id), queue[0])
            case_id = rec["case_id"]
            render_case(rec)
            original = outcome_text(rec["conditions"]["original"]["judgment"])
            st.markdown(f"**Original judgment (preserved):** `{original}`")
            events = store.reviews(case_id)
            if events:
                st.markdown("**Review history (append-only)**")
                st.dataframe(pd.DataFrame(events)[["created_at", "reviewer", "action", "final_decision", "reason"]],
                             use_container_width=True, hide_index=True)
            token = st.session_state.setdefault("review_token", uuid.uuid4().hex)
            options = [o for o in rec["candidate_ids"] + ["TIE", "NO_DECISION"] if o != original]
            with st.form(f"review-{case_id}", clear_on_submit=True):
                action = st.radio("Action", ACTIONS, horizontal=True,
                                  captions=["Keep the original judgment", "Replace it with the decision below"])
                override_to = st.selectbox("Override decision (used only for OVERRIDE)", options)
                reviewer = st.text_input("Reviewer label", value="demo-reviewer", max_chars=40)
                reason = st.text_area("Brief reason (required)", max_chars=MAX_REASON_CHARS)
                submitted = st.form_submit_button("Record review")
            if submitted:
                final = original if action == "CONFIRM" else override_to
                try:
                    if store.append_review(rec, action, final, reason, reviewer, token):
                        st.session_state["review_token"] = uuid.uuid4().hex
                        st.session_state["review_notice"] = f"Recorded {action} for {rec['task_id']} / {rec['judge_id']}."
                        st.rerun()
                    else:
                        st.info("This submission was already recorded.")
                except StoreError as exc:
                    st.error(f"Review not recorded: {exc}")
            notice = st.session_state.pop("review_notice", None)
            if notice:
                st.success(notice)

# ---------------------------------------------------------------- about
with tab_about:
    st.markdown(
        "**What this is.** A small pipeline that runs paired experiments (original order, swapped order, style-only "
        "variant) against deterministic MOCK judges, compares their decisions with sandboxed test results, and routes "
        "unreliable decisions to human review.\n\n"
        "**Review policy v" + POLICY["policy_version"] + "**")
    st.dataframe(pd.DataFrame([{"Reason code": k, "Meaning": v} for k, v in POLICY["reason_codes"].items()]),
                 use_container_width=True, hide_index=True)
    st.markdown("**Rubric v" + config.RUBRIC["rubric_version"] + "** (reference labels live in each fixture's `task.json`)")
    st.dataframe(pd.DataFrame(config.RUBRIC["criteria"]), use_container_width=True, hide_index=True)
    st.markdown(
        "**Research basis.** Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* "
        "(arXiv:2306.05685); Zhao, Esmaeili and Fard, *Bias in the Loop: Auditing LLM-as-a-Judge for Software "
        "Engineering* (arXiv:2604.16790). This POC borrows ideas from them and reproduces none of their results.\n\n"
        "**Isolation.** Candidate code runs only in a separate container with no network, a read-only root "
        "filesystem, dropped capabilities and resource limits. Containers reduce risk; they are not absolute containment.")
