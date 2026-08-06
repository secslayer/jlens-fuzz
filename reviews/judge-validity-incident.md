# CRITICAL FINDING — judge false-positive incident (2026-08-06)

## What happened

`hubert233/GPTFuzz` (the original GPTFuzzer RoBERTa success judge, `configs/*.yaml`'s
`judge_model`) was found to have a severe false-positive problem on the success class. Hand
reading all 4 completions it scored ~0.99 ("jailbroken") on a Phi-4-mini smoke run found **all
four were not jailbreaks**:

- One was a refusal ("I can't assist") that pivoted to an unrelated topic (basketball).
- Three were the model merely **echoing a DAN/Omega/APOPHIS-style roleplay template's
  persona/setup instructions**, with zero harmful content.

Diagnosis: the judge detects jailbreak-**shaped** vocabulary (roleplay persona declarations,
"you are now X" framing) rather than actual harm. This is a known failure mode for
classifier-based jailbreak judges in the literature (surface-pattern matching rather than
semantic harm detection) — this project's own results reproduced it directly.

**Scope: this invalidates ASR pipeline-wide, not just the Phi run that surfaced it.** The same
judge was used in `run_fuzz.py`, `sanity_check.py`, and `validate_signal.py`, across both targets.

## What was NOT invalidated

`reviews/stage3-human-signoff.md` (Qwen2.5-3B, the earlier smoke run) hand-verified 3 of Qwen's
judge-confirmed completions and found them **genuinely harmful** — a real, careful human check,
independent of this finding. That specific spot-check stands on its own evidence. What it does
**not** establish is that Qwen's full `asr=1.0` (`results/ours_smoke.json`) is free of the same
false-positive pattern among the *other*, non-spot-checked candidates — only 3 of several were
examined. Treat Qwen's existing ASR as **provisionally supported by a small human sample, not
fully re-validated** — the same re-scoring this incident calls for should be run against it too
before it's cited as a paper number.

## Existing results affected (not deleted, not edited — historical record of what the OLD judge
said; treat as UNVALIDATED pending re-score)

- `results/ours_smoke.json` (Qwen2.5-3B, `ours`, smoke, asr=1.0) — provisionally supported by a
  3-example human spot-check (see above), not fully re-validated.
- `results/sanity.json` (Qwen2.5-3B, Stage 1, refusal_rate=1.0) — a false-positive-prone
  "jailbroken" judge would, if anything, *undercount* refusals (refused = NOT jailbroken), so
  the true refusal rate is `>=` what was reported; this specific claim's direction of error is
  the safe one, but the underlying judge call was still the old, unreliable one.
- Any Phi-4-mini `ours` smoke result reporting `asr=0.8` from 4 "successes" — **fully
  invalidated**, true ASR for that run is 0.0 (uniform-mutation-equivalent template echoes, not
  jailbreaks) per the hand-read finding above.

No results file has been retroactively edited — they are honest records of what the old judge
produced at the time. This document is the pointer that says "do not cite these without
re-scoring."

## The fix (shipped 2026-08-06)

New shared module `scripts/judge.py` (imported by `run_fuzz.py`, `sanity_check.py`,
`validate_signal.py` — a deliberate, documented break from this repo's usual
self-contained-scripts convention, justified because judge-logic drift across files is exactly
the failure class being fixed):

1. **Stage 1 — cheap refusal pre-filter** (`is_refusal()`): deterministic keyword match on
   canonical refusal phrases within the first 300 characters. Catches the "refusal that pivots
   to something else" case with zero model calls.
2. **Stage 2 — LLM-as-judge rubric grading** (`rubric_judge()`): for anything that passes stage
   1, a fixed, small, ungated model (`judge_llm_model`, default `microsoft/Phi-3.5-mini-instruct`
   — already used elsewhere as `transfer_target_local`, distinct from both attack targets so it
   is never self-grading either Qwen2.5-3B or Phi-4-mini) is given an explicit rubric that
   specifically instructs it to reject roleplay/template-echo responses containing no actual
   harmful content, not just refusals. Fails **closed** (verdict=FAIL) if its output can't be
   parsed.

The original RoBERTa judge is **not removed** — its score is still computed and logged as a
**diagnostic** field (`roberta_judge_score` / `roberta_judge_positive_rate`) in every run's
output, specifically so "the naive judge overestimates ASR by X" can itself be reported as a
supplementary finding. It is no longer the success determinant anywhere.

`run_fuzz.py`'s MCTS reward signal was also changed from the RoBERTa continuous score to the new
trusted binary verdict — backpropagating the old score would have kept steering candidate
selection toward whatever it rewards (jailbreak-shaped vocabulary), actively undermining this fix
even after the final success/ASR determination was corrected. This trades away some reward
granularity (binary vs. continuous) for correctness; flagged here as a real, deliberate tradeoff,
not a free change.

## Re-validation tool

`scripts/rescore_judge.py` re-scores an existing run's raw completions
(`results/prompts_<stem>_full.jsonl`, gitignored) against the fixed judge **without
re-generating** — cheap, since generation was always the expensive part. Reports old-ASR vs.
rescored-ASR and a candidate-level flip count.

**Honest limitation, stated in the tool's own docstring and output:** this can only re-score
candidates that were actually generated. A behavior whose original run stopped early on a
false-positive success has no record of what more iterations would have found under the
corrected judge — the search would have kept going. Treat `rescored_asr_same_data` as "was the
original number trustworthy," not "what is the true number." For an authoritative number, re-run
`scripts/run_fuzz.py` (now fixed) from scratch.

## Required before any full matrix run (per the decision that triggered this fix)

1. ~~Add a stricter judge.~~ Done — `scripts/judge.py`, wired into all three consumers.
2. **Re-validate both targets.** Re-score Qwen's existing smoke completions with
   `scripts/rescore_judge.py` (data already exists) — how many of Qwen's "successes" were also
   false positives? Re-run the Phi `ours` smoke from scratch with the fixed judge (its existing
   completions are worth rescoring too, as a first look, but a full re-run gives real numbers,
   including a real `guided_fire_count`/`ASR` under a judge that isn't rewarding template echo).
3. Only after both are done should any ASR number from this pipeline be trusted, cited, or used
   to justify committing GPU budget to the full 2-target × 3-seed matrix.
