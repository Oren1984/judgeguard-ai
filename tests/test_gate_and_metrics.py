from judgeguard import experiment, fixtures, gate, metrics


def evidence(task, s1, s2, style=None, drop=None):
    c1, c2 = (c["id"] for c in task["candidates"])
    ev = {c1: {"base": {"status": s1, "counts": {}, "tests": []}},
          c2: {"base": {"status": s2, "counts": {}, "tests": []}}}
    target = task["style_target"]
    ev[target]["style"] = {"status": style or ev[target]["base"]["status"], "counts": {}, "tests": []}
    if drop:
        del ev[drop[0]][drop[1]]
    return ev


def case(task_id, judge_id, s1, s2, **kw):
    task = fixtures.load_task(task_id)
    return experiment.build_case(task, judge_id, evidence(task, s1, s2, **kw), "run-test", "test", "test")


def test_preference_handles_every_pairing():
    pref = gate.test_preference
    assert pref({"a": "PASS", "b": "FAIL"}) == {"kind": gate.CLEAR, "preferred": "a"}
    assert pref({"a": "FAIL", "b": "PASS"}) == {"kind": gate.CLEAR, "preferred": "b"}
    assert pref({"a": "PASS", "b": "PASS"})["kind"] == gate.BOTH_PASS
    assert pref({"a": "FAIL", "b": "FAIL"})["kind"] == gate.BOTH_FAIL
    for bad in ("TIMEOUT", "ERROR", "MISSING", "REJECTED"):
        assert pref({"a": "PASS", "b": bad})["kind"] == gate.UNAVAILABLE


def test_order_dependent_decision_routes_to_review_and_keeps_the_judgment():
    rec = case("chunk_list", "position_biased", "PASS", "FAIL")
    assert rec["gate"]["status"] == gate.HUMAN_REVIEW
    assert rec["gate"]["reason_codes"] == ["ORDER_DEPENDENT", "PREFERS_FAILING_CANDIDATE"]
    assert rec["conditions"]["original"]["judgment"]["winner"] == "chunk_list-c1"
    assert rec["conditions"]["swapped"]["judgment"]["winner"] == "chunk_list-c2"
    assert rec["flags"] == {"order_stable": False, "style_sensitive": False, "agrees_with_tests": True}


def test_preferring_a_failing_candidate_routes_to_review():
    rec = case("flatten", "rubric_based", "FAIL", "PASS")
    assert rec["gate"]["reason_codes"] == ["PREFERS_FAILING_CANDIDATE"]
    assert rec["flags"]["agrees_with_tests"] is False


def test_consistent_correct_decision_is_auto_accepted():
    rec = case("clamp", "rubric_based", "PASS", "FAIL")
    assert rec["gate"]["status"] == gate.AUTO_ACCEPT and rec["gate"]["reasons"] == []


def test_consistent_tie_is_auto_accepted_but_never_counts_as_agreement():
    both_pass = case("word_count", "rubric_based", "PASS", "PASS")
    assert both_pass["gate"]["status"] == gate.AUTO_ACCEPT
    assert both_pass["flags"]["agrees_with_tests"] is None
    clear = case("word_count", "rubric_based", "PASS", "FAIL")
    assert clear["gate"]["status"] == gate.AUTO_ACCEPT
    assert clear["flags"]["agrees_with_tests"] is False


def test_missing_judge_evidence_routes_to_review():
    rec = case("safe_divide", "rubric_based", "PASS", "PASS")
    assert rec["gate"]["reason_codes"] == ["MISSING_EVIDENCE"]
    assert rec["flags"]["order_stable"] is None and rec["flags"]["style_sensitive"] is None


def test_missing_timeout_and_error_test_results_route_to_review():
    assert "MISSING_EVIDENCE" in case("clamp", "rubric_based", "PASS", "MISSING")["gate"]["reason_codes"]
    assert "MISSING_EVIDENCE" in case("clamp", "rubric_based", "PASS", "REJECTED")["gate"]["reason_codes"]
    assert "TIMEOUT" in case("clamp", "rubric_based", "PASS", "TIMEOUT")["gate"]["reason_codes"]
    assert "EXECUTION_ERROR" in case("clamp", "rubric_based", "ERROR", "PASS")["gate"]["reason_codes"]
    dropped = case("clamp", "rubric_based", "PASS", "FAIL", drop=("clamp-c2", "style"))
    assert dropped["gate"]["reason_codes"] == ["MISSING_EVIDENCE"]


def test_style_variant_changing_test_outcome_is_flagged():
    rec = case("clamp", "rubric_based", "PASS", "FAIL", style="PASS")
    assert "TRANSFORM_INVARIANT_VIOLATED" in rec["gate"]["reason_codes"]


def test_style_sensitivity_alone_is_reported_but_does_not_route():
    rec = case("word_count", "style_biased", "PASS", "PASS")
    assert rec["flags"]["style_sensitive"] is True
    assert rec["gate"]["status"] == gate.AUTO_ACCEPT


def test_metric_denominators():
    records = [
        case("clamp", "rubric_based", "PASS", "FAIL"),         # clear, agrees, auto
        case("flatten", "rubric_based", "FAIL", "PASS"),       # clear, disagrees, review
        case("word_count", "rubric_based", "PASS", "PASS"),    # both pass, tie, auto
        case("median", "rubric_based", "FAIL", "FAIL"),        # both fail, auto
        case("gcd", "rubric_based", "PASS", "TIMEOUT"),        # unavailable, review
        case("safe_divide", "rubric_based", "PASS", "PASS"),   # no decision, review
    ]
    m = metrics.summarize(records)
    assert m["cases"] == 6
    assert (m["test_agreement"]["num"], m["test_agreement"]["den"]) == (1, 2)
    assert m["test_agreement"]["excluded"] == {"both_pass": 2, "both_fail": 1, "unavailable": 1}
    assert (m["order_stability"]["num"], m["order_stability"]["den"]) == (5, 5)
    assert m["order_stability"]["excluded_no_decision"] == 1
    assert (m["style_sensitivity"]["num"], m["style_sensitivity"]["den"]) == (0, 5)
    assert (m["human_review_routing"]["num"], m["human_review_routing"]["den"]) == (3, 6)
    assert m["human_review_routing"]["rate"] == 0.5
    assert m["auto_accept"]["num"] == 3
    assert m["auto_accept"]["agreeing_with_tests"] == 1
    assert m["auto_accept"]["without_clear_test_preference"] == 2
    assert m["reason_counts"] == {"MISSING_EVIDENCE": 1, "PREFERS_FAILING_CANDIDATE": 1, "TIMEOUT": 1}


def test_empty_denominator_gives_no_rate():
    m = metrics.summarize([case("word_count", "rubric_based", "PASS", "PASS")])
    assert m["test_agreement"]["den"] == 0 and m["test_agreement"]["rate"] is None


def test_execution_summary_counts_each_execution_once_across_judges():
    records = [case("gcd", j, "PASS", "TIMEOUT") for j in ("rubric_based", "style_biased", "position_biased")]
    summary = metrics.execution_summary(records)
    assert summary["executions"] == 3
    assert summary["by_status"] == {"PASS": 2, "TIMEOUT": 1}
    assert (summary["timeouts"], summary["failures"]) == (1, 0)


def test_digest_ignores_run_identity_and_timing():
    a = case("clamp", "rubric_based", "PASS", "FAIL")
    b = dict(case("clamp", "rubric_based", "PASS", "FAIL"), run_id="other", case_id="x", created_at="later")
    assert experiment.digest([a]) == experiment.digest([b])
    assert experiment.digest([a]) != experiment.digest([case("clamp", "rubric_based", "FAIL", "PASS")])
