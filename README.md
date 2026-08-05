# jlens-fuzz

Interpretability-guided jailbreak fuzzing for open-weight LLMs — a **proof-of-concept preprint**
scaffold. We replace GPTFuzzer's sparse binary fitness with a refusal-probe signal on a partial
forward pass, use a difference-in-means refusal direction to choose *where* to mutate, and test
whether human seed templates can be dropped (the headline ablation). White-box target:
`Qwen2.5-3B-Instruct`. Everything runs **free on Kaggle** — no paid APIs.

> **Ethics:** this is defensive red-teaming using public benchmarks (AdvBench) on small open-weight
> models. Do not commit generated attack strings (the `.gitignore` blocks them). See `PLAN.md §8`.

## Start here (read in this order)
1. **`RUNBOOK.md`** — click-by-click: accounts, laptop, Kaggle, the daily loop, arXiv.
2. **`ORCHESTRATION.md`** — how the pipeline is coordinated (the resumable job queue) + script specs.
3. **`PLAN.md`** — the stage plan and the peer-review gates.
4. **`CLAUDE.md`** — the rules Claude Code follows.

## First commands
```bash
python scripts/run_controller.py --lane core     # status board + next Kaggle launch lines
# then follow RUNBOOK.md Part 2 to run on Kaggle
```

## What exists vs. what you build (be honest with yourself)
**Ready to run now:**
- `scripts/train_probes.py` — the refusal probe (Day 2 make-or-break gate). The quality bar.
- `scripts/run_controller.py` — the resumable orchestrator.
- `scripts/run_experiment.py` — the single-job dispatcher.
- `scripts/run_parallel.sh` — two jobs, one per GPU.
- `experiments.yaml`, `configs/exp.yaml` — the manifest + invariants.
- `.claude/` — `builder` + `reviewer` subagents, `/review` + `/orchestrate` commands.

**You write these with the `builder` subagent (interfaces in `ORCHESTRATION.md`):**
`check_env.py`, `sanity_check.py`, `extract_direction.py`, `validate_signal.py`,
**`run_fuzz.py`** (the critical path — unblocks nearly everything),
`transfer_blackbox.py`, `make_figures.py`, `assemble_paper.py`.

## Layout
```
PLAN.md ORCHESTRATION.md RUNBOOK.md CLAUDE.md README.md
Makefile experiments.yaml requirements.txt .gitignore
configs/exp.yaml
scripts/{train_probes,run_controller,run_experiment}.py  scripts/run_parallel.sh
.claude/agents/{reviewer,builder}.md  .claude/commands/{review,orchestrate}.md
results/  reviews/  logs/          # created as you go (gitignored where appropriate)
```

## License
MIT (recommended). Add a `LICENSE` file before releasing.
