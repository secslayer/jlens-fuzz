# Stage 0 Re-Review — Repo & environment (4th cycle, independent, from scratch)

**Branch:** stage-0-1-env-sanity
**Commit reviewed:** af84c41c3e97270dd93be80153de945797307e92 ("chore: gitignore state.db
(runtime controller state)") — note this is **one commit past** `db66dae` (the commit named in
the review request); `af84c41` only adds a single `.gitignore` line (`state.db`) on top of
`db66dae` and does not touch any Stage 0 checklist artifact. Verified via `git show af84c41
--stat` → `.gitignore | 1 +`. This review evaluates current HEAD (`af84c41`), which is a strict
superset of `db66dae`'s changes.

**Prior verdict:** PASS at `04fa1da`, with two non-blocking "required fixes" logged (missing
`pytest` in `requirements.txt`; misleading `0a97e0f` commit message) and a recurring caveat that
green CI had not been freshly re-observed at the exact reviewed HEAD on every cycle. This is a
fresh, independent re-review — prior review prose is not trusted, only re-derived evidence below.

## Overall verdict: **PASS**

All four Gate 0 checklist items hold under direct re-verification at current HEAD. Both
previously-open "required fixes" are now genuinely closed (not just claimed — verified against
the diffs of the commits they describe). CI is confirmed green on GitHub for the **exact current
HEAD sha**, not a stale one. No secrets, no raw harmful text, and no gated-dataset regression
found anywhere in history.

## Gate 0 checklist

| # | Item | Verdict | Evidence |
|---|------|---------|----------|
| 1 | `.gitignore` blocks secrets and generated attack strings | PASS | `.gitignore` (read directly, 13 lines) contains `.env`, `*.key`, `.kaggle/`, `kaggle.json`, `results/**/prompts_*`, `results/**/*jailbreak*`, `checkpoints/`, plus `state.db` added in `af84c41`. `git log --all --diff-filter=A --name-only \| grep -iE '^\.env$\|kaggle\.json$\|\.key$'` → empty (no secret-named file ever added, any branch). `git log --all -p \| grep -iE "sk-[a-zA-Z0-9]{20,}\|OPENROUTER_API_KEY\s*=\|AKIA[0-9A-Z]{16}\|api_key\s*=\s*['\"][a-zA-Z0-9]{20,}"` → empty (full history, all refs). `git ls-files results/` → only `results/.gitkeep`, `results/sanity.json` (aggregate-only, no raw text — re-verified below). |
| 2 | `requirements.txt` installs clean in a fresh env | PASS | Built a brand-new venv at `/tmp/jlens_fresh_review` (`python3 -m venv`), `pip install -r requirements.txt` → exit 0, no `error`/`failed` in the log (70 packages installed, including `pytest-9.1.1` as one of the resolved packages — confirms it's a real dependency now, not just text in the file). |
| 3 | Kaggle runner clones + imports with no error (CPU dry run) | PASS | Fresh venv `/tmp/jlens_fresh_review2`, ran `python scripts/check_env.py --config configs/exp.yaml` → all 11 package imports PASS, `configs/exp.yaml` 14/14 required keys present, CUDA correctly absent (informational), `results/`, `results/probes/`, `logs/` directories ready, `OVERALL PASS — environment is ready.`, exit code confirmed via return of the process (no traceback). (No committed `scripts/kaggle_runner.ipynb`; PLAN.md's top banner explicitly marks that file legacy in favor of RUNBOOK.md/ORCHESTRATION.md, whose Kaggle bootstrap `check_env.py` reproduces locally — same interpretation as all three prior cycles, still valid.) |
| 4 | CLAUDE.md guardrails present and readable | PASS | `CLAUDE.md` present at repo root (3522 bytes), read directly — contains "Golden rules" (no secrets, never invent numbers, identical baseline conditions, human gates, AUC≥0.85 stop rule) and repo map. |

## Exit criterion: green CI (pytest placeholder passes), Kaggle dry run succeeds

| Check | Verdict | Evidence |
|---|---|---|
| `make setup && make test` self-contained, **no manual pytest install** | **PASS — this is the specific claim of the latest fix, directly verified** | Fresh venv `/tmp/jlens_fresh_review2` (never had pytest installed by hand). Ran `make setup PY=/tmp/jlens_fresh_review2/bin/python` (→ `pip install -r requirements.txt`, installs `pytest-9.1.1` as part of the requirements resolution — visible in pip's "Successfully installed ... pytest-9.1.1 ..." line) then, in the same venv with no intervening install step, `make test PY=/tmp/jlens_fresh_review2/bin/python` → `/tmp/jlens_fresh_review2/bin/python -m pytest -q` → `2 passed in 0.54s`, exit 0. Confirms `requirements.txt`'s `pytest>=8.0` (line 12, read directly) actually closes the gap the prior review flagged, not just declares it in prose. |
| `pytest -q` passes | PASS | Same run as above; `2 passed`. |
| `make test` propagates real failures (not swallowed) | PASS (re-confirmed pattern from prior cycle, `Makefile`'s `test:` target unchanged) | `Makefile` line: `test: $(PY) -m pytest -q` — no `\|\| true`/`\|\| echo` swallow, read directly. |
| CI actually ran and went green **on GitHub, at the exact current HEAD sha** | **PASS — confirmed with hard evidence, not a stale sha** | `git status -sb` → `## stage-0-1-env-sanity...origin/stage-0-1-env-sanity` — no ahead/behind, genuinely pushed. `git rev-parse HEAD` → `af84c41c3e97270dd93be80153de945797307e92`. `git ls-remote origin refs/heads/stage-0-1-env-sanity` → `af84c41c3e97270dd93be80153de945797307e92` — **exact match**, local and remote are identical. `gh auth status` → logged in as `secslayer`, `repo`+`workflow` scope. `gh run list --branch stage-0-1-env-sanity` → most recent run `30993776284`, `completed`/`success`, `2026-08-05T09:33:35Z`. `gh run view 30993776284 --json headSha,conclusion,event,headBranch` → `{"conclusion":"success","headSha":"af84c41c3e97270dd93be80153de945797307e92","headBranch":"stage-0-1-env-sanity","event":"pull_request"}` — **the sha matches current HEAD exactly**, resolving the caveat that recurred across prior review cycles (stale/unpushed commits). `gh pr list --head stage-0-1-env-sanity` → PR #1, `OPEN`. |

## Verification of the two specific fixes claimed since the last PASS (`04fa1da`)

| Claimed fix | Verdict | Evidence |
|---|---|---|
| `pytest>=8.0` added to `requirements.txt` | **PASS, real** | `requirements.txt` line 12 (read directly): `pytest>=8.0`. Functionally proven above (`make setup && make test` with zero manual installs, fresh venv, `2 passed`). |
| `reviews/stage0.md` Corrections section documenting `0a97e0f`'s misleading commit message | **PASS, factually accurate** — independently re-derived, not trusted from the correction's own prose | `git show 0a97e0f --stat` → `reviews/stage0.md \| 55 +++++...`, **only** `reviews/stage0.md` touched, zero change to `scripts/train_probes.py` or any code file. Commit message is `"fix: train_probes.py reads AdvBench from cfg[benchmark], single source of truth"` — confirmed mismatched with its own diff, exactly as the Corrections section claims. `git show 7e7c2b9 -- scripts/train_probes.py` → real diff: `load_instructions()` signature changes from `(n_per_class, seed)` to `(benchmark, n_per_class, seed)`, body changes from `load_dataset("walledai/AdvBench", split="train")` to `pd.read_csv(benchmark); harmful = adv["goal"].tolist()`, and the call site changes to `load_instructions(cfg["benchmark"], args.n_per_class, cfg.get("seed", 0))` — this is the actual functional fix, and it is in `7e7c2b9`, not `0a97e0f`, exactly as the Corrections section states. The correction's own claim checks out against both commits' real diffs. |

## Cross-cutting red-flag checks (re-run for new files since last PASS)

- **Secrets/API keys in tracked files, full history, all branches:** none found (see item 1 evidence above; re-run this cycle, not reused from a prior report).
- **`walledai` gated-dataset regression at current HEAD:** `git grep -in walledai HEAD` → 3 hits, all comments warning against the gated dataset (`configs/exp.yaml:11`, `scripts/sanity_check.py:83`, `scripts/train_probes.py:43`); no live `load_dataset("walledai/...")` call. Confirmed clean, unchanged since prior cycle.
- **New files since last PASS — `reviews/stage1-human-signoff.md` (added in `5fad92c`) and the `db66dae`/`af84c41` diffs:** read directly. `reviews/stage1-human-signoff.md` contains only meta-description (reviewer identity, date, methodology, verdict) — grepped for `BEHAVIOR:`, `COMPLETION:`, and harmful-content keywords (`bomb`, `hack`, `kill`, `steal`, `explosive`, `virus`, `malware`) → zero hits, no raw prompt/completion text. `db66dae`'s diff is `requirements.txt` (+1 line) and `reviews/stage0.md` (prose correction) only. `af84c41`'s diff is `.gitignore` (+1 line, `state.db`) only. None of these introduce a secret, an attack string, or a Stage-0-checklist regression. This does **not** re-litigate Stage 1's own gate (its `sanity.json`/human-signoff content is Stage 1's concern) — only confirms no Stage-0-scoped violation.
- **Uncommitted working-tree state:** `git status -sb` shows `M reviews/stage1.md` (modified, unstaged) at review time — this is dirty working-tree content, not part of `HEAD` and not part of what CI validated or what is pushed to `origin`. Diffed it directly: it is a draft Stage-1-review edit (prose only, no secrets, no harmful strings). Since it is uncommitted, it has no bearing on Stage 0's gate (which concerns committed/pushed state) but is noted here for completeness — a future commit should either commit or discard it so the working tree matches `HEAD`.
- **Numbers with no `results/*.json` backing:** N/A for Stage 0's own scope; the one number living on this branch (`refusal_rate: 1.0` in `results/sanity.json`) is Stage 1 content, already audited for Stage-0-relevant red flags in the prior cycle's report below (re-confirmed still git-tracked, aggregate-only, provenance present) — full Stage 1 gate adjudication is out of scope here per instructions.
- **Baseline vs. ours config invariants:** N/A for Stage 0.

## Summary

Both items carried over from the prior review as "required fixes / non-blocking" are now
verified closed with direct evidence, not just claimed:
1. `pytest>=8.0` in `requirements.txt` — functionally proven via a fresh-venv `make setup && make
   test` with zero manual pytest install.
2. `0a97e0f`'s misleading commit message — the Corrections section's own account was independently
   re-derived against `git show 0a97e0f --stat` and `git show 7e7c2b9 --stat` and found accurate.

The recurring "unpushed branch / stale CI" caveat is also resolved this cycle: `origin` and local
`HEAD` are identical (`af84c41`), and a GitHub Actions run with `conclusion: success` exists for
that exact sha.

No new blockers found. **Stage 0 gate: PASS.**

---

## Corrections (2026-08-05)

- **Item 2 above (`0a97e0f` message mismatch) — confirmed and closed.** `git show 0a97e0f --stat`
  shows the commit touched only `reviews/stage0.md` (the prior review report); the message
  ("fix: train_probes.py reads AdvBench from cfg[benchmark], single source of truth") was a
  copy-paste artifact carried over from drafting the actual fix, not a description of that
  commit's own diff. The real code change — `load_instructions()` taking `benchmark` as a param
  and the call site passing `cfg["benchmark"]` — landed in `7e7c2b9`, confirmed via
  `git show 7e7c2b9 -- scripts/train_probes.py`. No functional or security impact; the code at
  HEAD is correct. Going forward: verify a commit's message matches `git diff --stat` (or
  `git show --stat`) for that exact commit before committing, not the commit being drafted
  alongside it.
- **Item 1 above (`pytest` missing from `requirements.txt`) — fixed.** See `requirements.txt`;
  `pytest` is now a direct dependency so `make setup && make test` is self-contained for a fresh
  contributor without relying on CI's separate `pip install pytest pyyaml` step.
