# Stage 2 — Human Sign-off (Gate 2, PLAN.md §6) — MAKE-OR-BREAK GATE

- **Reviewer:** muhammed muiz (abdulmuiz3570@gmail.com)
- **Date:** 2026-08-05
- **Artifacts reviewed:** `results/probes/best_layer.json`, `results/probes/probe_best_layer.npz`,
  `results/direction.npz` (commit `a2323e3`, Kaggle bench run), and the output of
  `scripts/probe_novel_check.py` run against 6 hand-authored novel prompts (3 conversationally-
  phrased harmful, 3 benign imperatives — not included here per `.gitignore`'s
  `results/**/prompts_*` exclusion / CLAUDE.md golden rule 1).

## Gate 2 checklist (PLAN.md §6)

| Item | Verdict | Evidence |
|---|---|---|
| Best-layer held-out AUC ≥ 0.85 | **PASS (both signals)** | Probe: layer 9/36, AUC 1.0 (`results/probes/best_layer.json`). Direction: layer 25/36, AUC 1.0 (`results/direction.npz`). |
| Chosen layer in a sensible mid/late band, not layer 0 | **PASS (direction), MARGINAL (probe)** | Direction's layer 25/36 (~69% depth) is solidly mid/late. Probe's layer 9/36 (~25% depth) is early — not layer 0/1, so it doesn't trip the literal "leakage" flag, but in hindsight this is plausibly *why* the probe overfit a lexical/surface confound rather than a deeper semantic "harmfulness" representation (see below). Worth revisiting in the follow-up fix. |
| **Probe/direction separates 6 novel hand-written harmful/benign prompts** | **FAIL (probe) / PASS (direction)** | See below. |

## Novel-prompt result (the actual finding)

- **Direction signal: PASS, cleanly.** Harmful prompts projected **+30 avg**, benign **-5 avg** —
  correct separation, and notably robust *despite* a surface-form crossing (the benign novel
  prompts were phrased as imperatives, i.e. surface-similar to AdvBench's harmful phrasing style,
  and the direction still scored them correctly on the harmless side).
- **Probe signal: FAIL, generalization failure.** **0.5 accuracy** (chance) on the 6 novel prompts,
  despite **1.0 held-out AUC** at training time. Diagnosis: the probe overfit a surface confound —
  its held-out split was drawn from the same generating distributions as training (AdvBench
  imperatives = harmful class, Alpaca mixed-form instructions = benign class), so the held-out AUC
  measured "can it tell AdvBench-style phrasing from Alpaca-style phrasing," not "can it tell
  harmful intent from benign intent." The novel prompts (harmful phrased conversationally, benign
  phrased as imperatives — deliberately crossing that confound) exposed it.

This is exactly the failure mode Gate 2's novel-prompt check exists to catch, and exactly why it's
a 👤-mandatory item independent of the AUC number: CLAUDE.md rule 5's AUC≥0.85 hard-stop was not
triggered (both signals cleared it), but the qualitative checklist item makes clear the *probe's*
1.0 AUC was not evidence of real generalization.

## Overall Gate 2 verdict: **PARTIAL PASS — signal-specific**

- **Direction (token-attribution / mutation-targeting signal): PASS.** Cleared for use as the
  guided-mutation mechanism (Component 3) in `run_fuzz.py`.
- **Probe (fitness-classifier signal): FAIL.** Not cleared for use as a fitness signal until fixed
  and re-validated.

## Decisions

1. **Gate 2 recorded PASS on direction, FAIL on probe** (this document is that record).
2. **`run_fuzz.py`'s default fitness is judge-only, not `judge+act`, until the probe is fixed.**
   `experiments.yaml`'s core-lane jobs (`ours`, `abl_mut_uniform`, `abl_seed_bootstrap`,
   `abl_seed_random`) were updated from `--fitness judge+act` to `--fitness judge` (judge-based
   fitness was already validated in Stage 1's sanity check). Probe-based fitness (`judge+act`) is
   demoted to an extended-lane diagnostic job (`abl_fitness_probeact`, replacing the now-redundant
   `abl_fitness_judgeonly`), clearly commented as **not validated — do not report headline numbers
   from it** until the probe-generalization fix lands and this novel check is re-run clean.
   Guided-span mutation itself (Component 3, driven by the direction signal) is unaffected and
   stays the core-lane default — only the fitness *scoring* function changed.
3. **Follow-up tracked**: fix probe generalization by matching the benign training set's surface
   form to AdvBench's imperatives (e.g., benign instructions phrased as imperatives rather than
   Alpaca's mixed conversational/imperative mix), re-run `train_probes.py` and
   `scripts/probe_novel_check.py`, and only re-enable probe-based fitness in the core lane after a
   clean pass. Tracked as a GitHub issue (see repo issue tracker) rather than only in this file, so
   it isn't silently dropped once Stage 2's branch merges.
