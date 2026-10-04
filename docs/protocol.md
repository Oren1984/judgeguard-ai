# Experiment protocol, metrics and review policy

Versions in force: fixtures 1.0.0, config 1.0.0, rubric 1.0.0, review policy 1.0.0. All four are
written into every case record.

## Fixtures

Each task in `fixtures/tasks/<task>/` has a specification, two candidates with stable IDs
(`<task>-c1`, `<task>-c2`), a pytest file, rubric reference labels, and a list of what the tests cover
and do not cover. All data is synthetic.

| Task | c1 | c2 | Purpose |
| --- | --- | --- | --- |
| clamp | pass | fail | Wrong candidate is better presented |
| is_palindrome | fail | pass | Edge-case bug in the first-shown candidate |
| dedupe_preserve_order | pass | fail | Core requirement missed |
| chunk_list | pass | fail | **Prepared demo**: edge-case bug within the position bonus |
| word_count | pass | pass | Both correct: tests give no preference |
| median | fail | fail | Both wrong: tests give no preference |
| gcd | pass | timeout | Infinite loop exercises the sandbox timeout |
| parse_kv | error | pass | Import-time failure exercises execution-error handling |
| flatten | fail | pass | **Deliberately wrong reference label** for c1 |
| safe_divide | pass | pass | **Deliberately missing reference labels** for c2 |
| roman_to_int | fail | pass | Terse wrong answer that style decoration promotes |
| merge_intervals | pass | fail | Edge-case bug; style decoration promotes the wrong answer |
| running_total | fail | pass | Contract violation (mutates its input) |

The expected outcomes above are asserted by the project tests from `tests/expected_outcomes.json`, a
file no judge reads.

## Conditions

| Condition | Display order | Source shown |
| --- | --- | --- |
| `original` | c1, c2 | base |
| `swapped` | c2, c1 | base |
| `style` | c1, c2 | the fixture's `style_target` candidate gets the style-only variant |

**Stable identity.** Judges return the winner's candidate ID, never "first" or "second", and all
comparisons use IDs. A swap therefore cannot create disagreement by itself.

**Style-only variant.** `transforms.style_only_variant` prepends a six-line comment banner and adds a
comment above each `return`. It raises unless the parsed program (`ast.dump`) is identical to the
original. The variant is also executed in the sandbox, and a differing test status raises the
`TRANSFORM_INVARIANT_VIOLATED` reason. The style target is fixed per fixture in `task.json`: the
failing candidate where exactly one candidate fails its tests (dressing up the wrong answer), and the
working candidate in the timeout and import-error tasks so the variant can actually be executed.

Nothing is randomised. Order, transformations, judges and fixtures are fixed, and candidate tests run
with `PYTHONHASHSEED=0`.

## Mock judges

All three are pure functions of `(task, candidates in display order)`. None receives test results.

- **`position_biased`**: rubric score, plus 2.5 for the candidate shown first. Its choice flips under a
  swap whenever the rubric gap is 2 points or less.
- **`style_biased`**: `1.0 x comment lines + 2.0 x has docstring + 1.0 x has type hints +
  0.1 x non-blank lines` of the displayed source. Uses no rubric evidence.
- **`rubric_based`**: sum of rubric weights for criteria marked satisfied.

Equal scores give `TIE`. Missing rubric evidence gives `NO_DECISION`.

### Rubric v1.0.0 and its evidence

| Criterion | Weight |
| --- | --- |
| `core_behavior`: implements the main behaviour in the specification | 3 |
| `edge_cases`: handles the edge cases named in the specification | 2 |
| `input_contract`: respects the stated input/output contract | 1 |
| `clarity`: readable names and structure | 1 |

**Judge evidence and test evidence are separate.** The rubric judge reads only `rubric_evidence` in
each `task.json`: true/false reference labels per candidate, written by hand from reading the code and
keyed by candidate ID. It does not see pytest outcomes. Because the labels are keyed by ID, the rubric
judge is order- and style-invariant by construction; that is a property of the mock, not a finding.

The labels were written by the same author as the tests, so they are correlated with test outcomes
without being derived from them. Two fixtures are intentionally imperfect, and say so in their
`evidence_notes`:

- `flatten`: c1 is labelled as satisfying everything although it fails deep nesting. This simulates an
  annotator missing a defect.
- `safe_divide`: c2 has no labels at all.

## Test evidence

Each execution ends in one status: `PASS` (all tests pass), `FAIL` (at least one assertion fails),
`ERROR` (tests could not run to completion), `TIMEOUT`, or on the app side `MISSING` / `REJECTED`.

Per pair, tests establish a **clear preference** only when one candidate is `PASS` and the other `FAIL`.
Both-pass, both-fail, and any pair involving an error, timeout or missing result give no preference.
Passing tests establish correctness only for the cases the fixture lists as covered.

## Review policy v1.0.0

All rules are evaluated and every matching reason is recorded.

| Reason code | Fires when |
| --- | --- |
| `ORDER_DEPENDENT` | The judge decided in both orders and the outcomes differ (winner vs. other winner, or winner vs. tie) |
| `PREFERS_FAILING_CANDIDATE` | In any of the three conditions the judge's winner is `FAIL` while the other candidate is `PASS` |
| `MISSING_EVIDENCE` | The judge returned no decision in any condition, or a required test result is missing or rejected |
| `EXECUTION_ERROR` | A required execution ended in `ERROR` |
| `TIMEOUT` | A required execution timed out |
| `TRANSFORM_INVARIANT_VIOLATED` | The style variant's test status differs from the base candidate's |

Any reason gives `HUMAN_REVIEW`. No reason gives `AUTO_ACCEPT`.

`AUTO_ACCEPT` means only that no rule fired. In particular:

- A judge that consistently ties is auto-accepted.
- A case where both candidates fail, or both pass, is auto-accepted if the judge is order-consistent,
  because there is no failing-over-passing preference to detect.
- **Style sensitivity alone does not route.** It is recorded as the informational flag
  `STYLE_SENSITIVE` and reported as a metric. It routes only when the style-condition winner fails
  tests while the other candidate passes.

### Human review

A reviewer picks a case, chooses `CONFIRM` or `OVERRIDE`, and must give a reason of 1 to 280 characters.
Each submission appends one event to `reviews.jsonl` with the original decision, the final decision,
the reviewer label and a timestamp. The case record and its judgment are never modified, and a case can
accumulate several events. Each form carries a one-time token; a repeated token is ignored, so browser
reruns do not duplicate reviews.

## Metrics

Computed per judge and overall. Every rate is shown as numerator/denominator.

| Metric | Numerator | Denominator |
| --- | --- | --- |
| Agreement with tests | Cases whose original-order winner is the passing candidate | Cases with a clear test preference |
| Order stability | Cases with the same outcome in both orders (same ID, or tie both times) | Cases where the judge decided in both orders |
| Style sensitivity | Cases whose outcome differs between original and style conditions | Cases where the judge decided in both |
| Human-review routing | Cases with `HUMAN_REVIEW` | All cases |
| Auto-accept | Cases with `AUTO_ACCEPT` | All cases |
| Execution failures | Distinct executions that are `ERROR`, `MISSING` or `REJECTED` | reported as a count |
| Timeouts | Distinct executions that are `TIMEOUT` | reported as a count |

Edge handling:

- **Ties and no-decisions with a clear test preference** count as *not agreeing*.
- **Both-pass, both-fail and unavailable pairs** are excluded from agreement and counted separately.
- **No decision** in either condition excludes the case from stability and sensitivity, with the
  exclusion count reported.
- **A zero denominator** yields no rate ("n/a"), never 0% or 100%.
- **Executions** are counted once per run, task, candidate and variant, although three judges share them.
- Auto-accepted cases are broken down into those agreeing with a clear test preference and those with
  no clear preference.

Routing and coverage are always shown together. A policy that sent every case to a human would score
perfectly on "no bad automatic decisions" while automating nothing.

## Reproducibility

`experiment.digest` hashes the deterministic content of a run: judgments, display orders, gate status
and reason codes, flags, and per-test outcomes. It excludes run IDs, timestamps, durations and captured
output. Two runs of the same versions should produce the same digest.
