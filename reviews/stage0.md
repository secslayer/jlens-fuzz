# Stage 0 Re-Review — Repo & environment

**Branch:** stage-0-1-env-sanity
**Commit reviewed:** 7e7c2b9 ("Swap gated walledai/AdvBench for the ungated canonical AdvBench CSV")
**Prior verdict:** PASS at 54f1d77, with one non-blocking caveat (branch not pushed, so CI never
actually ran on GitHub). This review independently re-verifies all four Gate 0 items plus the
exit criterion from scratch (not trusting the prior review's notes), and separately verifies the
new dataset-swap commit is real, complete, and introduces no new leaks.

## Overall verdict: **PASS** (same push/CI caveat as last time still applies, confirmed not yet resolved)

## Gate 0 checklist

| # | Item | Verdict | Evidence |
|---|------|---------|----------|
| 1 | `.gitignore` blocks secrets and generated attack strings | PASS | `.gitignore` (read directly) contains `.env`, `*.key`, `.kaggle/`, `kaggle.json`, `results/**/prompts_*`, `results/**/*jailbreak*`, `checkpoints/`. `git log --all --diff-filter=A --name-only \| grep -iE "^\.env$\|kaggle\.json$"` → empty (never committed). `git log --all -p \| grep -iE "sk-[a-zA-Z0-9]{20,}\|OPENROUTER_API_KEY\s*=\|AKIA[0-9A-Z]{16}"` → empty. `git ls-files results/` → only `results/.gitkeep`. |
| 2 | `requirements.txt` installs clean in a fresh env | PASS | Built a new venv `/tmp/jlens_venv_test2`, ran `pip install -r requirements.txt > /tmp/pip_install.log 2>&1; echo $?` → `0`. `grep -i error /tmp/pip_install.log` → no matches. `grep -iE "openai\|openrouter" requirements.txt` → clean (no stale OpenRouter dep). |
| 3 | Kaggle runner clones + imports with no error (CPU dry run) | PASS | In the same fresh venv: `python scripts/check_env.py --config configs/exp.yaml` → all 11 package imports PASS, config validated (14/14 required keys present), CUDA correctly reported absent (informational), HF Hub reachable, `OVERALL PASS — environment is ready.`, exit code 0. |
| 4 | CLAUDE.md guardrails present and readable | PASS | `CLAUDE.md` present at repo root, 55 lines, contains the Golden Rules section (no secrets, never invent numbers, identical baseline conditions, human gates, AUC≥0.85 stop rule). |

## Exit criterion: green CI (pytest placeholder passes)

| Check | Verdict | Evidence |
|---|---|---|
| `pytest -q` passes | PASS | `python3 -m pytest -q` → `2 passed in 0.02s` (`tests/test_placeholder.py`: `test_placeholder` + `test_exp_config_has_required_invariant_keys`, which loads `configs/exp.yaml` and asserts all 14 required keys present — re-read the file directly, not the prior review's summary). |
| `make test` passes and propagates real failures | PASS | `make test` → runs `python -m pytest -q`, `2 passed`, exit 0. `Makefile` `test:` target is exactly `$(PY) -m pytest -q`, no `\|\| echo`/`\|\| true` swallow (grepped directly). |
| `.github/workflows/ci.yml` exists and gates on pytest | PASS (config only; NOT observed green on GitHub — caveat persists) | File present, valid YAML, triggers on `push: branches:[main]` and `pull_request`, job installs `pytest pyyaml` then runs `python -m pytest -q` as the terminal step. **Re-confirmed today:** `git status -sb` → `## stage-0-1-env-sanity...origin/stage-0-1-env-sanity [ahead 2]` (now 2 unpushed commits, was 1 last time — the gap grew, it was not closed). `gh run list` → empty. `gh run list --workflow=ci.yml` → `HTTP 404: workflow ci.yml not found on the default branch`. This is the identical unresolved caveat from the prior review's "required fixes" item, which was not acted on. |

## Dataset-swap commit (7e7c2b9) — independently re-verified

| Claim | Verdict | Evidence |
|---|---|---|
| No remaining hardcoded/live reference to gated `walledai/AdvBench` id | PASS | `git grep -in walledai` → 3 hits, all in comments *warning against* the gated dataset (`configs/exp.yaml:11`, `scripts/sanity_check.py:83`, `scripts/train_probes.py:43`) — no `load_dataset("walledai/...")` call anywhere. Full-repo `grep -rin walledai . --exclude-dir=.git` (tracked + untracked) confirms the same 3 comment-only hits. `git grep -in 'load_dataset("walledai\|load_dataset(.walledai'` → no matches. |
| `configs/exp.yaml`'s `benchmark` is a live, fetchable, ungated URL with a `goal` column | PASS | `configs/exp.yaml:12` → `benchmark: "https://raw.githubusercontent.com/llm-attacks/llm-attacks/main/data/advbench/harmful_behaviors.csv"`. `curl -sSL <url> -o /tmp/advbench_test.csv -w "HTTP_CODE:%{http_code}"` → `HTTP_CODE:200`, `wc -l` → 521 lines (1 header + 520 rows), `head -3` shows header `goal,target` and real rows. |
| `scripts/sanity_check.py` reads `cfg["benchmark"]`, not hardcoded | PASS | `load_harmful_behaviors(cfg, n, seed)` at line 79 does `df = pd.read_csv(cfg["benchmark"])` (line 87), called at line 179 as `load_harmful_behaviors(cfg, args.n, seed)`. Ran it live end-to-end in the fresh venv: `load_harmful_behaviors(cfg, 5, cfg.get('seed', 0))` against the real config → returned 5 non-empty strings from the live URL, confirming the whole path (not just static grep) actually works. |
| `scripts/train_probes.py` reads `cfg["benchmark"]`, not hardcoded (this was the actual bug — function previously ignored the config entirely) | PASS | `load_instructions(benchmark, n_per_class, seed)` signature at line 39 now takes `benchmark` as an explicit param; body does `adv = pd.read_csv(benchmark)` (line 47); call site at line 119 is `load_instructions(cfg["benchmark"], args.n_per_class, cfg.get("seed", 0))`. Confirmed via direct diff read (`git show 7e7c2b9 -- scripts/train_probes.py`), not the commit message. The `datasets.load_dataset("tatsu-lab/alpaca", ...)` call remaining in the same file (line 55) is the harmless-class source, not AdvBench, and `tatsu-lab/alpaca` is ungated — correctly left alone. |
| Both scripts still `py_compile` clean | PASS | `python3 -m py_compile scripts/sanity_check.py scripts/train_probes.py` → exit 0, no output. |
| No CSV row content (harmful behavior text or judge-target strings) leaked into any tracked file | PASS | `git grep -in "exploit vulnerabilities in a software"` (a literal row-1 goal string) → no hits. `git grep -in "Sure, here is"` (the target-column template phrase) → no hits. Only the benchmark URL and the column names `goal`/`target` (schema references, not row content) appear in tracked files. |

## Cross-cutting red-flag checks

- Secrets/API keys in tracked files (full history): none found.
- Generated attack strings / benchmark row content in tracked files: none found (checked both pre-existing `results/**/prompts_*` patterns and, specifically for this diff, literal AdvBench CSV row text).
- Numbers with no `results/*.json` backing: N/A — Stage 0 makes no metrics claims; the "520 behaviors" figure in the commit message is reproducible via `curl` + `wc -l` (done above) and is not used as a paper number.
- Baseline vs. ours config invariants: N/A for Stage 0.

## Required fixes (non-blocking for this gate, but escalating)

1. **Push to origin.** This is now the second consecutive review where the branch is unpushed
   (was `[ahead 1]` at the last review, now `[ahead 2]`) and `gh run list --workflow=ci.yml`
   still 404s. The plan's exit criterion is literally "green CI" — that has still never been
   observed on GitHub, only reproduced locally. Continuing to add commits without pushing means
   this will keep recurring at every re-review. Push and open the PR before Stage 0 is truly
   closed out, and get a human (or at minimum a follow-up automated check) to confirm the
   Actions run is actually green on GitHub, not just configured correctly.
