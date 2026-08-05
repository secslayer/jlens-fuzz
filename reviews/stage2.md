# Stage 2 Review — Refusal probes (Gate 2, PLAN.md §6) — RE-REVIEW

- **Branch / HEAD reviewed:** `stage-2-probes-direction` @ `30a7e09` ("stage2: regenerate probe
  results with provenance block").
- **Reviewer:** adversarial peer-review subagent (fresh review, prior uncommitted
  `reviews/stage2.md` and prior review prose discarded/not trusted; this file overwrites it).
- **Scope of this cycle:** re-verify the three Gate 2 checklist items against the *regenerated*
  probe artifacts, and specifically confirm the provenance fix (`b64f59c` → `30a7e09`) actually
  landed in the data files, not just in the script.

## Overall verdict: **PASS** (artifact well-formedness/consistency only — see caveat below)

This PASS certifies that the regenerated artifacts are internally consistent, correctly
provenanced, numerically unchanged from what the human sign-off reviewed, and that the
fitness-demotion mitigation from the last cycle is still intact in `experiments.yaml`. It is
**not** a substitute for the human's own novel-prompt judgment call. That judgment is already
recorded in `reviews/stage2-human-signoff.md` (commit `0e7d6b9`) as a **signal-specific partial
pass**: direction PASS, probe FAIL on generalization. This review confirms that finding is still
valid against the current artifacts (the layer/AUC numbers it cites did not drift) — it does not
re-run or override it.

## Checklist (PLAN.md §6, Gate 2)

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Best-layer held-out AUC ≥ 0.85 | **PASS** | `results/probes/best_layer.json`: `"best_layer": 9, "best_auc": 1.0, "auc_threshold": 0.85, "passes_gate": true`. `results/direction.npz` (`np.load(..., allow_pickle=True)["best_auc"]` → `1.0`, `["best_layer"]` → `25`). Both ≥ 0.85; neither is the CLAUDE.md hard-stop condition (`AUC < 0.85`). |
| 2 | Chosen layer in sensible mid/late band, not layer 0 | **PASS (direction), MARGINAL (probe)** — unchanged from prior cycle | Direction: layer 25/36 (~69% depth) — solidly mid/late. Probe: layer 9/36 (~25% depth) — not layer 0/1 (doesn't trip the literal CLAUDE.md `best layer == 1` FAIL condition), but early, and per the human sign-off this is plausibly *why* the probe overfit a surface confound rather than a semantic one. Not a new finding this cycle — the regenerated file reproduces the identical layer choice (see item 5). |
| 3 | Probe/direction separates 6 novel hand-written harmful/benign prompts (👤) | **FAIL (probe) / PASS (direction)**, per `reviews/stage2-human-signoff.md` — reconfirmed still current, not stale | See "Staleness check" below: the regenerated `best_layer.json`/`probe_best_layer.npz` are byte-identical (modulo the added `_provenance` block) to the `a2323e3` versions the human actually reviewed. The sign-off's cited numbers (probe layer 9, AUC 1.0, 0.5 novel-prompt accuracy; direction layer 25, AUC 1.0, +30/−5 avg projection separation) are unchanged and not stale. |

## Provenance fix verification (this cycle's main task)

| Check | Result | Evidence |
|---|---|---|
| `best_layer.json` has `_provenance` dict with `git_sha`/`job`/`config_hash`/`timestamp` | **PASS** | Read directly: `{"git_sha": "b64f59c", "job": "probes", "config_hash": "605032769f74b171", "timestamp": "2026-08-05T12:32:19.248072+00:00"}`. |
| `probe_best_layer.npz` has `provenance` key with same JSON fields, recoverable via `json.loads(str(np.load(path)["provenance"]))` | **PASS** | Ran exactly that call: `{'git_sha': 'b64f59c', 'job': 'probes', 'config_hash': '605032769f74b171', 'timestamp': '2026-08-05T12:32:19.248072+00:00'}` — identical to the JSON sidecar, as expected from `train_probes.py`'s shared `provenance` dict. |
| `config_hash` matches a fresh sha256 of current `configs/exp.yaml` | **PASS** | `hashlib.sha256(open("configs/exp.yaml","rb").read()).hexdigest()[:16]` computed locally → `605032769f74b171`, matches both provenance blocks exactly. `git diff HEAD -- configs/exp.yaml` is empty, so this is the config as committed at HEAD, not a working-tree drift. |
| `git_sha` in provenance is a real commit, and its identity is sensible | **PASS** | `git cat-file -t b64f59c` → `commit`. `git log -1 --format="%H %ci %s" b64f59c` → `b64f59cf... 2026-08-05 17:58:01 +0530 Add _provenance block to train_probes.py's outputs`. This is exactly the commit the task predicted (the one that added the provenance code) — confirmed by timestamp ordering: the run's `timestamp` (12:32:19 UTC) is *after* `b64f59c`'s commit time (12:28:01 UTC), and the results-commit `30a7e09` (12:33:13 UTC) follows shortly after the run finished. `git merge-base --is-ancestor b64f59c 30a7e09` → true. |
| Regeneration didn't silently change the picked layer/numbers | **PASS (no drift)** | `git show a2323e3:results/probes/best_layer.json` (the version the human sign-off actually reviewed) vs. current, diffed with the `_provenance` key stripped from the new one: **identical** (`old == new` → `True` in Python). Same for `probe_best_layer.npz`: `coef`/`intercept`/`layer` all `np.allclose`/`==` True between the `a2323e3` blob and the current one. This is expected — `train_probes.py` seeds `random.seed`/`np.random.seed`/`torch.manual_seed` from `configs/exp.yaml`'s `seed` (line 128) and uses `random_state=cfg["seed"]` in the train/test split (line 149) and is otherwise deterministic (frozen model forward pass, no stochastic training beyond that), so a re-run with unchanged config reproduces bit-identical numbers. The `git show 30a7e09 -- results/probes/best_layer.json` diff confirms only the trailing `_provenance` block was added (8 insertions, 1 deletion for the missing-newline-at-EOF fix), nothing upstream of it changed. |
| `direction.npz` provenance / untouched-ness | **Confirmed unchanged, correctly out of scope this cycle** | `git log --oneline -- results/direction.npz` → only `a2323e3`, never touched by `30a7e09`. Its provenance (`git_sha: 23e15ce, job: direction, config_hash: 605032769f74b171`) matches the same config hash, so the probe re-run and the (untouched) direction artifact are still on the same config invariants. |

**Conclusion on staleness risk (the thing this cycle was specifically asked to rule out):** the
regenerated files carry *new provenance metadata* but *bit-identical scientific content* to what
the human already reviewed under `a2323e3`/`reviews/stage2-human-signoff.md`. The sign-off's
specific numbers (layer 9, AUC 1.0 for probe; layer 25, AUC 1.0 for direction; 0.5 novel-prompt
accuracy for probe) are **not stale** — they describe the exact artifact at current HEAD.

## Fitness demotion still intact (experiments.yaml)

```
grep -n "judge+act\|--fitness" experiments.yaml
```
- Core-lane jobs (all four use `--fitness judge`, no `judge+act`):
  - `ours` (line 61), `abl_mut_uniform` (line 67), `abl_seed_bootstrap` (line 73),
    `abl_seed_random` (line 79).
- Extended-lane diagnostic (the only `judge+act` occurrence, correctly isolated and commented
  "NOT VALIDATED"):
  - `abl_fitness_probeact` (line 88), with the explanatory NOTE block at lines 50–56 pointing at
    `reviews/stage2-human-signoff.md`.

**PASS** — the mitigation recorded in the last review cycle is still present and unmodified at
current HEAD; `judge+act` appears exactly once, in the extended-lane job, as required.

## Cross-cutting red flags

| Flag | Result | Evidence |
|---|---|---|
| Secrets/API keys in git-tracked files | **None found** | `git ls-files \| xargs grep -lIE "sk-[A-Za-z0-9]{20,}\|AKIA[0-9A-Z]{16}\|api[_-]?key"` → only hits `reviews/stage0.md`, which is prior review *prose describing a search pattern*, not a real key (confirmed by reading the line — it's the grep command itself quoted in the report). `git log --all -p -- results/ \| grep -iE "sk-...\|OPENROUTER_API_KEY=\|AKIA..."` → empty. |
| Generated attack strings in git-tracked files | **None found** | `.gitignore` line 10: `results/**/prompts_*`. `git ls-files \| grep prompts_` → empty (no such file ever tracked). `git ls-files results/` → only `.gitkeep`, `direction.npz`, `probes/best_layer.json`, `probes/probe_best_layer.npz`, `sanity.json` — all aggregate metrics/weights, no raw prompt text. `scripts/probe_novel_check.py` (lines 1–29) is explicitly designed to never write prompt text to disk or logs, only index/label/score. |
| Numbers with no `results/*.json`/`.npz` backing | **None found** | Every number cited above traces to `results/probes/best_layer.json` or `results/direction.npz`, both read directly in this review, not taken from prose. |
| Baseline vs. ours run under different config invariants | **N/A this stage / consistent** | Both probe and direction runs share `config_hash: 605032769f74b171` (current `configs/exp.yaml`); no baseline-vs-ours comparison happens at Stage 2. |
| Probe AUC < 0.85, or best layer == 1 | **Neither triggered** | Probe AUC 1.0, layer 9; direction AUC 1.0, layer 25. Note per CLAUDE.md this is a hard numeric gate and it is *not* tripped — the probe's real weakness (generalization failure on novel prompts) is a separate, qualitative finding that the numeric AUC gate structurally cannot catch, which is exactly why the 👤 novel-prompt item exists and exactly why it correctly overrode the numeric PASS for probe-based fitness. |
| Metrics missing for any method/behavior cell | **N/A this stage** | Stage 2 produces per-layer AUC/acc for both direction and probe signals; both are fully populated (36 layers each in `best_layer.json`'s `per_layer` array and `direction.npz`'s `per_layer_auc`). |

## Required fixes

None. This is a re-review confirming the single non-blocking gap from the prior cycle
(missing `_provenance` on the two probe artifacts) is now closed, with no regressions
introduced by the regeneration.

## Explicit note on the 👤 gate

This is a **👤-mandatory gate**. An agent verdict (this document) is **necessary but not
sufficient**. The substantive human judgment — that the probe fails to generalize to novel
harmful/benign phrasing despite a perfect held-out AUC — is already recorded by the human in
`reviews/stage2-human-signoff.md` and is correctly never re-litigated by an agent (the raw novel
prompts are, correctly, never committed per `.gitignore`'s `results/**/prompts_*` and CLAUDE.md
golden rule 1, so an agent has no way to independently re-run that judgment even if it wanted
to). This review's PASS is scoped strictly to: (a) the numeric AUC gate, (b) the provenance
fix landing for real in the data files, (c) the regenerated numbers matching what the human
actually signed off on (no silent drift), and (d) the fitness-demotion mitigation remaining
intact. A human must independently confirm they still stand by the novel-prompt finding in
`reviews/stage2-human-signoff.md` before Stage 3 proceeds with probe-fitness re-enablement (it
already correctly remains disabled in the core lane per the demotion, so no action is blocking
core-lane progress).
