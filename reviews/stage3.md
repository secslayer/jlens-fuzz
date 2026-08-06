# Stage 3 Review — Fitness swap into the fuzzing loop (`scripts/run_fuzz.py`)

**Branch:** `stage-3-run-fuzz` @ `c973943` (matches `origin/stage-3-run-fuzz`, working tree clean)
**Reviewer:** agent (adversarial peer review), 2026-08-06

## Overall verdict: **FAIL**

The code (`scripts/run_fuzz.py`) is real, complete, and its two claimed bugfix commits check out
against the diff. But the gate's central empirical claim — "loop produces ≥1 judge-confirmed
jailbreak on the 5-behavior smoke set" — has **zero backing artifact in the repo**. No
`results/ours_smoke.json` (or any `results/ours*.json`) exists anywhere: not tracked, not
untracked, not on origin, not in any commit in `git log --all`. `reviews/stage3-human-signoff.md`
asserts ASR=1.0, 3 hand-verified genuine jailbreaks, and "100% guided mutation, 0 fallbacks" —
but these are narrative claims about a Kaggle session with no committed output JSON to check them
against. This is exactly CLAUDE.md rule 2 ("never invent numbers... a number with no provenance
does not go in the paper") and this reviewer's own standing red flag ("any number cited that has
no backing `results/*.json` → FAIL"). A well-written human sign-off narrative is not a substitute
for the actual artifact, unlike Stage 1 (`results/sanity.json`, committed) and Stage 2
(`results/probes/best_layer.json`, committed) where the human sign-off doc was paired with a real
file this reviewer could independently open and check numbers against.

## Checklist table

| Gate 3 item (PLAN.md §6, post-descope) | Verdict | Evidence |
|---|---|---|
| Loop produces ≥1 judge-confirmed jailbreak on the 5-behavior smoke set | **FAIL** | No `results/ours_smoke.json` or any `results/ours*.json` exists. `git ls-files \| grep -i ours` → empty. `find . -iname "*ours*" -not -path "./.git/*"` → empty. `git log --all --diff-filter=A --name-only \| grep -i ours` → no such file ever added in any commit, on this branch or any other. The ASR=1.0 / "3 spot-checked genuine jailbreaks" claims in `reviews/stage3-human-signoff.md` (lines 17, 29, 41) have no `results/*.json` to back them — fabrication red flag per this reviewer's own instructions and CLAUDE.md rule 2. |
| ~~Partial-forward fitness cheaper than full-judge fitness~~ (descoped) | **N/A (correctly descoped)** | PLAN.md lines 198-202 strike this with a stated rationale (judge+act rides the Stage 2 probe signal, proven non-generalizing per `reviews/stage2-human-signoff.md`: 0.5 acc on 6 novel prompts vs. 1.0 training AUC). Rationale is sound and consistent with `experiments.yaml` demoting `abl_fitness_probeact` to `lane: extended` (lines 81-88) with an explicit "NOT VALIDATED... do not report headline numbers from this job until then" comment. Reasonable to descope, but see "process" note below — descoping a gate item after the fact requires the *other* item still be independently verified, which it is not (see row above). |
| No harmful strings written to any git-tracked path (grep) | **PASS (by code inspection)** | The tracked-output dict (`summary`, `run_fuzz.py` lines 836-864) contains only scalars/counters — no `template`/`candidate`/`completion` field. Raw per-candidate records (`records`, appended at line 640-649, containing `template`, `candidate`, `completion`) are written only to `full_records_file = results/prompts_{stem}_full.jsonl` (line 726, write loop lines 814-818), never to `out_path`. Confirmed `.gitignore` line 10 `results/**/prompts_*` actually matches this filename: `git check-ignore -v results/prompts_ours_smoke_full.jsonl` → matches (`.gitignore:10:results/**/prompts_*`), verified experimentally (`touch` + `git check-ignore`, exit 0). `git grep -niE "api[_-]?key\|secret"` and a scan for harmful-instruction phrasing in tracked non-.md files → no hits. Note this PASS is necessarily vacuous on live data: since no run's output was ever committed, there is currently no tracked artifact to have leaked anything into in the first place — the PASS is about the code's design, not about a verified real run's output. |

## Supporting/independent checks

**1. `scripts/run_fuzz.py` completeness and correctness**
- `python3 -m py_compile scripts/run_fuzz.py` → clean, no errors.
- 875 lines, 28 top-level functions (`ast.parse` walk) — not a stub; covers behavior loading,
  seed tiers (human/random/bootstrap), guided/uniform mutation, judge and judge+act fitness, UCB1
  MCTS-lite pool selection, perplexity/self-BLEU/distinct-2 diagnostics, and a full aggregate
  JSON schema with `_provenance`.
- `derive_out_path` (lines 160-172) is deterministic and matches `experiments.yaml`'s `produces:`
  paths for every core-lane job (`ours.json`, `abl_mut_uniform.json`, `abl_seed_bootstrap.json`,
  `abl_seed_random.json`) and the extended-lane `abl_fitness_probeact.json` — spot-checked all
  five branches against `experiments.yaml` lines 57-88, consistent.
- `find_attribution_span` (lines 338-429): confirmed via `git show fa06ebc` and `git show
  5c31406` that (a) the `offsets_mapping` → `offset_mapping` typo fix is real (diff shows the
  literal key string change), and (b) the try/except was genuinely widened from covering only
  the tokenizer call to covering the entire function body through the final `return span_text`
  (diff shows the whole block re-indented under one `try:`, single `except Exception as e` at
  line 427-429). This matches the sign-off's and commit messages' claims — **verified true in
  the current file, not just claimed**.
- Output-path / side-file split (Section "SAFETY" docstring, lines 22-24, and the actual code at
  lines 640-649 / 814-818 / 836-864): confirmed by reading the code, not just the docstring, that
  raw text genuinely never reaches `out_path`.

**2. `reviews/stage3-human-signoff.md`**
- Well-formed, dated (2026-08-06), attributed (`muhammed muiz`, email present), git-tracked
  (`git ls-files | grep stage3` → present).
- Contains no raw prompt/completion text — aggregate claims only ("3 spot-checked", "ASR=1.0",
  "100% guided mutation fired"). No secrets, no attack strings.
- Structurally identical in intent to Stage 1/2 sign-offs **except** for the one thing that
  matters most for verifiability: Stage 1 and Stage 2 sign-offs each point at a companion
  `results/*.json` this reviewer can open (`results/sanity.json`,
  `results/probes/best_layer.json`) as ground truth for the numbers being narrated. This document
  points at `results/prompts_ours_smoke_full.jsonl` "inspected directly on Kaggle... not present
  in this local checkout" (line 12-13) as its evidence — by construction (it's gitignored,
  correctly) that file is *never* going to land in this repo, and it was never meant to. What
  *should* have landed in this repo, and did not, is the small aggregate
  `results/ours_smoke.json` — that file is git-tracked by design (`derive_out_path` +
  `--smoke` naming, `run_fuzz.py` lines 160-172, 719-726) and its absence is the actual gap.

**3. Cross-cutting**
- Secrets/API keys: `git grep -niE "api[_-]?key|sk-[a-zA-Z0-9]{10,}|secret"` across tracked
  files (excluding `reviews/`) → no hits.
- Attack strings in tracked files: no harmful instruction text found; `RANDOM_SEED_TEMPLATES`
  and prompt-engineering instruction strings in `run_fuzz.py` (lines 61-92) are benign
  wrapper/meta-instruction text (asking a model to write a *template*), not harmful content
  themselves — consistent with the file's own comment justifying why these are safe to hardcode.
- `experiments.yaml`'s `abl_fitness_probeact` job (lines 81-88) still exists, `lane: extended`,
  `cmd: "... --fitness judge+act"` — confirmed this is the intended future home for the
  deferred efficiency check, as the sign-off and PLAN.md both claim.
- Minor secondary finding (not gating, but worth flagging): PLAN.md's stated Stage 3 **Target**
  is `make ours SMOKE=1`, but the `Makefile` has no `ours` target and no `SMOKE` variable is
  read anywhere (`grep -n "SMOKE" scripts/run_experiment.py scripts/run_controller.py` → no
  hits; only entry points are `make job JOB=<id>` and direct `python scripts/run_fuzz.py ...`
  invocation). The actual smoke run, per the sign-off doc, was launched manually via
  `python scripts/run_fuzz.py --method ours --mutation guided --seedtier human --fitness judge
  --smoke`, bypassing both the Makefile's stated target and the "go through the manifest, never
  launch jobs ad hoc" convention in CLAUDE.md's Orchestration section. This is a smoke test, so
  ad hoc invocation is defensible in spirit, but PLAN.md's literal `make ours SMOKE=1` target
  line is currently false/aspirational and should be corrected regardless of the outcome of this
  gate.

## Required fixes before Gate 3 can be considered closed

1. **Commit and push the actual run artifact**: `results/ours_smoke.json` (aggregate-only, per
   `run_fuzz.py`'s own schema) from the Kaggle smoke run the sign-off narrates. Without this file,
   the ASR=1.0 and "0 fallbacks" numbers in `reviews/stage3-human-signoff.md` are unverifiable
   assertions, not results.
2. Push `results/prompts_ours_smoke_full.jsonl` **nowhere** (correctly gitignored) — but do keep
   it available for a future reviewer/human to re-spot-check if needed; the sign-off doc should
   say where it lives (Kaggle output artifact / dataset version) if it's not attachable here.
3. Once `results/ours_smoke.json` exists, re-verify: `asr` field actually reads 1.0,
   `full_forward_passes` / iteration counts are consistent with "guided mutation fired on 100% of
   iterations, 0 fallbacks" (note: the current script does not directly log a fallback counter —
   check whether that specific claim is even derivable from the committed schema, or whether it's
   purely from the sign-off author's manual reading of the gitignored jsonl; if the latter, say so
   explicitly rather than presenting it as if backed by the aggregate JSON).
4. Fix or annotate the `make ours SMOKE=1` Target line in PLAN.md's Stage 3 section to reflect
   the actual invocation path (`make job JOB=ours` doesn't support `--smoke` either, per
   `scripts/run_experiment.py`) — either wire `SMOKE` through the Makefile/manifest or correct the
   documented command.
5. Re-run `/review` on Stage 3 only after (1) lands; do not re-close the gate on narrative alone.
