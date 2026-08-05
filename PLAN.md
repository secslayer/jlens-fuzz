# Research Automation Plan — Interpretability-Guided Jailbreak Fuzzing

> **NOTE (Kaggle-only path):** `RUNBOOK.md` v2 and `ORCHESTRATION.md` are authoritative for the
> free Kaggle-only workflow. Mentions of RunPod/OpenRouter/Kimi-K3 below are legacy context;
> the actual pipeline uses Kaggle only, and RQ3 transfer replays prompts on a second small
> open-weight model **locally** (Phi-3.5-mini), no external API.


**Scope (honest):** a *proof-of-concept preprint* in ~1 week. One white-box target you can
actually run (`Qwen2.5-3B-Instruct`), 50 AdvBench behaviors, refusal probes as the
interpretable signal (logit-lens/J-lens motivation, linear-probe realization), the
**seed-free ablation as the headline**, and RQ3 transfer done **locally on Kaggle** by replaying
optimized prompts on a second small open-weight model (Phi-3.5-mini). No external API — Kaggle only.

Everything below is designed to be executed by **Claude Code** with **peer-review gates**
between stages. Nothing proceeds to the next stage until its gate passes.

---

## 1. The three-plane architecture

Keep these mentally separate — most confusion comes from conflating them.

| Plane | What runs there | Free option | Paid upgrade |
|---|---|---|---|
| **Control plane** | Claude Code (writes/edits code, runs the loop, drafts paper) | Your laptop terminal | RunPod box (SSH) |
| **Compute plane** | The GPU that hosts Qwen + judge + activation extraction | Kaggle headless commits | RunPod 24GB GPU |
| **Storage plane** | Code, results, checkpoints, paper | GitHub + Google Drive | same |

**Free path (recommended to start):** Claude Code on your laptop → push to GitHub →
Kaggle notebook `git clone`s and runs the heavy job as a *headless commit* (up to ~12h,
30 GPU-hrs/week) → artifacts saved to a Kaggle Dataset + mirrored to Google Drive/GitHub.

**Paid path (~$10–25 total, tighter loop):** rent a RunPod 24GB card (~$0.30–0.44/hr),
`tmux` + Claude Code **on the box**, everything runs against the local GPU. Lets you use a
7B model. Use this if Kaggle's push→wait loop frustrates you.

> Why not tmux/Claude Code *inside* Kaggle? Kaggle kernels have no SSH, no persistent
> shell, and a hard session timeout. tmux + interactive Claude Code only make sense on a
> box you control (laptop or RunPod). On Kaggle you run **headless commits**, not sessions.

---

## 2. Prerequisite tools (install once) — with links

Install on the **control plane** machine (laptop or RunPod box):

- **git** — https://git-scm.com/downloads
- **GitHub CLI (`gh`)** — https://cli.github.com  (for `gh repo create`, `gh release`)
- **Node.js LTS** (Claude Code needs it) — https://nodejs.org/en/download
- **Claude Code** — https://docs.claude.com/en/docs/claude-code/overview
  install: `npm install -g @anthropic-ai/claude-code` then run `claude` and sign in with
  your $20 Pro account.
- **uv** (fast Python env/dep manager) — https://docs.astral.sh/uv/getting-started/installation/
- **tmux** (paid path only) — https://github.com/tmux/tmux/wiki/Installing
- **Kaggle API** — https://github.com/Kaggle/kaggle-api  (`pip install kaggle`, then put
  `kaggle.json` token in `~/.kaggle/`)
- **Hugging Face CLI** — https://huggingface.co/docs/huggingface_hub/guides/cli
  (`hf auth login` with a read token — free)

Learning links if any tool is new:
- git basics — https://git-scm.com/book/en/v2
- GitHub Flow (branch/PR) — https://docs.github.com/en/get-started/using-github/github-flow
- tmux quickstart — https://tmuxcheatsheet.com

---

## 3. Accounts & secrets (all free)

1. **GitHub** — create a **private** repo `jlens-fuzz` (`gh repo create jlens-fuzz --private`).
2. **Kaggle** — verify phone to unlock GPU; generate API token → `~/.kaggle/kaggle.json`.
3. **Hugging Face** — free read token for model/dataset downloads.
4. **Google Drive** — for checkpoint/result mirroring (Kaggle datasets are the primary store;
   Drive is backup). Mount in Kaggle via the `kaggle datasets` flow, not Drive directly.
6. **Anthropic / Claude Code** — your existing $20 Pro login.

**Secret hygiene:** put all tokens in a `.env` that is `.gitignore`d. Never let Claude Code
commit `.env`, `kaggle.json`, or any generated jailbreak strings. This is enforced in
`CLAUDE.md`.

---

## 4. Compute setup in detail

### 4A. Free path — Kaggle headless commits

The pattern for every heavy job:

1. Claude Code writes/updates the job script and pushes to GitHub.
2. A thin Kaggle notebook (kept in the repo as `scripts/kaggle_runner.ipynb`) does:
   ```python
   !git clone https://github.com/<you>/jlens-fuzz && cd jlens-fuzz && pip install -r requirements.txt
   !python scripts/<stage_script>.py --config configs/exp.yaml
   ```
   Enable **GPU T4×2**, **Internet on**, then **Save Version → Save & Run All (Commit)**.
   The commit runs headless in the background; you close the tab.
3. Outputs written to `/kaggle/working/results/` are captured in the commit; export them as
   a **Kaggle Dataset** so the next kernel can mount them, and `gh release upload` the small
   JSON/CSV metrics back to GitHub.

Budget the 30 GPU-hrs/week: probe training and each 50-behavior run are the costly steps.
Do dry runs on 5 behaviors before spending a full run.

### 4B. Paid path — RunPod + tmux + Claude Code on the box

```bash
# after SSHing into the RunPod instance
tmux new -s research            # create a persistent session
# inside tmux:
git clone https://github.com/<you>/jlens-fuzz && cd jlens-fuzz
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv
uv venv && source .venv/bin/activate && uv pip install -r requirements.txt
npm install -g @anthropic-ai/claude-code && claude   # sign in, then let it drive
# detach with Ctrl-b then d ; reattach later with:  tmux attach -t research
```

**tmux survival kit:** `Ctrl-b d` detach · `tmux attach -t research` reattach ·
`Ctrl-b c` new window · `Ctrl-b "` split · `Ctrl-b [` scroll (q to exit scroll).
Run long jobs inside tmux so a dropped SSH connection doesn't kill them.

---

## 5. Claude Code configuration (the automation brain)

Files already scaffolded in this repo:

- **`CLAUDE.md`** — project context + hard rules. Keep it under ~200 lines (Anthropic
  guidance) so it doesn't eat your token budget every turn.
- **`Makefile`** — one command per stage (`make probes`, `make ours`, …). Claude Code runs
  these; you read the logs.
- **`.claude/agents/reviewer.md`** — a **peer-review subagent** invoked at every gate.
- **`.claude/commands/review.md`** — a `/review` slash command that runs the reviewer against
  the current stage's outputs.

Set these up per current docs (syntax may have moved since this was written):
- Subagents — https://docs.claude.com/en/docs/claude-code/sub-agents
- Slash commands — https://docs.claude.com/en/docs/claude-code/slash-commands
- Settings & hooks — https://docs.claude.com/en/docs/claude-code/settings

**How the peer review works:** the `reviewer` subagent runs in a *fresh context* (it hasn't
seen the code get written, so it reviews adversarially, not sympathetically). It reads the
stage's outputs + the stage checklist in this plan, and must emit `PASS` or `FAIL` with
concrete reasons, written to `reviews/stageN.md`. **You do not advance on FAIL.** Some gates
also require a **human check** (marked 👤) that no agent can sign off — probes, judge labels,
and ethics.

---

## 6. Stage-by-stage plan with peer-review gates

Each stage: **Goal → Agent tasks → `make` target → Gate (checklist) → Exit criteria**.
Run `/review` at each gate. Log to `reviews/stageN.md`. Fix and re-review on FAIL.

### Stage 0 — Repo & environment (Day 1 morning)
- **Agent tasks:** finalize repo structure, `requirements.txt`, `.gitignore` (must include
  `.env`, `*.json` keys, `results/**/prompts_*`, checkpoints), wire the Makefile, commit,
  push, create the private GitHub repo, smoke-test the Kaggle runner on CPU.
- **Target:** `make setup`
- **Gate 0 checklist:**
  - [ ] `.gitignore` blocks secrets and generated attack strings (grep the repo history).
  - [ ] `requirements.txt` installs clean in a fresh env.
  - [ ] Kaggle runner clones + imports with no error (CPU dry run).
  - [ ] CLAUDE.md guardrails present and readable.
- **Exit:** green CI (pytest placeholder passes), Kaggle dry run succeeds.

### Stage 1 — Model + judge load, baseline sanity (Day 1 afternoon)
- **Agent tasks:** load `Qwen2.5-3B-Instruct` and the RoBERTa judge (`hubert233/GPTFuzz`)
  on Kaggle GPU; run 20 raw harmful behaviors through the model; confirm it *refuses* most
  (establishes there's something to jailbreak) and the judge scores them correctly.
- **Target:** `make sanity`
- **Gate 1 checklist:**
  - [ ] Model generates coherently with the correct chat template.
  - [ ] Judge agrees with 10 hand-labeled examples (👤 you label them).
  - [ ] Baseline refusal rate on raw harmful prompts is high (else nothing to measure).
- **Exit:** judge validated; refusal baseline recorded in `results/sanity.json`.

### Stage 2 — Refusal probes (Day 2) — **make-or-break**
- **Agent tasks:** build the counterfactual set (harmful vs. harmless instructions), extract
  last-token residual activations at every layer, train per-layer logistic probes, pick the
  best layer by held-out AUC. Script: `scripts/train_probes.py` (already written).
- **Target:** `make probes`
- **Gate 2 checklist (👤 mandatory human check):**
  - [ ] Best-layer held-out **AUC ≥ 0.85** (if not, the whole method's signal is weak — stop
        and reconsider before wasting the week).
  - [ ] Probe separates a few *novel* hand-written harmful/benign prompts (👤 you write 6).
  - [ ] Chosen layer is in a sensible mid/late band, not layer 0 (would indicate leakage).
- **Exit:** `results/probes/best_layer.json` + probe weights saved. **If AUC < 0.85, you
  reframe now** (e.g., ensemble layers, mean-pool tokens) rather than on Day 7.

### Stage 3 — Fitness swap into the fuzzing loop (Day 3)
- **Agent tasks:** fork `sherdencooper/GPTFuzz`, replace the fitness call with a **partial
  forward pass to the probe layer** scored by the probe (lower refusal-prob = higher
  fitness); full generation + judge only on elite candidates. Get first end-to-end jailbreaks
  on 5 behaviors; log queries-to-success and compute.
- **Target:** `make ours SMOKE=1`
- **Gate 3 checklist:**
  - [ ] Loop produces ≥1 judge-confirmed jailbreak on the 5-behavior smoke set.
  - [ ] Partial-forward fitness runs and is cheaper than full-judge fitness (logged FLOPs/
        wall-clock show the gap).
  - [ ] No harmful strings written to any git-tracked path (grep).
- **Exit:** smoke run green; efficiency delta recorded.

### Stage 4 — Seed-free ablation (Day 4) — **the headline**
- **Agent tasks:** implement workspace-derived seed generation (read candidate framings from
  the probe/logit-lens signal; fall back to a minimal generic seed if empty), then run the
  ablation: full human seeds → 5 seeds → **0 human seeds**. This is the plot the preprint
  lives on.
- **Target:** `make ablation-seeds`
- **Gate 4 checklist:**
  - [ ] Zero-human-seed condition runs end to end.
  - [ ] ASR at 0 seeds is reported honestly (even if lower — a modest but non-trivial ASR
        with *no* human seeds is still the story).
  - [ ] Result reproducible from a fixed seed/config.
- **Exit:** `results/ablation_seeds.json` + the plot.

### Stage 5 — Full runs + baselines (Day 5)
- **Agent tasks:** run **your method** and the **GPTFuzzer baseline** (and AutoDAN if time)
  on all 50 behaviors, *identical* judge/budget/decoding — this is the only valid way to
  compare (you cannot borrow numbers from the papers). Collect ASR, queries-to-success,
  compute, perplexity, diversity.
- **Target:** `make baseline-gptfuzzer && make baseline-autodan && make ours`
- **Gate 5 checklist:**
  - [ ] All methods ran under identical conditions (assert config invariants match).
  - [ ] Metrics complete for every method (no missing cells).
  - [ ] 👤 You hand-validate ~50 judge labels; report judge/human agreement.
- **Exit:** `results/main_table.json` populated and cross-checked.

### Stage 6 — local transfer + interpretability panels (Day 6)
- **Agent tasks:** replay the optimized prompts on a second small open-weight model **locally on Kaggle** (Phi-3.5-mini, black-box),
  log transfer ASR; generate the qualitative logit-lens/probe readout panels (success vs.
  failure) that a scalar-probe method can't produce.
- **Target:** `make job JOB=transfer_local && make figures`
- **Gate 6 checklist:**
  - [ ] Transfer target loaded and ran locally on a T4 (no external API).
  - [ ] Figures regenerate from `results/*.json` with one command (reproducibility).
  - [ ] Readout panels actually show the concept collapse you claim (👤 sanity check).
- **Exit:** all 7 figures/tables built.

### Stage 7 — Write, review, release (Day 7)
- **Agent tasks:** draft all sections from the numbers (no invented results), assemble the
  arXiv PDF, clean the repo, tag `v1.0-arxiv`, write README + `CITATION.cff`, gate dangerous
  artifacts.
- **Target:** `make paper && make release`
- **Gate 7 checklist (full peer review + 👤):**
  - [ ] Every number in the paper traces to a `results/*.json` file (agent verifies).
  - [ ] Related-work explicitly distinguishes Mechanistic AutoDAN (2605.28553).
  - [ ] Ethics + responsible-disclosure section present.
  - [ ] 👤 No harmful content in repo or paper appendix; disclosure statement final.
- **Exit:** arXiv submitted, repo tagged.

---

## 7. Metrics spec (what every run must log)

Every method writes one JSON per run with: `asr` (judge), `asr_human_subset`,
`queries_to_success` (per behavior + median), `full_forward_passes`, `partial_forward_passes`,
`wall_clock_s`, `mean_prompt_perplexity`, `self_bleu`, `distinct_2`, and (transfer runs)
`transfer_asr`. The `make figures` step reads only these files — so a lost session never
loses your results.

## 8. Ethics & disclosure gate (non-negotiable, 👤)

- Public benchmarks only (AdvBench); no new harmful capability introduced.
- White-box work on small open-weight models; transfer target used black-box only.
- Repo ships **no** generated successful-jailbreak strings; provide a regeneration script
  behind an ethics notice instead.
- Include an "Ethics Considerations" section + a defense suggestion (monitor the probe signal
  at runtime) — required at security venues and it strengthens the paper.
- Disclose to the affected open-weight maintainer(s) before publicizing transfer results.

## 9. Publish checklist

- [ ] arXiv preprint (cs.CR + cs.CL), `v1.0-arxiv` git tag matching it.
- [ ] README: pitch → install → reproduce Table 1 → results → ethics → BibTeX → license (MIT).
- [ ] `CITATION.cff` so GitHub shows "Cite this repository".
- [ ] All 4 prior works cited and distinguished; closest competitor named in the abstract's
      differentiation sentence.
