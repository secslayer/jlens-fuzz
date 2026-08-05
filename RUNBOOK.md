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

**Day 4 - Stage 4 (headline ablations) + kick off full runs.**
- [L] `/orchestrate core` -> `ours, gptfuzzer, abl_mut_uniform, abl_seed_random,
  abl_seed_bootstrap, validate` become ready -> launch the first batch on the 2 commit runners (Part 6).

**Day 5 - Stage 5 (finish the matrix in parallel).**
- [B] Keep the controller's batches flowing across the 2 runners until all core method/ablation jobs
  are done. [H] Gate 5: hand-validate ~50 judge labels; assert identical `configs/exp.yaml`. `/review 5`.

**Day 6 - Stage 6 (local transfer + figures).**
- [L] builder: `scripts/transfer_blackbox.py` (`--local`, target from `transfer_target_local`) and
  `scripts/make_figures.py`. Push.
- [L] `/orchestrate core` -> `transfer_local` then `figures` become ready -> run them. `/review 6`.

**Day 7 - Stage 7 (write + release).**
- [L] builder: `scripts/assemble_paper.py`; draft `paper/` from `results/*.json` only. Related-work
  must distinguish Mechanistic AutoDAN (2605.28553). Ethics section required. `/review 7`, [H] sign-off.

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

1. [L] `make paper`, review the PDF.
2. [B] https://arxiv.org -> login/register (institutional email helps).
3. [B] **Endorsement gotcha:** first-time `cs.CR`/`cs.CL` authors may need an endorsement
   (https://arxiv.org/help/endorsement). Arrange it by Day 5 so it doesn't block you.
4. [B] **Submit -> Start New Submission** -> primary `cs.CR`, cross-list `cs.CL` -> upload PDF/LaTeX
   -> title/abstract/authors -> **Preview -> Submit**. Announced next business day.
5. [L] Tag the release:
   ```bash
   git tag v1.0-arxiv && git push --tags
   gh release create v1.0-arxiv --title "v1.0 (arXiv)" --notes "Preprint release"
   ```
6. [B] Add `CITATION.cff` + the arXiv ID to the README (GitHub shows "Cite this repository").

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
