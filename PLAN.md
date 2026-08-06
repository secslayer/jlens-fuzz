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
  - [ ] 👤 You hand-validate ~50 judge labels; report judge/human agreement. **This exact check
        is what caught the judge false-positive incident early, on a 4-example smoke sample
        instead of a 50-behavior full run — see `reviews/judge-validity-incident.md` and §11
        below.** Do this hand-validation at EVERY scale (smoke included), not only here.
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
- A **second blocker** surfaced and was fixed: the first live fresh-judge smoke OOM'd (target +
  judge_llm + diagnostic judge together exceed one T4). Fixed by loading the judge in 8-bit
  (`scripts/judge.py`, `bitsandbytes`) — judge-only, the target stays fp16 always. Deliberately
  not fixed by a second GPU (would break `run_parallel.sh`'s per-job GPU pinning and halve
  throughput for every judged run). See the incident doc for why.

**Do not run the full 2-target × 3-seed matrix (§10) until**: (1) Qwen's existing completions are
re-scored with `scripts/rescore_judge.py`, (2) FRESH (not re-scored) smokes run on all four core
conditions — `ours`-Phi, `gptfuzzer`-Phi, `ours`-Qwen, `gptfuzzer`-Qwen — with the fixed judge and
fixed MCTS reward, (3) all of the above are reviewed. Re-scores are a floor, not a substitute for
fresh runs: early-stopping on an old false positive means a fresh run may explore further and
find real jailbreaks the old run never reached. This gate applies on top of, not instead of,
§10's sequencing (Qwen core lane complete and reviewed) and Gate 5's existing 👤 hand-validation
requirement (now explicitly noted to apply at every scale, not just the 50-behavior full run).

**Possible reframe, prepared for but not yet decided:** if `ours` (guided mutation) does not beat
`gptfuzzer` (uniform mutation) on these honest, fresh, post-fix numbers, this judge-reliability
finding itself becomes a candidate **core contribution** for the paper, not just an incident
footnote — a demonstrated, reproducible measurement-validity failure in a judge the field
currently treats as a standard evaluation tool is a real result on its own, independent of
whether the guided-mutation headline holds up. Do not treat the target-difficulty axis (§10) or
the guided-vs-uniform ablation as the only possible paper narrative; keep
`reviews/judge-validity-incident.md` written at paper-evidence quality (it currently is) in case
it needs to become a section rather than a footnote.
