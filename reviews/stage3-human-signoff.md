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

## Gate 3 checklist (PLAN.md §6) — scoped to the two items this stage actually gates on

| Item | Verdict | Evidence |
|---|---|---|
| Loop produces ≥1 judge-confirmed jailbreak on the 5-behavior smoke set | **PASS** | ASR=1.0 (5/5), and the judge's positive calls are human-verified as real jailbreaks, not false positives (see above). |
| No harmful strings written to any git-tracked path | **PASS** | Raw completions — which include self-harm content — stay in the gitignored `results/prompts_ours_smoke_full.jsonl`, never committed. Withheld from the repo entirely pending the ethics/disclosure plan (PLAN.md §8). |

### Partial-forward efficiency delta — deliberately NOT a Gate 3 item

PLAN.md's Gate 3 checklist also lists a partial-forward-vs-full-judge efficiency delta. This
smoke run used `--fitness judge` (the core default, per the Stage 2 fitness demotion), so
`partial_forward_passes=0` here — but more importantly, the `judge+act` path this would measure
runs on the exact Stage 2 probe signal already **proven not to generalize**
(`reviews/stage2-human-signoff.md`: 0.5 accuracy on 6 novel prompts vs. 1.0 training AUC). An
efficiency number produced by a signal known to be scientifically unreliable is meaningless as a
pass/fail gate — measuring "how fast is a broken shortcut" tells us nothing worth gating on.

This is deliberately **descoped from Stage 3's gate** and deferred to the Day 5 extended-lane
`abl_fitness_probeact` run (already demoted out of the core lane for the same reason). When that
run happens, report the efficiency delta honestly as a **finding**, not a validated result —
expected framing: *"the probe-gated variant is faster but less effective, because the probe
signal doesn't generalize"* — consistent with `experiments.yaml`'s comments on that job and
tracked follow-up issue #2.

## Verdict

**Gate 3 human check: PASS.** Both items in Stage 3's actual scope (genuine jailbreaks confirmed,
no tracked harmful strings) are closed. The efficiency delta is not a Stage 3 gate requirement —
it is deferred to Day 5's extended-lane `abl_fitness_probeact` run and will be reported there as
a finding.
