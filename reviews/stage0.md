# Stage 0 Re-Review — Repo & environment (3rd cycle, from scratch)

**Branch:** stage-0-1-env-sanity
**Commit reviewed:** 04fa1da40c0eb2e6b8bda96fdcbbc085efba88eb ("stage1: sanity check results,
refusal_rate=1.0, hand-verified")
**Prior verdict:** PASS at 7e7c2b9, with one open caveat: branch had never been pushed, so
"green CI" was configured but never actually observed running on GitHub. This review starts
over, does not trust the prior review's notes, and specifically resolves that caveat plus
independently audits the two commits added since (`0a97e0f`, `04fa1da`).

## Overall verdict: **PASS**

All four Gate 0 checklist items and the exit criterion hold under direct re-verification, and
the previously-open CI caveat is now resolved with hard evidence (a real GitHub Actions run at
the exact HEAD sha, `conclusion: success`). No secrets, no raw harmful text, and no gated-dataset
regressions were found. Two non-blocking hygiene issues are logged below under "required fixes."

## Gate 0 checklist

| # | Item | Verdict | Evidence |
|---|------|---------|----------|
| 1 | `.gitignore` blocks secrets and generated attack strings | PASS | `.gitignore` (read directly) contains `.env`, `*.key`, `.kaggle/`, `kaggle.json`, `results/**/prompts_*`, `results/**/*jailbreak*`, `checkpoints/`. `git log --all --diff-filter=A --name-only \| grep -iE "^\.env$\|kaggle\.json$"` → empty. `git log --all -p \| grep -iE "sk-[a-zA-Z0-9]{20,}\|OPENROUTER_API_KEY\s*=\|AKIA[0-9A-Z]{16}\|api_key\s*=\s*['\"][a-zA-Z0-9]{20,}"` → empty (checked full history, all branches). `git ls-files results/` → `results/.gitkeep`, `results/sanity.json` only (audited separately below, aggregate-only). |
| 2 | `requirements.txt` installs clean in a fresh env | PASS | Built a brand-new venv `/tmp/jlens_venv_review3`, ran `pip install -r requirements.txt`, exit code `0`, no `error`/`failed` lines in the captured log. |
| 3 | Kaggle runner clones + imports with no error (CPU dry run) | PASS | In the same fresh venv: `python scripts/check_env.py --config configs/exp.yaml` → all 11 package imports PASS, `configs/exp.yaml` 14/14 required keys present, CUDA correctly reported absent (informational, not a failure), HF Hub reachable, `OVERALL PASS — environment is ready.`, exit code `0`. (Repo has no committed `scripts/kaggle_runner.ipynb`; PLAN.md §4A's mention of that file is explicitly marked legacy at the top of PLAN.md — "RUNBOOK.md v2 and ORCHESTRATION.md are authoritative." RUNBOOK.md §2.4 defines the real Kaggle bootstrap as a live notebook cell — `pip install -r requirements.txt` + import smoke test — which is what `check_env.py` reproduces locally. Same interpretation as the prior two review cycles.) |
| 4 | CLAUDE.md guardrails present and readable | PASS | `CLAUDE.md` present at repo root, contains the "Golden rules" section (no secrets, never invent numbers, identical baseline conditions, human gates, AUC≥0.85 stop rule). Read directly, not inferred. |

## Exit criterion: green CI (pytest placeholder passes)

| Check | Verdict | Evidence |
|---|---|---|
| `pytest -q` passes | PASS | In the fresh venv + `pip install pytest`: `python -m pytest -q` → `2 passed in 0.02s` (`tests/test_placeholder.py`: `test_placeholder` + `test_exp_config_has_required_invariant_keys`, which loads `configs/exp.yaml` and asserts all 14 required keys — read the file directly). |
| `make test` passes and propagates real failures | PASS | `make test` → `python -m pytest -q`, `2 passed`, exit `0`. Confirmed the target does NOT swallow failures: copied the repo to `/tmp/jlens_makecheck`, appended a deliberately-failing test, ran `make test` → `1 failed, 2 passed`, `make: *** [test] Error 1`, exit code `2` (propagated, not silenced). `Makefile`'s `test:` target is exactly `$(PY) -m pytest -q`, no `\|\| true`/`\|\| echo` swallow. |
| CI actually ran and went green **on GitHub** (the previously open caveat) | **PASS — now confirmed with hard evidence, caveat resolved** | `git status -sb` → `## stage-0-1-env-sanity...origin/stage-0-1-env-sanity` (no ahead/behind — genuinely pushed, not just tracking-configured). `git ls-remote origin refs/heads/stage-0-1-env-sanity` → `04fa1da...` — matches local `HEAD` exactly. `gh auth status` → logged in as `secslayer`, token has `repo`+`workflow` scope. `gh run list --workflow=ci.yml` → 2 runs, both `completed`/`success`, most recent `30990667261` at `2026-08-05T08:50:11Z`. `gh run view 30990667261 --json headSha,conclusion,event` → `{"conclusion":"success","event":"pull_request","headBranch":"stage-0-1-env-sanity","headSha":"04fa1da..."}` — **the sha matches the exact commit under review**. `gh pr list --head stage-0-1-env-sanity` → PR #1, `OPEN`. This is a real, observed green run on GitHub triggered by a real open PR, not a local reproduction and not merely "configured correctly." |

## Cross-cutting red-flag checks

- **Secrets/API keys in tracked files (full history, all branches):** none found (see item 1 evidence).
- **`walledai` gated-dataset regression check (fix from last two commits):** `git grep -in walledai $(git rev-list --all)` shows the id appears only in commits up to `7e7c2b9`'s parent (`54f1d77`, `62cbc52`, `d5327f4`, `2afcab3` — pre-fix history, expected). At every commit from `7e7c2b9` onward (including current HEAD `04fa1da`), the only hits are **comments warning against** the gated dataset (`configs/exp.yaml:11`, `scripts/sanity_check.py:83`, `scripts/train_probes.py:43`) — no live `load_dataset("walledai/...")` call remains anywhere at HEAD. `scripts/train_probes.py:119` calls `load_instructions(cfg["benchmark"], ...)` and `load_instructions()` at line 49 does `pd.read_csv(benchmark)` — confirmed reading the ungated CSV via config, not hardcoded. **Confirmed clean.**
- **Generated attack strings / raw harmful text in any git-tracked file:** none found. See dedicated `results/sanity.json` audit below.
- **Numbers with no `results/*.json` backing:** N/A for Stage 0's own scope. The one number newly on this branch (`refusal_rate: 1.0`) does trace to a tracked JSON file with a provenance block (see below) — audited separately since it's Stage 1 content living on this branch.
- **Baseline vs. ours config invariants:** N/A for Stage 0.

## `results/sanity.json` audit (Stage 1 content on this branch — checked for Stage 0 red flags only, per instructions; this does NOT clear Gate 1, which still needs its own 👤 human sign-off)

| Check | Verdict | Evidence |
|---|---|---|
| Is it git-tracked? | Yes | `git ls-files results/` → `results/.gitkeep`, `results/sanity.json`. Added in commit `04fa1da`. |
| Contains raw prompt/completion text (Golden Rule 1 violation)? | **No — aggregate-only, as designed** | `python3 -c "import json; d=json.load(open('results/sanity.json')); print(list(d.keys())); print(list(d['per_behavior'][0].keys()))"` → top-level keys `['target_model','judge_model','n','refusal_rate','per_behavior','hand_label_examples_file','hand_label_examples_count','_provenance']`; each `per_behavior` entry only has `['index','judge_label','judge_score']` — no `behavior`/`completion`/`goal`/`target` text fields. `grep -iE 'behavior":\|completion":' results/sanity.json` matches only the array key name `per_behavior`, not string content. Matches the documented design in `scripts/sanity_check.py` (read in full): raw text is written only to `results/prompts_sanity_examples.jsonl`, which the `.gitignore` pattern `results/**/prompts_*` correctly matches (`git check-ignore -v results/prompts_sanity_examples.jsonl` confirms) and which is **not present in git** (`git ls-files \| grep -i prompts_sanity` → empty) and not currently on disk either. |
| `_provenance` block present and internally consistent? | PASS | Block is `{"git_sha":"0a97e0f","job":"sanity","config_hash":"605032769f74b171","timestamp":"2026-08-05T08:47:12.525701+00:00"}`. Independently recomputed: `git show 0a97e0f:configs/exp.yaml \| shasum -a 256 \| cut -c1-16` → `605032769f74b171` — **exact match**, confirming the hash is a real, programmatically-computed sha256 of the actual config at that commit (via `sanity_check.py`'s `config_hash()` function, read directly), not a hand-typed placeholder. `0a97e0f` is a real ancestor of `04fa1da` (`git merge-base --is-ancestor 0a97e0f 04fa1da` → true). |
| `n` matches `len(per_behavior)`, and `refusal_rate` matches the label mean (internal consistency)? | PASS | `n: 20`, `per_behavior` has exactly 20 entries (indices 0–19), all `judge_label: true`; `refusal_rate: 1.0` = 20/20. Arithmetically consistent, not fabricated round numbers pasted over mismatched data. |
| Can the underlying model run be independently confirmed from this control-plane session? | **Not fully — disclosed limitation, not a Stage 0 fail** | `~/.cache/huggingface` has no `Qwen`/`GPTFuzz` model ever downloaded on this laptop, and `.github/workflows/ci.yml` only runs `pytest`, never `sanity_check.py` — so the numbers were **not** produced by this control session or by the GitHub Actions job. The commit author identity is `ci <ci@x>` (`gh api repos/.../commits/04fa1da` → `"author":{"name":"ci","email":"ci@x"...}`, `"author":null` on the GitHub-user side, i.e. not a registered GitHub bot). This exactly matches the git-commit convention **documented in `RUNBOOK.md:210`** for Kaggle→GitHub result pushes (`git -c user.email=ci@x -c user.name=ci commit -m "results"`), which is reassuring (matches the intended pipeline) rather than a fabrication signal on its own, but I have no Kaggle-account access from this review session and cannot directly confirm a GPU inference run actually executed. This is an inherent verification gap for an agent reviewer, not evidence of wrongdoing — flagging explicitly per instructions rather than asserting either way. This is exactly what Gate 1's mandatory 👤 human check (hand-label the 10 examples, confirm judge agreement) exists to close, and that check has **not** happened yet (no `results/prompts_sanity_examples.jsonl` on disk to hand-label from, and no human-sign-off artifact exists). |
| Does its presence violate any Stage 0 checklist item or cross-cutting red flag? | **No** | No secret, no raw harmful string, no gated-dataset reference, provenance present and arithmetically self-consistent. Stage 0's own gate is unaffected. |

## Required fixes (non-blocking for Stage 0, logged for hygiene / next cycle)

1. **`requirements.txt` does not declare `pytest`.** `make setup && make test` on a bare fresh
   env fails with `No module named pytest` until `pytest` is installed separately (confirmed:
   `pip install -r requirements.txt` then `make test` → `ModuleNotFoundError`). CI works around
   this by installing `pytest pyyaml` directly (`.github/workflows/ci.yml`), which is why CI
   itself is unaffected and green — so this is not a gate blocker — but it means the Makefile's
   own `setup` → `test` sequence is not self-contained for a local contributor. Add `pytest` to
   `requirements.txt` (or a `requirements-dev.txt`) to close the gap.
2. **Commit `0a97e0f`'s message does not match its diff.** Message says "fix: train_probes.py
   reads AdvBench from cfg[benchmark], single source of truth," but `git show 0a97e0f --stat`
   shows the only file touched is `reviews/stage0.md` (+55 lines, the prior review report) — zero
   change to `scripts/train_probes.py`. The actual code fix for that bug landed earlier, in
   `7e7c2b9` (`git diff 7e7c2b9^ 7e7c2b9 -- scripts/train_probes.py` shows the real change, and
   `scripts/train_probes.py:119`/`:49` at HEAD confirm it reads `cfg["benchmark"]` correctly — so
   the *code* is fine). This is a commit-message hygiene defect only (likely a copy-paste of the
   prior commit's subject when committing the reviewer's output), not a functional or security
   issue, but worth correcting practice going forward so commit history stays trustworthy as a
   provenance trail.
3. **Gate 1's human sign-off is still outstanding.** `results/sanity.json` exists with a
   plausible, internally-consistent, non-fabricated-looking provenance trail, but the 👤
   hand-label step (10 examples, judge-agreement check) required by PLAN.md Stage 1 has not
   happened yet — no human-reviewed artifact exists, and the raw examples file isn't present
   locally to review from. This is explicitly **out of Stage 0's gate** and does not block this
   verdict, but should not be treated as "Stage 1 done" — flagging per the task's own framing so
   it isn't silently skipped.
