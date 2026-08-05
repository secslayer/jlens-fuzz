# CLAUDE.md — jlens-fuzz

## What this project is
Proof-of-concept preprint: interpretability-guided jailbreak fuzzing. We swap GPTFuzzer's
sparse binary fitness for a **refusal-probe fitness on a partial forward pass**, and remove
the human-seed dependence (headline: the **zero-human-seed ablation**). White-box target:
`Qwen2.5-3B-Instruct`. Judge: `hubert233/GPTFuzz` (RoBERTa). Benchmark: 50 AdvBench behaviors.
Everything runs on Kaggle, free — no external APIs. RQ3 transfer replays optimized prompts on a
second small open-weight model locally (e.g. Phi-3.5-mini). No OpenRouter, no Kimi K3.

Read `PLAN.md` for the full stage plan and peer-review gates. Follow it stage by stage.

## Golden rules (do not violate)
1. **Never commit secrets or attack strings.** `.env`, `~/.kaggle/kaggle.json`, and any file
   under `results/**/prompts_*` are `.gitignore`d. Before every commit, grep for accidental
   harmful strings and API keys and abort the commit if found.
2. **Never invent numbers.** Every figure/table value must come from a `results/*.json` file
   produced by an actual run. If a run didn't happen, the number does not exist.
3. **Identical conditions for baselines.** GPTFuzzer/AutoDAN baselines and our method must use
   the *same* target model, judge, 50 behaviors, query budget, and decoding params. Assert the
   config invariants match before any comparison run. We do NOT copy ASR numbers from papers.
4. **Human gates are human.** Stages 2 (probes), 5 (judge labels), and 8 (ethics) require a
   human sign-off (👤). Prepare the artifact for review; do not self-approve these.
5. **Stop at Gate 2 if probe AUC < 0.85.** A weak probe = no signal = no paper. Flag it loudly
   rather than proceeding.

## Repo map
- `PLAN.md` — the plan + gates (source of truth).
- `Makefile` — one target per stage.
- `configs/exp.yaml` — the invariants (model, judge, budget, seed). Everything reads this.
- `scripts/` — stage scripts (`train_probes.py`, loop, metrics, figures, transfer).
- `results/` — one JSON per run; the only input to `make figures`.
- `reviews/` — peer-review logs (`stageN.md`), written by the reviewer subagent.
- `.claude/agents/reviewer.md` — adversarial peer-review subagent.

## Workflow
- Branch per stage (`stage-2-probes`), PR into `main`. Small, verifiable commits.
- Heavy compute runs on Kaggle (headless commit), never in this control session. No paid services.
- After each stage, run `/review` and only advance on PASS in `reviews/stageN.md`.
- Keep this file and edits terse; token budget is shared with chat on the $20 plan.

## Orchestration
- `experiments.yaml` declares every run as a job (deps + output + command). `ORCHESTRATION.md`
  is the design + per-script interfaces. Never launch jobs ad hoc — go through the manifest.
- To decide what to run next: `/orchestrate core` (runs the resumable controller). It infers
  status from files on disk, so a dead Kaggle session never loses your place.
- CORE lane = the 1-week preprint. EXTENDED lane = the fuller paper (RQ3/RQ4, extra baselines) —
  do not start extended jobs until core is done and reviewed.

## Conventions
- Python 3.11, `uv` for envs, deterministic seeds from `configs/exp.yaml`.
- Log metrics as flat JSON matching the schema in PLAN.md §7.
- **Provenance:** every `results/*.json` includes a `_provenance` block {git_sha, job, config_hash,
  timestamp}. A number with no provenance does not go in the paper.
- No `print`-debugging left in committed code; use `logging`.
