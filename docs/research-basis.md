# Research basis and implementation mapping

Everything in JudgeGuard AI is simulated. This page records which published ideas inspired the design,
what was implemented, and where the POC departs from the sources. No result from either paper is
reproduced here, and no number in this repository should be cited as evidence about real LLM judges.

## Sources and how they were checked

Both sources were retrieved on 2026-10-04.

| | Source 1 | Source 2 |
| --- | --- | --- |
| Title | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | Bias in the Loop: Auditing LLM-as-a-Judge for Software Engineering |
| Authors | Zheng, Chiang, Sheng, Zhuang, Wu, Zhuang, Lin, Li, Li, Xing, Zhang, Gonzalez, Stoica | Zhao, Esmaeili, Fard |
| Link | <https://arxiv.org/abs/2306.05685> | <https://doi.org/10.48550/arXiv.2604.16790> (resolves to arXiv:2604.16790) |
| Status | NeurIPS 2023 Datasets and Benchmarks Track; v4 dated 24 Dec 2023 | arXiv preprint, submitted 18 Apr 2026, cs.SE |

How they were read: the arXiv abstract pages and the arXiv HTML full-text pages were fetched and read
through an automated page-summarisation tool. Abstract-level statements below were checked against the
abstract text. **Section-level details come from that tool's summary of the HTML pages and were not
re-checked line by line against the PDFs**, so verify them in the papers before quoting them elsewhere.

One inconsistency was noticed and is left unresolved: the abstract of source 2 refers to "two pointwise
judging regimes", while its method section, as summarised, describes the judge comparing two candidate
snippets (A and B). This POC uses pairwise comparison and does not depend on which reading is right.

## Ideas taken from the sources

| Idea in the source | Where it appears | What JudgeGuard AI does with it |
| --- | --- | --- |
| Judges can favour a position. Source 1 names position bias among the limitations it examines; source 2 evaluates each item in an original and a swapped presentation. | S1 abstract and section 3; S2 method section | The `swapped` condition and the `position_biased` mock judge. |
| Source 1 measures *consistency*: whether a judge gives the same result when the two answers are swapped. | S1 section 3 | The **order stability** metric. Candidates carry stable IDs so a swap is compared by identity, not by slot. |
| Source 1 describes a conservative approach: call the judge in both orders and only declare a win when the same answer is preferred both times. | S1 section 3.4 | The `ORDER_DEPENDENT` rule. The POC routes the case to a human rather than recording a tie. |
| Source 1 names verbosity bias: favouring longer responses that are not better. Source 2 lists verbosity and style-related cues among the biases it probes. | S1 abstract and section 3; S2 method section | The `style_biased` mock judge and the `style` condition. |
| Source 2 argues that bias sensitivity should be reported alongside accuracy, and that explicit controls such as order swapping should be used. | S2 abstract | Stability and sensitivity are reported next to agreement, each with its denominator. |
| Source 2 uses executable tests as the reference for code tasks and mentions falling back to executable tests and human calibration when judge reliability is low. | S2 method section | Sandboxed tests are the reference signal; the gate falls back to human review. |
| Source 1 describes reference-guided grading. | S1 section 3 | Loosely echoed by the `rubric_based` judge scoring against written reference labels. |

## What was implemented

- Thirteen small Python tasks, each with two candidates, tests, and hand-written rubric reference labels.
- Three deterministic mock judges and three paired conditions per case.
- A review gate with versioned reason codes, an append-only human review step, and summary metrics.
- Test execution in a separate sandbox container.

## What was simplified or changed

- **No model is involved.** The "biases" are a few lines of arithmetic. The position-biased judge adds a
  fixed bonus of 2.5 points to the first-shown candidate; a real judge's order effects are not a
  constant.
- **The style manipulation differs from source 2.** As summarised, source 2 injects one cue at a time
  into the *prompt* while leaving the code unchanged. This POC instead adds comments to the *candidate
  source* and checks that the parsed program and the test outcomes are identical. It is a different
  intervention with a similar intent.
- **Verbosity in source 1 concerns natural-language answers.** Here it is approximated by code comments.
- **Scale.** 13 hand-written tasks and 39 cases. No sampling, no confidence intervals, no difficulty
  strata, no repeated-run consistency measurement (the mock judges are deterministic, so repeating a run
  is uninformative).
- **Self-enhancement bias, limited reasoning ability, and the other biases studied in the sources are
  not modelled.**
- **The human-review gate is this project's own addition.** Neither paper proposes this specific policy.
- **Reference labels are hand-authored and two are deliberately wrong or missing** to exercise the gate
  (see [protocol.md](protocol.md)). They are not a gold standard.
