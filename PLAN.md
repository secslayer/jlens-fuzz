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
- **Target:** `python scripts/run_fuzz.py --config configs/exp.yaml --method ours --mutation
  guided --seedtier human --fitness judge --smoke` (there is no `make ours` target or `SMOKE`
  variable — that line was documentation drift, corrected 2026-08-06 per `reviews/stage3.md`;
  the actual manifest job `make job JOB=ours` runs the full (non-smoke) config).
- **Gate 3 checklist (2026-08-06 update — see `reviews/stage3-human-signoff.md`):**
  - [x] Loop produces ≥1 judge-confirmed jailbreak on the 5-behavior smoke set.
  - [ ] ~~Partial-forward fitness runs and is cheaper than full-judge fitness~~ — **descoped from
        this gate.** That path runs on the Stage 2 probe signal already proven not to generalize
        (`reviews/stage2-human-signoff.md`); an efficiency number from a signal known to be
        unreliable isn't a meaningful pass/fail check. Deferred to the Day 5 extended-lane
        `abl_fitness_probeact` run, reported there as a finding, not a gate.
  - [x] No harmful strings written to any git-tracked path (grep).
- **Exit:** smoke run green (both remaining checklist items closed); efficiency delta deferred to
  Day 5, not blocking.

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

## 10. Target-difficulty ladder (RQ3) — planned core part of the paper

**Status (2026-08-06): PLANNED CORE, not "maybe later."** Superseded the original framing of
this section (extended-lane, indefinite). Sequencing still matters, though: **do not launch any
target below until the Qwen2.5-3B core lane (Stages 4–7) is complete and reviewed** — Qwen is the
"easy/control" tier this whole axis is measured relative to, and it's the only tier with a full
reviewed matrix so far. `experiments.yaml`/`configs/` are scaffolded (see below); the manifest
jobs are `lane: extended` specifically so the normal `run_controller.py --lane core` workflow
cannot accidentally launch them — that flag flip (or explicit `--lane all`) is the actual trigger
for "sequenced after Qwen lane completes," not just a comment.

**Difficulty is measured empirically in our own setting, not cited from literature** — jailbreak
difficulty is attack- and category-dependent, so a number from a different judge/method/benchmark
isn't a defensible ordering here. Smoke-test each target first (5 behaviors × 5 methods) before
committing it to a full run; if a target saturates at ASR≈1.0 in ~3 queries like Qwen did, it adds
nothing over the control and should be dropped.

### Tier table

| Tier | Model | Gated? | VRAM strategy | Config |
|---|---|---|---|---|
| easy / control | `Qwen/Qwen2.5-3B-Instruct` | No | 1×T4, fp16 (~6GB) | `configs/exp.yaml` (running now) |
| same-size / family | `microsoft/Phi-4-mini-instruct` | No | 1×T4, fp16 (~8GB) | `configs/exp_phi4mini.yaml` |
| larger / same-family | `Qwen/Qwen2.5-7B-Instruct` | No | 1×T4, fp16 (~14GB, tight) | `configs/exp_qwen7b.yaml` |
| **HARD (capstone)** | `google/gemma-2-9b-it` | **Yes (manual)** | **both T4s**, fp16, `device_map="auto"` | `configs/exp_gemma9b.yaml` |

`mistralai/Mistral-7B-Instruct-v0.3` is optional, budget-permitting only — first to drop if GPU
budget runs short.

**Dropped, with reasons:** `Llama-3.1-8B-Instruct` (HF-gated AND ~16–18GB fp16, over one T4 —
Gemma is the better-evidenced hard target, no need for both). `gpt-oss-120b` (~240GB fp16,
impossible on a T4). `gpt-oss-20b` (would require 4-bit quantization, which is explicitly
disallowed here — see below).

**Gemma-2-9B-IT is the designated hard target and the insurance policy against this axis showing
nothing:** it has the only consistent, citable difficulty gap among the candidates considered
(reported ~8% ASR vs. Llama-3.1's ~22% on HarmBench). Sequenced **last** — if the ungated mid-tier
(Phi-4-mini, Qwen2.5-7B) already shows real headroom over Qwen's saturation, Gemma is a bonus; if
they all saturate the way Qwen did, Gemma is what makes the difficulty-axis claim defensible at
all. Two blockers must be resolved before it can run (confirmed 2026-08-06, not yet fixed — see
`configs/exp_gemma9b.yaml`'s header comment):
1. Gated on Hugging Face (verified live, `gated: "manual"`) — request access ahead of time,
   approval isn't instant.
2. Every model-loading script in this repo (`run_fuzz.py`, `train_probes.py`,
   `extract_direction.py`, `sanity_check.py`, `validate_signal.py`, `probe_novel_check.py`)
   currently hardcodes single-GPU (`device = "cuda" if ... else "cpu"` → `.to(device)`), confirmed
   via grep — none use `device_map`. `scripts/run_parallel.sh` also assumes two independent
   single-GPU jobs (`CUDA_VISIBLE_DEVICES=0`/`=1`), which doesn't fit a one-job-both-GPUs run
   either. Both need fixing before Gemma can be attempted; not done yet, scaffold only.

**FP16 is non-negotiable across every tier — never quantize.** The refusal direction was
validated in fp16 (Stage 2); quantization would corrupt the activation signal the whole method
depends on. For any VRAM-tight target, split across both T4s via `device_map="auto"` instead of
reaching for 4-bit/8-bit.

### Per-target pipeline cost

Each new target needs its own Stage 1 (baseline refusal, `sanity_check.py`) and Stage 2
(`train_probes.py` + `extract_direction.py`, plus Gate 2's novel-prompt check) re-run — the
refusal direction is model-specific, not transferable across targets. Budget for this; it is not
optional plumbing.

### Rigor requirements (this is what makes the result strong on a free-tier budget, not model
count)

- **3 seeds per (target × method) condition.** Non-negotiable — single-run ASR/queries-to-success
  numbers will not survive review. Report ASR and median-queries with 95% bootstrap or Wilson
  confidence intervals.
- Full queries-to-success distribution (quartiles), not just the median.
- Per-AdvBench-category ASR breakdown — guided mutation may help disproportionately on hard
  categories even when overall ASR ties with the uniform-mutation ablation.
- `guided_fire_count`/`guided_fallback_count` (already in `run_fuzz.py`'s output schema, added
  2026-08-06) committed per run as proof guided mutation actually fired, not silently fell back to
  uniform on every iteration.

### Budget reality — Kaggle free tier only (~30 GPU-hr/week)

Depth over breadth: 2–3 targets with real 3-seed confidence intervals beats 4 targets run once.
If budget runs short, cut targets (Mistral first, then Qwen2.5-7B) before ever cutting seed count
or CIs. Spread across multiple weeks if needed. Gemma runs consume both T4s for one job — no
parallel second job during those sessions, effectively half throughput; budget for it explicitly
rather than being surprised by it.

**Worked GPU-hour estimate (2026-08-06).** Anchored on the ONE real measured data point available
at scaffold time — `results/ours_smoke.json`: 84.6s / 14 full queries = **6.04s/query, measured,
Qwen2.5-3B, 1×T4**. Everything else below is a labeled estimate (linear-in-params scaling for
model size, +50% for Gemma's dual-GPU pipeline-split overhead — naive `device_map="auto"` sharding
does not give a 2x speedup for single-sequence autoregressive decoding, sometimes a slowdown), not
measured — replace with each target's own real smoke-test number before committing further
budget to it.

Full 5-method matrix, 50 behaviors, ×3 seeds, in GPU-hours (= wall-clock × number of GPUs used):

| Target | best case (~3 q/behavior, Qwen-like) | realistic (~30 q/behavior avg) | worst case (full 50-q budget every time) |
|---|---:|---:|---:|
| Qwen2.5-3B (1 GPU) | 3.8 | 37.8 | 63.0 |
| Phi-4-mini (1 GPU) | 4.8 | 48.0 | 79.9 |
| Qwen2.5-7B (1 GPU) | 8.8 | 88.0 | 146.9 |
| Gemma-2-9B (2 GPUs) | 17.0 | 340.0 | 566.5 |

Stage 1–2 per target (sanity + probes + direction, rough — none of those three scripts log
`wall_clock_s` yet, unlike `run_fuzz.py`) is small by comparison: **~0.15–0.75 GPU-hr**, growing
with target size; not the budget bottleneck.

**Reading this table:** even the "realistic" column for all 4 targets × 3 seeds sums to roughly
**500+ GPU-hours ≈ 17 weeks** at 30/week — confirms the "depth over breadth, cut targets before
cutting seeds" rule above is load-bearing, not caution for its own sake. In practice: smoke-test
each target for real numbers, then decide tier-by-tier whether it earns its 3-seed budget, cutting
from the bottom of the tier table first.

### Implementation notes

- Config-driven, not hardcoded: one `configs/exp_<tag>.yaml` per tier (`configs/exp.yaml` stays
  the Qwen/control config, unchanged), identical to it in every invariant except
  `target_model`/`mutate_model` — see CLAUDE.md rule 3.
- `experiments.yaml` job family per target: `probes_<tag>`, `direction_<tag>`, `validate_<tag>`,
  `gptfuzzer_<tag>`, `ours_<tag>`, `abl_mut_uniform_<tag>`, `abl_seed_bootstrap_<tag>`,
  `abl_seed_random_<tag>` — same 8-job shape as the Qwen tier, results namespaced under
  `results/<tag>/`. No underlying script needed code changes to support this (every script
  already accepted explicit `--out`/`--probes`/`--direction` overrides) except one real bug fix:
  `run_fuzz.py`'s gitignored raw-prompt side-file path used to derive from `--out`'s basename
  only, which would have silently collided across two different targets' runs; it now derives
  from the full relative `--out` path instead.
