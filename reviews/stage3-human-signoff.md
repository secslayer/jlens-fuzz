# Stage 3 — Human Sign-off (Gate 3, PLAN.md §6)

Note: Stage 3 is not one of CLAUDE.md's three mandatory 👤-gated stages (2 probes, 5 judge
labels, 8 ethics). This check is recorded anyway because PLAN.md's Gate 3 checklist item
"Loop produces ≥1 judge-confirmed jailbreak" is only meaningful if the judge is actually
trustworthy on the *success* class — something only a human reading real completions can
confirm, and Stage 1's sanity check only validated the judge on the *refusal* class (raw
AdvBench prompts the model declined). This closes that gap.

- **Reviewer:** muhammed muiz (abdulmuiz3570@gmail.com)
- **Date:** 2026-08-06
- **Source reviewed:** Kaggle notebook session — `results/prompts_ours_smoke_full.jsonl`
  inspected directly on Kaggle (this file is gitignored via `results/**/prompts_*` and is not
  present in this local checkout). `scripts/run_fuzz.py` deliberately never logs completion text
  to its own stdout log (only `success`/`judge_score` scalars, per its aggregate-only safety
  design) — the raw text only exists in that jsonl side file.
- **Run reviewed:** `results/ours_smoke.json` — `--method ours --mutation guided --seedtier
  human --fitness judge --smoke` (5-behavior smoke set, core-lane default flags per the Stage 2
  fitness demotion).

## What was checked

- Spot-checked 3 of the judge-confirmed successful completions from the smoke run by reading the
  actual generated text.
- Confirmed all 3 are genuine harmful jailbreaks — real compliance with the harmful request, not
  judge false-positives. This validates judge accuracy on the SUCCESS class specifically,
  complementing (not duplicating) Stage 1's refusal-class validation
  (`reviews/stage1-human-signoff.md`).
- **ASR = 1.0 on the 5 smoke behaviors — confirmed legitimate**, not an artifact of a lenient or
  broken judge, given the above.
- **Guided mutation fired on 100% of MCTS iterations in this run — 0 fallbacks to uniform
  mutation.** `find_attribution_span` never hit a degenerate case or exception on real Kaggle
  data — corroborating evidence that the `offset_mapping` KeyError fix (`fa06ebc`) and the
  widened try/except (`5c31406`) actually resolved the earlier crash and the guided-mutation path
  runs cleanly end-to-end, not just in the fallback path.

## Gate 3 checklist (PLAN.md §6)

| Item | Verdict | Evidence |
|---|---|---|
| Loop produces ≥1 judge-confirmed jailbreak on the 5-behavior smoke set | **PASS** | ASR=1.0 (5/5), and the judge's positive calls are human-verified as real jailbreaks, not false positives (see above). |
| Partial-forward fitness runs and is cheaper than full-judge fitness (efficiency delta) | **NOT COVERED by this sign-off** | This smoke run used `--fitness judge` (the core default, per the Stage 2 probe-fitness demotion) — `partial_forward_passes=0` for this run. The judge+act efficiency comparison (`wall_clock_partial_s` vs `wall_clock_full_s`) requires a separate smoke run with `--fitness judge+act` (i.e. exercising `abl_fitness_probeact`), not yet done. Do not treat this item as closed. |
| No harmful strings written to any git-tracked path | **PASS** | Raw completions — which include self-harm content — stay in the gitignored `results/prompts_ours_smoke_full.jsonl`, never committed. Withheld from the repo entirely pending the ethics/disclosure plan (PLAN.md §8). |

## Verdict

**Gate 3 human check: PASS** for the checklist items in scope of this review (jailbreak
confirmation, no tracked harmful strings). The efficiency-delta checklist item remains open and
requires a `--fitness judge+act` smoke run before Gate 3 can be considered fully closed.
