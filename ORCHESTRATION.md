# ORCHESTRATION.md — coordinating the full matrix without losing your place

This upgrades the linear runbook into a **dependency-aware, resumable job queue**. It exists
because the expanded plan (RQ1–4, Components 1–4, seed tiers, transfer, defenses, extra baselines)
is too many runs to track by hand on a platform whose sessions die every ~12h. Read this with
`PLAN.md` (gates) and `RUNBOOK.md` (clicks); this file governs *what runs when*.

## What changed and why

Before: you ran scripts one by one and remembered what was done. If a Kaggle commit died at hour
10 of a 12h matrix, you lost the thread.

Now: `experiments.yaml` declares each run as a **job** (deps + the output file that proves it's
done + its command). `scripts/run_controller.py` infers status *purely from which output files
exist on disk*, computes the ready set that respects dependencies, and prints the exact Kaggle
launch lines for the next batch — packed onto your budget (2 GPUs × 2 commit notebooks). Because
state lives in the result files, **any machine can ask "what's left?" and get the right answer**,
and a dead session costs nothing. `scripts/run_experiment.py` dispatches one job id;
`run_parallel.sh` runs two (one per GPU); `run_controller.py` tells you which two.

Daily loop is now just: `/orchestrate core` → paste the emitted lines into the commit notebooks →
push results → `/orchestrate core` again.

## The DAG (core lane = 1 week)

```
probes ─┐
        ├─► validate ─┐
direction ┘            │
                       ├─────────────────────────────► figures ─► paper
gptfuzzer ─────────────┤                                  ▲
                       │                                   │
probes+direction ─► ours ─► transfer_k3 ───────────────────┤
              ├─► abl_mut_uniform  (RQ1: guided vs uniform) ┤
              ├─► abl_seed_bootstrap (RQ2 tier b) ──────────┤
              └─► abl_seed_random   (RQ2 tier c, headline) ─┘
```

`gptfuzzer` has no internal-signal dependency, so it launches immediately in parallel with
`probes`/`direction` — free parallelism the controller exploits automatically.

**EXTENDED lane (after the preprint):** `autodan`, `amnesia`, `gcg`, `pair` baselines;
`abl_fitness_judgeonly` (Component 4); layer sweep; `transfer_llama/mistral` (RQ3);
`defense_ppl/smoothllm` (RQ4). Declared in the manifest with `lane: extended`; the controller
ignores them until you pass `--lane all`.

## Two signals, two jobs (reconciling probes and directions)

The pasted plan and my scaffold use different internal signals; they are **complementary**, so we
keep both:

- **`probes`** → a logistic refusal probe = the **fitness classifier** (how close is a candidate
  to refusal, on a partial forward pass). Cheap dense score for selection.
- **`direction`** → a difference-in-means refusal direction (Amnesia-style) = the **token
  attribution** signal (project each token's activation onto it → which span is *pulling* the
  model toward refusal). This is what tells the mutator **where** to mutate.

That split is exactly Components 2→3→4 of the pasted plan, made concrete.

## Script interfaces (what `builder` must implement)

The manifest calls these with specific flags — argparse must match:

- **`extract_direction.py`** `--config --out results/direction.npz` — difference-in-means refusal
  direction per layer from harmful vs. benign activations; save all layers + the chosen one.
- **`validate_signal.py`** `--config` → `results/validate_signal.json` — correlation between probe
  score / direction-projection and *actual* refusal on a held-out set (RQ interpretability
  evidence AND a sanity gate: if there's no correlation, the method has no basis).
- **`run_fuzz.py`** `--config --method {ours,gptfuzzer,autodan} --mutation {guided,uniform}
  --seedtier {human,bootstrap,random} --fitness {judge,judge+act}` → `results/<method|abl>.json`.
  - `ours + guided`: token-attribution picks the top-k span; the mutator LLM rewrites *only that
    span* ("reduce refusal-triggering framing, preserve intent"). Component 3.
  - `uniform`: same loop, mutate the whole prompt (GPTFuzzer default) — the RQ1 ablation.
  - `seedtier`: human CSV / model-bootstrapped / random innocuous — the RQ2 tiers (Component 1).
  - `fitness`: RoBERTa-judge only, or judge + activation term — the Component 4 ablation.
  - Reuse GPTFuzzer's MCTS selection unchanged; the novelty is the mutation *location* and the
    fitness *signal*, which makes the ablations clean.
- **`transfer_blackbox.py`** `--config --from results/ours.json --local [--target <hf_id>]`
  — replay optimized prompts against a SECOND small open-weight model on Kaggle (default
  `transfer_target_local` from config, e.g. Phi-3.5-mini). No external API.
- **`make_figures.py` / `assemble_paper.py`** — read only `results/*.json`; emit the 7
  figures/tables and the draft. No number without a backing file.

Every one writes the `_provenance` block (git sha from `$JLENS_GIT`, job from `$JLENS_JOB`,
config hash, timestamp).

## Claude Code roles (the orchestration agents)

- **`builder`** subagent — implements ONE script per invocation to the `train_probes.py` bar, then
  stops and asks for review. Prevents half-finished multi-script sprawl.
- **`reviewer`** subagent — adversarial gate after each stage (`/review N`), fresh context.
- **`/orchestrate [core|all]`** — runs the controller, shows the next batch, flags stuck jobs.

Loop: `builder` writes a script → `/review` its stage → push → `/orchestrate` → launch the batch
on Kaggle → push results → `/orchestrate` again. The human gates (probes AUC, judge labels,
ethics) still require your sign-off.

## Mapping to Kaggle limits (why this fits)

- 2 GPUs/session × (1 interactive + 2 commit) ⇒ controller packs the ready set into ≤2 commit
  notebooks of 2 jobs each per round; the interactive bench stays free for dev/monitoring.
- 30 GPU-hr/week is the real ceiling. The core lane is ~10 jobs; on a 3B model with a 50-behavior
  budget, smoke-test every job at 5 behaviors first (`--smoke`) — the controller/​manifest keep
  full and smoke outputs distinct so a smoke run never marks a job "done".
- Resumability means you can spread the matrix across several days without a scheduler or a
  babysat session.

## Honest scope line

The full pasted matrix (6 models × 6 baselines × defenses × tiers) is a multi-month paper, not a
week. The **core lane is the preprint**: one white-box model, GPTFuzzer baseline, the RQ1 mutation
ablation, the RQ2 seed-tier ablation (headline), K3 transfer, and the signal-validation evidence.
Everything else is `extended` — real and wired, but off the critical path. If the 30-hr quota
tightens, cut in this order: abl_seed_bootstrap (keep human + random as the two RQ2 endpoints),
then autodan (GPTFuzzer alone is a sufficient baseline for a preprint).
