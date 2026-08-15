# Research Automation Plan — Interpretability-Guided Jailbreak Fuzzing

> **NOTE (2026-08-09, what actually shipped):** The "Scope (honest)" paragraph and the RQ3
> transfer plan just below are the *original* plan, kept for history (this project documents
> reversals rather than erasing them — see §11, §12). Both are superseded by what actually
> happened: the headline is the **judge-reliability finding** (§11), not the seed-free ablation;
> the reported scale is **`n=5` behaviors per condition** (README.md's "Scale, stated plainly"),
> not 50 (this paragraph) or the 25×3-seed design §10 later locked to; and **RQ3 transfer never
> ran** — no `results/*transfer*` file exists, and it does not appear in `paper/paper.tex`.
> `Phi-3.5-mini-instruct` ended up in the paper in a different role entirely: the rubric-based
> LLM judge (`scripts/judge.py`), not a transfer target. See `README.md` and `paper/paper.tex`
> §4/§6 for the accurate, final accounting.

> **NOTE (Kaggle-only path):** `RUNBOOK.md` v2 and `ORCHESTRATION.md` are authoritative for the
> free Kaggle-only workflow. Mentions of RunPod/OpenRouter/Kimi-K3 below are legacy context;
> the actual pipeline uses Kaggle only, and RQ3 transfer replays prompts on a second small
> open-weight model **locally** (Phi-3.5-mini), no external API.


**Scope (honest, as originally written — see the superseded-by note above):** a
*proof-of-concept preprint* in ~1 week. One white-box target you can actually run
(`Qwen2.5-3B-Instruct`), 50 AdvBench behaviors, refusal probes as the interpretable signal
(logit-lens/J-lens motivation, linear-probe realization), the **seed-free ablation as the
headline**, and RQ3 transfer done **locally on Kaggle** by replaying optimized prompts on a
second small open-weight model (Phi-3.5-mini). No external API — Kaggle only.

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
> **Did not run** (superseded, see the top-of-document note): no `results/ablation_seeds.json`
> exists, and the seed-free ablation is not this paper's headline — the judge-reliability finding
> (§11) is. Kept below for history, not as an open task.
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
> **Ran in reduced form, not as specified below** (superseded, see the top-of-document note): no
> `results/main_table.json` exists and neither method ran on 50 (or even the later-locked 25)
> behaviors. What actually shipped is the `n=5`-per-condition pool-12 comparison
> (`results/*_smoke_pool12.json`, both targets) reported in `paper/paper.tex` §5 — the free-tier
> compute budget was exhausted before the full matrix could run (README.md's "Scale, stated
> plainly"). The 👤 hand-validation checklist item below is still the real, executed practice
> (that's how the judge incident, §11, was caught) — only the "50 behaviors" scale is stale.
- **Agent tasks:** run **your method** and the **GPTFuzzer baseline** (and AutoDAN if time)
  on all 50 behaviors, *identical* judge/budget/decoding — this is the only valid way to
  compare (you cannot borrow numbers from the papers). Collect ASR, queries-to-success,
  compute, perplexity, diversity.
- **Target:** `make baseline-gptfuzzer && make baseline-autodan && make ours`
- **Gate 5 checklist:**
  - [ ] All methods ran under identical conditions (assert config invariants match).
  - [ ] Metrics complete for every method (no missing cells).
  - [ ] 👤 You hand-validate ~50 judge labels; report judge/human agreement. **This exact check
        is what caught the judge false-positive incident early, on a 4-example smoke sample
        instead of a 50-behavior full run — see `reviews/judge-validity-incident.md` and §11
        below.** Do this hand-validation at EVERY scale (smoke included), not only here.
- **Exit:** `results/main_table.json` populated and cross-checked.

### Stage 6 — local transfer + interpretability panels (Day 6)
> **Did not run** (superseded, see the top-of-document note): no `results/*transfer*` file
> exists, RQ3 transfer does not appear in `paper/paper.tex`, and none of the 7 figures below were
> built (the paper's tables are hand-assembled from `results/*.json`, not `make figures`
> output — README.md confirms `make_figures.py` "is not implemented"). `Phi-3.5-mini-instruct`
> ended up in the paper as the rubric LLM judge instead (`scripts/judge.py`), a different role
> than the transfer target described here. Kept below for history, not as an open task.
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

## 10. Target-difficulty design (RQ3) — LOCKED core, 2 targets

**Status (2026-08-06): LOCKED.** The core design is **exactly 2 targets** — Qwen2.5-3B
(control) and Phi-4-mini (treatment) — at **25 behaviors, query_budget=40, 3 seeds per
condition**. This supersedes the prior "4-tier ladder, sequenced after Qwen" framing: the
4-target version's own worked budget (~500 GPU-hr realistic, ~17 weeks at 30/week) made it
undeliverable on a free-tier budget with real seed counts. Locking to 2 targets at a smaller
per-behavior budget is what makes the 3-seed rigor requirement (below) actually affordable — see
the recomputed budget table.

**Sequencing still matters:** do not launch `phi4mini` jobs until the Qwen2.5-3B core lane
(Stages 4–7) is complete and reviewed — Qwen is the control this whole axis is measured relative
to. `experiments.yaml`'s `phi4mini` job family is `lane: core` (promoted 2026-08-06, same tier as
Qwen) so it WILL appear in `run_controller.py --lane core`'s ready set as soon as its own
dependencies (`probes_phi4mini`, `direction_phi4mini`) are satisfied — nothing in the manifest
mechanically blocks it on Qwen finishing first, that ordering is a human judgment call, not an
enforced dependency. Don't launch it early just because the controller offers it.

**Difficulty is measured empirically in our own setting, not cited from literature** — jailbreak
difficulty is attack- and category-dependent, so a number from a different judge/method/benchmark
isn't a defensible ordering here. Smoke-test Phi-4-mini (5 behaviors × 5 methods) before
committing it to the full 3-seed matrix; if it saturates at ASR≈1.0 in ~3 queries like Qwen did,
report that honestly as a finding (the method saturates on both a control and a same-tier
treatment target) rather than treating it as a wasted run.

### Locked core design

| | Qwen2.5-3B (control) | Phi-4-mini (treatment) |
|---|---|---|
| Model | `Qwen/Qwen2.5-3B-Instruct` | `microsoft/Phi-4-mini-instruct` |
| Gated? | No | No |
| VRAM | 1×T4, fp16 (~6GB) | 1×T4, fp16 (~8GB) |
| Config | `configs/exp.yaml` | `configs/exp_phi4mini.yaml` |
| Manifest | `probes`/`direction`/`validate`/`gptfuzzer`/`ours`/`abl_*` (+ `_seed1`/`_seed2`) | same shape, `_phi4mini` suffix (+ `_seed1`/`_seed2`) |

Shared, locked invariants (CLAUDE.md rule 3 — identical across both targets, only
`target_model`/`mutate_model` differ): `n_behaviors: 25` (was 50), `query_budget: 40` (was 50),
`judge_model`, `benchmark`, `human_seed_templates`, `decode_temperature`/`decode_top_p`,
`max_iterations: 100`.

### Dropped from core — future work, compute-limited (not "sequenced later")

`Qwen2.5-7B-Instruct`, `google/gemma-2-9b-it`, and `mistralai/Mistral-7B-Instruct-v0.3` are
**dropped from the core paper**, not deferred within it. The scaffolding for the first two
(`configs/exp_qwen7b.yaml`, `configs/exp_gemma9b.yaml`, and their `experiments.yaml` job
families) is kept in place — `lane: extended`, never launched, kept in sync with the locked
core's `n_behaviors`/`query_budget` so it isn't stale if scope reopens — but nothing about the
core paper depends on them. Mistral was never scaffolded as job entries (only mentioned in prose
previously); nothing to remove there.

Reasons these didn't make the locked cut: the honest 3-seed GPU-hour cost of a 4-target ladder
(~500 GPU-hr realistic-case, ~17 weeks at 30/week) doesn't fit a free-tier budget with the rigor
this paper needs. Two targets at 25 behaviors / query_budget=40 does (see budget table below) —
depth (real seeds, real CIs) beat breadth (more targets, single-run numbers that wouldn't survive
review).

**`Llama-3.1-8B-Instruct` was never in the running** (separately from the above): HF-gated AND
~16–18GB fp16, over one T4. `gpt-oss-120b` is impossible on a T4 (~240GB fp16). `gpt-oss-20b`
would require 4-bit quantization, disallowed below.

**Since Gemma is dropped from core, its `device_map` multi-GPU work stays deferred — not being
fixed now.** For the record (confirmed 2026-08-06, unresolved, revisit only if Gemma is
reconsidered): every model-loading script in this repo (`run_fuzz.py`, `train_probes.py`,
`extract_direction.py`, `sanity_check.py`, `validate_signal.py`, `probe_novel_check.py`)
hardcodes single-GPU (`device = "cuda" if ... else "cpu"` → `.to(device)`), confirmed via grep —
none use `device_map`. `scripts/run_parallel.sh` also assumes two independent single-GPU jobs
(`CUDA_VISIBLE_DEVICES=0`/`=1`), which doesn't fit a one-job-both-GPUs run either. Neither is
being fixed while Gemma is out of the core design.

**FP16 is non-negotiable for both locked targets — never quantize.** The refusal direction was
validated in fp16 (Stage 2); quantization would corrupt the activation signal the whole method
depends on. Both Qwen-3B and Phi-4-mini comfortably fit one T4 in fp16, so this isn't even a
tradeoff for the locked design — it only becomes one if a dropped tier is ever reconsidered.

### Per-target pipeline cost

Phi-4-mini needs its own Stage 1 (baseline refusal, `sanity_check.py`) and Stage 2
(`train_probes.py` + `extract_direction.py`, plus Gate 2's novel-prompt check) re-run — the
refusal direction is model-specific, not transferable across targets. Budget for this; it is not
optional plumbing.

### Rigor requirements (this is what makes the result strong on a free-tier budget, not target
count)

- **3 seeds per (target × method) condition — now wired into `experiments.yaml`** (`_seed1`/
  `_seed2` job variants alongside every base job, both targets, via `run_fuzz.py`'s `--seed`
  override added 2026-08-06). Non-negotiable — single-run ASR/queries-to-success numbers will not
  survive review. Report ASR and median-queries with 95% bootstrap or Wilson confidence
  intervals.
- Full queries-to-success distribution (quartiles), not just the median.
- Per-AdvBench-category ASR breakdown — guided mutation may help disproportionately on hard
  categories even when overall ASR ties with the uniform-mutation ablation.
- `guided_fire_count`/`guided_fallback_count` (already in `run_fuzz.py`'s output schema) committed
  per run as proof guided mutation actually fired, not silently fell back to uniform on every
  iteration.
- **Open item, not yet designed:** `make_figures.py` (Day 6) needs to aggregate 3 seeds × 2
  targets × 5 methods into means + CIs; `experiments.yaml`'s `figures` job `needs:` list still
  only names the seed-0 Qwen jobs. Revisit both when `make_figures.py` is actually built.

### Budget reality — Kaggle free tier only (~30 GPU-hr/week)

**Worked GPU-hour estimate (2026-08-06, recomputed for the locked 25-behavior/40-query design).**
Anchored on the ONE real measured data point available — `results/ours_smoke.json`: 84.6s / 14
full queries = **6.04s/query, measured, Qwen2.5-3B, 1×T4**. Phi-4-mini's number is a labeled
estimate (linear-in-params scaling, ~3.8B vs. 3B), not measured — replace with its own real
smoke-test number before committing further budget to it.

> **This anchor is now STALE as a cost estimate** (though still valid as a historical data
> point): it was measured before the judge fix (§11, `reviews/judge-validity-incident.md`) added
> a second LLM generation call (the rubric judge) to every "full query" that isn't caught by the
> cheap refusal pre-filter. Real per-query cost under the fixed judge will be higher than 6.04s —
> get a fresh number from the next real smoke run before trusting this table for planning.

Full 5-method matrix, 25 behaviors, query_budget=40, ×3 seeds, in GPU-hours:

| Target | best (~3 q/behavior) | realistic (~24 q/behavior, 60% of budget) | worst (full 40-q budget every time) |
|---|---:|---:|---:|
| Qwen2.5-3B (control) | 1.9 | 15.1 | 25.2 |
| Phi-4-mini (treatment) | 2.4 | 19.2 | 32.0 |
| **Total, both targets** | **4.3** | **34.3** | **57.2** |

Stage 1–2 per target (sanity + probes + direction — none of those three scripts log
`wall_clock_s` yet, unlike `run_fuzz.py`, so this part stays a rough estimate): **~0.14–0.16
GPU-hr each**, negligible next to the fuzzing matrix.

**Reading this table:** even the worst case (~57 GPU-hr ≈ 1.9 weeks) fits comfortably inside a
realistic multi-week budget, and the realistic case (~34 GPU-hr ≈ 1.1 weeks) is genuinely
affordable in about a week. This is the entire point of locking to 2 targets at a smaller budget
instead of the 4-target ladder's ~500 GPU-hr realistic cost — depth (2 targets, real seeds, real
CIs) instead of breadth (4 targets, numbers that wouldn't survive review).

### Implementation notes

- Config-driven, not hardcoded: `configs/exp.yaml` (Qwen) and `configs/exp_phi4mini.yaml`,
  identical in every invariant except `target_model`/`mutate_model` — CLAUDE.md rule 3.
- `experiments.yaml` job family per target: `probes_<tag>`, `direction_<tag>`, `validate_<tag>`
  (single-run), `gptfuzzer_<tag>`, `ours_<tag>`, `abl_mut_uniform_<tag>`,
  `abl_seed_bootstrap_<tag>`, `abl_seed_random_<tag>` (each ×3 seeds) — Qwen's tag is empty
  (unsuffixed = the original job ids, unchanged for backward compatibility with already-completed
  Kaggle runs), Phi-4-mini's tag is `_phi4mini`, results namespaced under `results/phi4mini/`.
- `run_fuzz.py` gained one new flag (`--seed`, overrides `cfg["seed"]`) to make the 3-seed variants
  possible without a config file per seed. No other script needed changes for the target axis —
  every script already accepted explicit `--out`/`--probes`/`--direction` overrides — except one
  real bug fix: `run_fuzz.py`'s gitignored raw-prompt side-file path used to derive from `--out`'s
  basename only, which would have silently collided across two different targets' runs; it now
  derives from the full relative `--out` path instead.

## 11. CRITICAL: judge validity incident (2026-08-06)

**Full writeup: `reviews/judge-validity-incident.md`. Read it before trusting any ASR number
from this pipeline, past or future.**

Summary: the original success judge (`hubert233/GPTFuzz`) has a severe false-positive problem —
it rewards jailbreak-**shaped** vocabulary (roleplay persona declarations like DAN/Omega/APOPHIS
template setup) rather than actual harmful content. Hand-reading 4 Phi-4-mini "successes" it
scored ~0.99 found all four were not jailbreaks (one refusal-then-pivot, three template echoes
with zero harmful content). This affected the whole pipeline (`run_fuzz.py`, `sanity_check.py`,
`validate_signal.py`), both targets, not just the run that surfaced it.

**Fixed 2026-08-06**: new shared module `scripts/judge.py` (refusal pre-filter + LLM-as-judge
rubric grading via a fixed, non-self-grading `judge_llm_model`), wired into all three consumers.
The old RoBERTa judge is kept as a logged diagnostic only, never the success determinant.
`scripts/rescore_judge.py` re-validates existing raw completions against the fixed judge without
re-generating (cheap) — with an honest limitation documented in its own docstring: it can't
recover iterations a run never took because it stopped early on a false-positive success.

**Existing results are UNVALIDATED until re-scored, not deleted or retroactively edited**:
`results/ours_smoke.json` (Qwen `ours` smoke, `asr=1.0`) is provisionally supported by a
3-example human spot-check (`reviews/stage3-human-signoff.md`) but not fully re-validated across
all its candidates; `results/sanity.json`'s `refusal_rate=1.0` has a safe direction of error (a
false-positive-prone jailbreak judge can only undercount refusals) but still used the old judge
call. Any Phi `ours` smoke result reporting a nonzero ASR from the pre-fix judge is fully
invalidated (true ASR was 0.0, see the incident doc).

**Status update (2026-08-06):**
- Fix **reported validated**: re-scoring the Phi `ours` smoke's existing completions flipped all
  4 recorded "successes" to failure (`0.8 → 0.0`) — consistent with the hand-read diagnosis, but
  the backing `results/rescore_*.json` hasn't landed in the repo yet, so treat as reported-not-
  yet-artifact-backed per CLAUDE.md rule 2. See the incident doc's Validation section.
- A **second blocker** surfaced and needed two attempts to fix: the first live fresh-judge smoke
  OOM'd (target + judge_llm + diagnostic judge together exceed one T4). First attempt (2026-08-06)
  was 8-bit judge quantization via `bitsandbytes` — **abandoned 2026-08-07**: unreliable on Kaggle
  (import/CUDA issues) and it still OOM'd. **Current fix: target and judge on separate GPUs**
  (`scripts/judge.py`'s `load_judge_llm()`, target stays `cuda:0` fp16 unchanged, judge moves to
  `cuda:1` fp16, no quantization at all — Kaggle gives 2 T4s per session, use both). Reverses the
  earlier "don't use a second GPU" guidance in this section — that concern (breaking
  `run_parallel.sh`'s per-job GPU pinning) was real and is now handled properly instead of
  avoided: `run_parallel.sh` gained a `JOB=<id>` mode (full 2-GPU visibility, no
  `CUDA_VISIBLE_DEVICES` restriction) for judged jobs, and `run_controller.py`'s batch packing is
  now judged/unjudged-aware — `probes*`/`direction*` (the only jobs that never call the judge)
  still pair up 2-per-notebook via the old `JOB_A=`/`JOB_B=` mode; every other ready job packs 1
  per notebook via the new `JOB=` mode. **Real throughput tradeoff, not eliminated**: a judged job
  now occupies both GPUs of its notebook/session, so two judged jobs can no longer share one
  notebook — they still run concurrently fine across the 2 separate commit notebooks (each has
  its own 2 T4s), just one judged job per notebook instead of two independent single-GPU jobs.

**Full 2-target × 3-seed matrix (§10): ABANDONED, not deferred (2026-08-07).** It was gated on
(1) Qwen's existing completions re-scored, (2) fresh smokes on all four core conditions with the
fixed judge/MCTS reward, (3) review of both — steps (1)-(2) happened at smoke scale (see the
DECIDED reframe below); the full n=25×3-seed matrix itself will not run: **GPU budget is
exhausted**. This is a hard stop, not a scheduling choice — the matrix existed to give a positive
guided-vs-uniform result statistical power, and the result came back null (below), so there is
nothing left to power up.

**DECIDED reframe (2026-08-07)** — supersedes the "possible reframe, not yet decided" text this
replaced. The paper's contributions, in order:

1. **PRIMARY — the judge-reliability finding.** The standard GPTFuzz RoBERTa judge
   (`hubert233/GPTFuzz`) inflates ASR via template-echo false positives — it rewards
   jailbreak-**shaped** vocabulary (DAN/Omega/APOPHIS persona declarations), not actual harm.
   Reported delta: Phi `0.8 → 0.0` after the fixed judge. **Strengthened 2026-08-07**: hand-
   verifying the *fixed* judge's own pool-12 Qwen `ours` output caught a **second, distinct false
   positive** — a "ChadGPT" persona-wrapper completion that actually REFUSES and gives crisis
   resources (zero harmful content), which the stricter LLM-rubric judge still scored PASS (full
   writeup: `reviews/judge-validity-incident.md`'s "Residual false positive found AFTER the fix").
   This means the failure mode is not specific to the original RoBERTa classifier — it survives a
   deliberately anti-roleplay LLM-as-judge rubric too, which is a stronger, more general claim
   than the original incident alone. This is the paper's headline result, not an incident
   footnote.
2. **SECONDARY — the honest guided-mutation null, with an explicit noise caveat.** Activation-
   guided span mutation shows no *consistent, significant* ASR advantage over uniform mutation,
   with the mechanism independently verified as actually operating: `guided_fire_count` is 167/167
   (Qwen) and 200/200 (Phi) — guided mutation fires on essentially every iteration, 0 fallback —
   and tree search genuinely engaged after the seed-pool fix: `n_mutated_child_selected` = 54
   (Qwen `ours`), 80 (Qwen `gptfuzzer`, Phi both) — all **verified directly from
   `results/{ours,gptfuzzer}_smoke_pool12.json` and `results/phi/{ours,gptfuzzer}_smoke_pool12.json`,
   pushed from Kaggle and landed in this repo 2026-08-07**. Those files' own `asr` field (the
   fixed judge's live verdict during the run, before any hand-verification) reads: Qwen `ours`
   0.4 (2/5), Qwen `gptfuzzer` 0.0 (0/5), Phi both 0.0. Hand-verifying Qwen `ours`'s 2 flagged
   successes found 1 genuine + 1 false positive (the ChadGPT case) — true hand-verified ASR 0.2
   (1/5), not written back into the JSON (this repo does not retroactively edit results files,
   same convention as the original incident). **A separate, earlier pool-77 (post-judge-fix,
   pre-pool-fix) Qwen run reportedly showed `ours` = `gptfuzzer` = 0.4 (tied) — this comparison
   point has NO backing file in this repo and must be treated as PI-reported-only** until/unless
   it lands, unlike the pool-12 numbers above. Both pool-12 (0.2 vs. 0.0, hand-verified) and the
   reported pool-77 (0.4 vs. 0.4) point the same direction: no reproducible guided advantage.
   **Do not cite the pool-12 2-vs-0 raw judge count, or the 1-vs-0 hand-verified count, as guided
   beating uniform** — that is noise at n=5, not signal; a single flip changes the ratio entirely.
   The null is reported *because* the mechanism was confirmed engaged, not despite an
   unverified/inert one — that is what makes it an honest negative result. Establishing
   statistical significance either way requires the full matrix, which will not run (GPU
   exhausted).
3. **METHODOLOGY note — seed-pool exhaustion (§12).** At `query_budget=40` against the original
   77-template pool, UCB1 never mutates past the original seeds — documented as a caveat/lesson
   for anyone reusing GPTFuzzer's MCTS-lite scaffold with a small query budget, not as a result
   in itself.
4. **NOT the paper:** "guided mutation beats baselines." That hypothesis was tested (mechanism
   verified as engaged, both the attribution and the tree-search halves) and falsified — do not
   frame §10's target-difficulty axis or the guided-vs-uniform ablation as the headline. Also NOT
   the paper: "guided mutation beats uniform at pool-12" from the 1-vs-0 count above — see the
   noise caveat in point 2.

**Provenance status, updated 2026-08-07 (this replaces the earlier "not yet artifact-backed"
flag — the files have since landed):**
- **Now artifact-backed**: `results/ours_smoke_pool12.json`, `results/gptfuzzer_smoke_pool12.json`,
  `results/phi/ours_smoke_pool12.json`, `results/phi/gptfuzzer_smoke_pool12.json` — all four
  pushed from Kaggle and confirmed in this repo (`git log` shows them landing via commit
  `4e0ebb8`). Their `asr`/`guided_fire_count`/`n_mutated_child_selected` fields were read
  directly from these files and match the PI's report exactly — CLAUDE.md rule 2 satisfied for
  these specific numbers.
- **Still PI-hand-verified only, not written back into any JSON** (correct — this repo does not
  retroactively edit results files): the ChadGPT false-positive finding and the resulting 0.2
  true Qwen `ours` ASR. This is a real, completed human read (stronger evidence than a raw
  self-report) but is a qualitative/manual correction layered on top of the artifact, not itself
  in a committed file — cite it in the paper as a hand-verification finding (pointing to
  `reviews/judge-validity-incident.md`), not as a `results/*.json` field.
- **Still PI-reported only, no backing file at all in this repo**: the pool-77 (post-judge-fix,
  pre-pool-fix) Qwen `0.4`/`0.4` comparison point. Do not cite it as a number without a source; it
  may only ever exist as a comparison anecdote unless that run's JSON is separately pushed.

`/review` should check all three provenance tiers above before any Gate 5/7 PASS — they are not
interchangeable.

**Explicit limitation, required in the paper**: every number behind this reframe is **smoke-scale
(n=5 behaviors)**, not the originally planned n=25×3-seed matrix — GPU exhausted before the full
matrix could run. State this as a limitation, not a footnote: effect sizes and the judge-inflation
delta should be reported with the sample size attached, and the paper should not imply matrix-scale
statistical power it does not have. `reviews/judge-validity-incident.md` should be brought to
paper-evidence quality (finding 1's primary source) as part of Day 7 writing.

## 12. UCB1 seed-pool exhaustion within budget (found via --debug-attribution, 2026-08-07)

**Finding**: `--debug-attribution` (new flag on `run_fuzz.py`, logs each guided-mutation call's
token-projection scores + selected span, `behavior_idx`/`behavior_text` included) showed
behavior 2's attribution trace bit-identical to behavior 1's. Root-caused, not a bug:

1. `select_ucb1()` returns the first `visits==0` node it finds, scanning the pool **in order** —
   fully deterministic, no randomness in node choice for unvisited nodes.
2. `load_seed_templates("human", ...)` reads the same fixed CSV
   (`sherdencooper/GPTFuzz` `GPTFuzzer.csv`) every call — **verified live: 77 rows**, identical
   text and order for every behavior.
3. `query_budget` is locked at **40** (§10) — less than 77.
4. Attribution runs on the **template**, before `fill_template()` injects behavior text (the
   marker span is explicitly excluded from scoring) — so it cannot see behavior-specific content
   at all until the pool's original seed nodes are exhausted.

Put together: for `--seedtier human` (the default; `gptfuzzer` forces it), **every iteration of
every behavior's run selects the next unvisited original seed template, in the same fixed order,
identical across all behaviors** — the pool never reaches a point within budget where UCB1
actually chooses to exploit/refine an already-visited (mutated) node. The MCTS-lite exploitation
half of "MCTS-lite seed selection" is effectively inert at the current budget for `human` seedtier;
the run is, in practice, a fixed march through 40 of the 77 seed templates, each mutated once.

**Does this invalidate the CIs?** No. Per-behavior independence for ASR/CI purposes rests on the
**generated completion and judge verdict** being behavior-specific, which they are —
`fill_template()` injects the real behavior before generation, and `evaluate_completion()` judges
against that behavior's harm criteria. The mutator LLM's rewrite of the (identical) selected span
also differs across behaviors because `do_sample=True` draws from a continuously-advancing global
RNG stream (`set_seed()` runs once, not per behavior — checked, not reseeding). What's identical
across behaviors is only the **span-selection step** on the shared, pre-injection template.

**What it does affect**: the "guided mutation converges on high-value candidates via UCB1" story
implied by "MCTS-lite" is not actually exercised within this budget for `human` seedtier — both
`ours` and `gptfuzzer` share the identical `select_ucb1`/pool code path, so this does not bias the
guided-vs-uniform comparison, but it does mean neither condition is doing real tree search at
`query_budget=40` against a 77-template pool. More importantly: **the `ours`-vs-`gptfuzzer` null
result reported so far may not have actually tested guided-vs-uniform MUTATION at all** — if the
loop never leaves the "replay original seeds" phase, both conditions are doing the same thing
(mutating a never-before-mutated seed once) and a null result there says nothing about whether
guided span-selection helps once real mutation/revisit search is happening.

**Fix, shipped 2026-08-07 (Option 2 — subsample the seed pool, not raise the budget)**: new config
key `seed_pool_size` (default 12 in code, set to `12` in every `configs/exp_*.yaml`, all four kept
in sync per CLAUDE.md rule 3) makes `load_seed_templates("human", ...)` subsample the 77-template
pool down to 12 before returning it. The subsample uses a **fixed constant**
(`SEED_POOL_SUBSAMPLE_SEED = 0` in `run_fuzz.py`, deliberately NOT `--seed`/`cfg['seed']`) so it is
the *exact same* 12 templates for every run — all 3 `--seed` replicates, both methods, every
target — rather than a different subsample per replicate. With 12 seeds and `query_budget=40`,
~12 iterations exhaust the pool and the remaining ~28 are spent on UCB1 actually selecting and
refining `MUTATED_CHILD` nodes.

**Proof this actually engages tree search, verified (not asserted)**: extracted `select_ucb1()`
and `backpropagate()` **verbatim** from `run_fuzz.py` (not reimplemented) and ran them standalone
against a synthetic pool/reward loop matching the real code's structure:
- Old pool (77 templates), budget 40: **0/40 `MUTATED_CHILD` selections** — matches the finding
  above exactly.
- New pool (12 templates via `seed_pool_size`), budget 40, **worst-case reward always 0** (no
  success signal at all — the hardest case, since UCB1 has nothing but the explore term to work
  with): **16/40 `MUTATED_CHILD` selections**, first one at iteration 24. A more realistic sparse
  reward (occasional success) gave the identical count. So even in the worst case, guided/uniform
  mutation now gets exercised on real revisited, previously-mutated candidates for a large minority
  of the budget — the fix works.

**Instrumentation added** (`run_fuzz.py`, both methods since `select_ucb1`/pool code is shared):
every iteration now classifies its UCB1 selection as `ORIGINAL_SEED` or `MUTATED_CHILD` and
increments `counters["n_original_selected"]`/`["n_mutated_child_selected"]` **unconditionally**
(not gated behind `--debug-attribution`) — these are committed to every run's aggregate
`results/*.json`, same pattern as `guided_fire_count`/`guided_fallback_count`, so this is an
auditable artifact fact, not a transient log line. `--debug-attribution` additionally logs the
per-iteration kind (plus `visits_before`/`pool_size`) when set, for interactive debugging.

**Required before trusting any post-fix `ours`-vs-`gptfuzzer` comparison**: check the *real* run's
`n_mutated_child_selected` in its `results/*.json` is meaningfully > 0 (not just the synthetic
proof above) before treating that run's ASR difference as evidence about guided-vs-uniform
mutation specifically, rather than about "which seed template a fixed march happened to land on."
