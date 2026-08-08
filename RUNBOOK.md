# RUNBOOK v2 — Kaggle-only, click-by-click, from zero to preprint

Everything here runs **free on Kaggle**. No OpenRouter, no RunPod, no paid API. The only other
services are free and unavoidable: **GitHub** (syncs your laptop's code to Kaggle) and **Hugging
Face** (downloads the open-weight models). The RQ3 "transfer" experiment now replays your attacks
on a **second small model locally on Kaggle** — no external API.

Read alongside `ORCHESTRATION.md` (what runs when) and `PLAN.md` (the peer-review gates).

**Architecture**
- **Laptop** = Claude Code (writes code, drafts paper) + git. No GPU needed.
- **GitHub** (free, private repo) = the bridge. Laptop pushes; Kaggle pulls.
- **Kaggle** = the ONLY compute. 1 interactive notebook (dev bench) + 2 commit notebooks (parallel
  runners), each with 2x T4 GPUs.
- **Hugging Face** (free) = model/dataset downloads.

Legend: [L] laptop . [B] browser . [K] Kaggle notebook . [H] human gate.

---

## PART 0 - Accounts (~20 min, once) - all free

### 0.1 GitHub  [B]
1. https://github.com -> sign in.
2. Top-right **+ -> New repository**. Name `jlens-fuzz`. **Private**. Don't add any files. **Create**.
3. Avatar -> **Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens ->
   Generate new token**. Repository access = only `jlens-fuzz`; Permissions -> **Contents =
   Read and write**. Generate -> **copy** the `github_pat_...` string. This is your `GH_PAT`.

### 0.2 Kaggle  [B]
1. https://www.kaggle.com -> Register.
2. Avatar -> **Settings -> Phone verification** -> verify. **GPU stays locked until you do this.**
3. Same page -> **API -> Create New Token** -> a `kaggle.json` downloads (has username + key).

### 0.3 Hugging Face  [B]
1. https://huggingface.co -> Sign up.
2. Avatar -> **Settings -> Access Tokens -> New token** -> type **Read** -> Create -> copy it. This
   is your `HF_TOKEN`. (Qwen2.5-3B and Phi-3.5-mini are ungated, so this is just for faster pulls.)

*(No OpenRouter. No other accounts.)*

---

## PART 1 - Laptop setup (~15 min, once)  [L]

### 1.1 git + GitHub CLI
- git: https://git-scm.com/downloads
- gh: https://cli.github.com -> then `gh auth login` (GitHub.com -> HTTPS -> browser).

### 1.2 Install Claude Code (native installer - avoids the npm ENOTEMPTY trap)
```bash
curl -fsSL https://claude.ai/install.sh | bash      # macOS/Linux/WSL
# Windows PowerShell:  irm https://claude.ai/install.ps1 | iex
```
Open a **new terminal**, then:
```bash
which claude          # expect ~/.local/bin/claude
claude doctor         # expect install type: native
claude                # sign in with your $20 Pro account, then /exit
```
If `which claude` is empty: `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc`.

### 1.3 Put the scaffold in the repo and push
Place all the files I gave you into a `jlens-fuzz/` folder, preserving subfolders
(`scripts/`, `configs/`, `.claude/`): `PLAN.md`, `ORCHESTRATION.md`, `RUNBOOK.md`, `CLAUDE.md`,
`Makefile`, `experiments.yaml`, `requirements.txt`, `.gitignore`, `configs/exp.yaml`,
`scripts/train_probes.py`, `scripts/run_controller.py`, `scripts/run_experiment.py`,
`scripts/run_parallel.sh`, `.claude/agents/{reviewer,builder}.md`,
`.claude/commands/{review,orchestrate}.md`.
```bash
cd jlens-fuzz
git init && git add . && git commit -m "scaffold + orchestration layer"
git branch -M main
git remote add origin https://github.com/<you>/jlens-fuzz.git
git push -u origin main            # paste GH_PAT if prompted for a password
```

---

## PART 2 - Kaggle setup (~10 min, once)  [B][K]

### 2.1 Create the interactive bench
1. https://www.kaggle.com/code -> **+ New Notebook**. Rename it (top-left) `jlens-bench`.

### 2.2 GPU + Internet
Right sidebar -> **Session options**:
- **Accelerator -> GPU T4 x2**
- **Internet -> On**
- **Persistence -> Files and Variables**

### 2.3 Secrets (only two now)
Top menu -> **Add-ons -> Secrets -> Add a new secret** twice:
- `HF_TOKEN` = your Hugging Face token
- `GH_PAT` = your GitHub token

Toggle **Attach to notebook** on for both. *(No OPENROUTER_KEY - it's gone.)*

### 2.4 Bootstrap cell (first cell; re-run every fresh session and after every push)
```python
import os, subprocess, pathlib
from kaggle_secrets import UserSecretsClient
s = UserSecretsClient()
os.environ["HF_TOKEN"] = s.get_secret("HF_TOKEN")
GH_PAT = s.get_secret("GH_PAT")

GH_USER, REPO = "<your-github-username>", "jlens-fuzz"
url = f"https://{GH_PAT}@github.com/{GH_USER}/{REPO}.git"
root = f"/kaggle/working/{REPO}"
if not pathlib.Path(root).exists():
    subprocess.run(["git","clone","-q",url], cwd="/kaggle/working", check=True)
else:
    subprocess.run(["git","pull","-q"], cwd=root, check=True)
%cd /kaggle/working/jlens-fuzz
# Activate the local raw-text pre-commit guard (reviews/stage7.md) -- core.hooksPath is a LOCAL
# git config, never cloned, so this must run every fresh session or commits from THIS session
# won't be checked before they leave Kaggle. Backstopped by CI's own copy of the same check
# (.github/workflows/ci.yml), which runs after the fact regardless of this line.
!git config core.hooksPath .githooks
!pip install -q -r requirements.txt
!python -c "import torch; print('GPUs:', torch.cuda.device_count())"
print("ready")
```
"GPUs: 2" + "ready" = bench is live. **Re-running this cell is how new code reaches Kaggle.**

---

## PART 3 - The orchestrated daily loop (replaces manual stage-tracking)

The controller decides what runs next; you just launch what it prints.

1. [L] In the repo: `python scripts/run_controller.py --lane core` (or `/orchestrate core` inside
   Claude Code). It reads `experiments.yaml`, sees which result files exist, and prints the ready
   jobs + exact Kaggle launch lines. It's **resumable** - a dead session never loses your place.
2. [B] Open your two commit runners (Part 6) and paste the emitted line(s) into each.
3. [K] Each runner executes `run_parallel.sh`, one job per T4 via `run_experiment.py`.
4. [B] When they finish, push `results/` back to GitHub (Part 6).
5. [L] `git pull`, then run the controller again -> it unblocks the next batch. Repeat until `paper`.

At each stage boundary run the gate (`/review <stage>`) and the [H] human checks before advancing
(probes AUC, judge labels, ethics).

---

## PART 4 - Driving Claude Code

Start `claude` in the repo. Core moves:
- Orient: `Read ORCHESTRATION.md, PLAN.md, CLAUDE.md. Summarize the current stage + its gate.`
- Build a missing script: `Use the builder subagent to implement scripts/run_fuzz.py per its
  interface in ORCHESTRATION.md and the flags in experiments.yaml.`
- Review a gate: `/review 3` -> reviewer writes `reviews/stage3.md`. Advance only on PASS.
- Check the queue: `/orchestrate core`.
- Branch per stage; small commits; `git push` after each.

> $20 Pro budget: code-gen shares the 5-hour window with chat. Keep CLAUDE.md lean, use Sonnet for
> routine coding, generate in focused bursts.

---

## PART 5 - Day-by-day (mapped to manifest jobs + gates)

**Day 1 - Stage 0/1 (env + sanity).**
- [L] builder: write `scripts/check_env.py` and `scripts/sanity_check.py`. Push.
- [K] bench: re-run bootstrap, then `!python scripts/check_env.py --config configs/exp.yaml` and
  `!python scripts/sanity_check.py --config configs/exp.yaml --n 20`.
- [H] Gate 1: hand-label 10 judge outputs; confirm the model refuses raw harmful prompts. `/review 1`.

**Day 2 - Stage 2 (probes + direction) - MAKE-OR-BREAK.**
- [L] builder: write `scripts/extract_direction.py` and `scripts/validate_signal.py`.
- [K] bench: `!python scripts/train_probes.py --config configs/exp.yaml --out results/probes`
  (already written) and `!python scripts/extract_direction.py --config configs/exp.yaml --out results/direction.npz`.
- [H] Gate 2: **best-layer AUC >= 0.85** and it separates 6 novel prompts you write. If not, STOP
  and re-engineer the signal. `/review 2`.

**Day 3 - Stage 3 (`run_fuzz.py` - the critical path).**
- [L] builder: implement `scripts/run_fuzz.py` with `--method {ours,gptfuzzer,autodan}
  --mutation {guided,uniform} --seedtier {human,bootstrap,random} --fitness {judge,judge+act}`
  (guided-span mutation via the direction's token attribution; probe/activation fitness). Push.
- [K] bench: smoke it at 5 behaviors (`--smoke` path or n_behaviors:5). Confirm >=1 judged jailbreak.
- `/review 3`.

**Day 4 - Stage 4 (headline ablations) + kick off full runs.** — **ABANDONED 2026-08-07, GPU
exhausted (PLAN.md §11).** Originally planned: `/orchestrate core` -> `ours, gptfuzzer,
abl_mut_uniform, abl_seed_random, abl_seed_bootstrap, validate` become ready -> launch the first
batch on the 2 commit runners (Part 6), at full `n_behaviors=25`. **What happened instead**: the
seed-pool-size fix (PLAN.md §12) was validated with a 5-behavior `ours`/`gptfuzzer` smoke on both
targets first, to confirm guided mutation's mechanism actually engages before spending GPU-hours
on the full matrix. It came back a validated null (guided=uniform) before more budget existed.
These jobs remain `ready` in `experiments.yaml` (nothing wrong with them) but will not be
launched — there is no GPU budget left, and the smoke-scale null already answers what they
existed to give statistical power to.

**Day 5 - Stage 5 (finish the matrix in parallel).** — **ABANDONED 2026-08-07**, same reason as
Day 4: no matrix left to finish, no runners to keep flowing. Gate 5's requirement survives at
**reduced scope**: hand-validate the judge labels you actually have (the smoke-scale completions
plus the judge-incident hand-reads already done — 4 Phi false positives, 3 Qwen spot-checks, see
`reviews/judge-validity-incident.md`) and assert `configs/exp.yaml`/`configs/exp_phi4mini.yaml`
stayed identical across both targets' smoke runs. Run `/review 5` explicitly against this reduced
scope — do not skip the gate just because the full-scale trigger for it never arrived.

> **Before Day 6/7**: as of 2026-08-07, `results/` in this repo only has the pre-judge-fix,
> pre-pool-fix `ours_smoke.json` — none of the post-fix pool-12 smoke JSONs (the ones the Day 6/7
> narrative below is based on) have been pushed from Kaggle and pulled here yet. The specific
> numbers driving that narrative (Phi `0.8→0.0`, Qwen `1.0→0.4`, `n_mutated_child_selected`
> 54-80) are **PI-reported, not yet artifact-backed** (CLAUDE.md rule 2) until those files land —
> same caveat as PLAN.md §11. Push + `git pull` first; `/review 6`/`/review 7` should recheck this
> before PASS.

**Day 6 - Stage 6 (local transfer + figures).** — Still applies, scoped to what's actually on
disk (smoke JSONs, not the full matrix — see caveat above).
- [L] builder: `scripts/transfer_blackbox.py` (`--local`, target from `transfer_target_local`) and
  `scripts/make_figures.py`. Push.
- [L] `/orchestrate core` -> `transfer_local` then `figures` become ready -> run them against the
  smoke-scale results. Figures should show `n=5` confidence intervals, not matrix-scale ones, and
  say so on the figure itself. `transfer_blackbox.py` replays *successful* prompts — check first
  whether the smoke runs produced any (`success: true` records); if ASR is at or near 0 on both
  methods (plausible post-judge-fix), there may be nothing to transfer — state that rather than
  skipping it silently. `/review 6`.

**Day 7 - Stage 7 (write + release).** — Still applies; `assemble_paper.py`/ethics
section/Mechanistic AutoDAN (2605.28553) distinction requirements unchanged. Narrative follows
PLAN.md §11's **DECIDED reframe**:
- **PRIMARY**: the judge-reliability finding — `hubert233/GPTFuzz` inflates ASR via template-echo
  false positives, a measurement-validity failure in a tool the field treats as standard.
- **SECONDARY**: the honest guided-mutation null — no ASR advantage over uniform mutation, with
  the mechanism independently verified as engaged (attribution + tree search both confirmed
  operating, PLAN.md §12).
- **METHODOLOGY note**: seed-pool exhaustion at `query_budget=40` vs. a 77-template pool (§12) —
  a caveat for reuse, not a result.
- **NOT the paper**: "guided mutation beats baselines" — tested and falsified, do not frame it as
  the headline.
- State the **smoke-scale (n=5) limitation** up front, not buried — the paper should not imply
  matrix-scale statistical power it does not have.
- [L] builder: `scripts/assemble_paper.py`; draft `paper/` from `results/*.json` only. `/review 7`,
  [H] sign-off.

---

## PART 6 - Parallel runners (the 2 commit notebooks)  [B][K]

1. [B] In `jlens-bench`, top-right **... -> Copy notebook**, twice -> `jlens-run-A`, `jlens-run-B`.
   Copies keep the GPU/Internet/Secrets settings.
2. [B] In each, keep the bootstrap cell, then add ONE cell with the line the **controller** printed:
   - `jlens-run-A`: `!JOB_A=ours JOB_B=gptfuzzer bash scripts/run_parallel.sh`
   - `jlens-run-B`: `!JOB_A=abl_mut_uniform JOB_B=abl_seed_random bash scripts/run_parallel.sh`
3. [B] Each: **Save Version -> Save & Run All (Commit)** with GPU on -> runs headless; close the tab.
   (Kaggle allows **2 commit + 1 interactive** GPU sessions - this uses exactly that.)
4. [B] Monitor: avatar -> **Your Work** -> the notebook -> **Logs**.
5. **Persist results before the session ends** - final cell (token not printed):
   ```python
   import os, subprocess
   r="/kaggle/working/jlens-fuzz"
   subprocess.run(["git","add","results"], cwd=r)
   subprocess.run(["git","-c","user.email=ci@x","-c","user.name=ci","commit","-m","results"], cwd=r)
   subprocess.run(["git","push",f"https://{s.get_secret('GH_PAT')}@github.com/<you>/jlens-fuzz.git"], cwd=r)
   ```
6. [L] `git pull` on the laptop so the controller/figures see the new results.
7. **Watch the 30 GPU-hr/week meter** (avatar -> Settings). Always smoke-test at 5 behaviors first.

---

## PART 7 - Publish the preprint (arXiv, free)  [B]

**Release checklist (Stage 7 exit, PLAN.md §6/§9) — run this before anything below.**

0. [L] `make release` — runs tests, the raw-text content scan
   (`scripts/check_no_raw_text.py`, `reviews/stage7.md`), and prints every remaining
   `[DRAFT FLAG]` in `paper/paper.md` plus a manual checklist (CI green, Gate 7 signed off,
   no unresolved disclosure flag). It does **not** tag for you — read its output, confirm each
   item, then continue. As of this writing `paper/paper.md` is not converted to PDF/LaTeX by
   any script (`scripts/assemble_paper.py` doesn't exist — `make paper` will fail; the paper
   was assembled by hand from `results/*.json`, see `paper/paper.md`'s own header) — step 1
   below is manual until that changes.

1. [L] Convert `paper/paper.md` to arXiv's expected format (PDF via pandoc/LaTeX, or a bundled
   LaTeX source tree) — there is no automated pipeline for this yet; do it manually or write
   `scripts/assemble_paper.py` first if you want one.
2. [B] https://arxiv.org -> login/register (institutional email helps).
3. [B] **Endorsement gotcha:** first-time `cs.CR`/`cs.CL` authors may need an endorsement
   (https://arxiv.org/help/endorsement). Arrange it early so it doesn't block you.
4. [B] **Submit -> Start New Submission** -> primary `cs.CR`, cross-list `cs.CL` -> upload PDF/LaTeX
   -> title/abstract/authors -> **Preview -> Submit**. Announced next business day.
5. [B] **Send the recorded disclosure notices now** (`paper/paper.md` §7): MSRC (for
   Phi-4-mini-instruct, Phi-3.5-mini-instruct) and Alibaba/Qwen (for Qwen2.5-3B-Instruct) — the
   plan says "at the time of arXiv posting," so this is that time. Record the actual send
   date/outcome back into `paper/paper.md` §7 and `reviews/stage7-human-signoff.md` afterward.
6. [L] Tag the release (manual — `make release` deliberately stops short of this):
   ```bash
   git tag -a v1.0-arxiv -m "v1.0-arxiv: Gate 7 signed off, paper frozen for arXiv"
   git push origin v1.0-arxiv
   gh release create v1.0-arxiv --title "v1.0 (arXiv)" --notes "Preprint release"
   ```
7. [L] Fill in the arXiv ID in `CITATION.cff`'s `preferred-citation.url` (currently a commented
   placeholder) and commit. GitHub will then show "Cite this repository" using it.

---

## APPENDIX - If something breaks
- `torch.cuda.device_count()` = 1 -> accelerator on single-GPU; fix Part 2.2.
- HF 401 -> `HF_TOKEN` secret not attached (Part 2.3).
- Push from Kaggle fails -> `GH_PAT` lacks Contents:write or wrong repo (Part 0.1).
- A job never leaves "ready" across two `/orchestrate` rounds -> check `logs/<job>.log`; it likely
  crashed. Fix the script, push, re-pull on Kaggle, relaunch.
- Quota exhausted mid-run -> ~30 GPU-hr/week hit; commits fail until weekly reset. Controller is
  resumable, so continue next reset.
- Probe AUC < 0.85 -> Stage 2 gate; do not proceed (PLAN.md Stage 2).
