#!/usr/bin/env python3
"""Re-validate an EXISTING run's raw completions against the fixed judge (scripts/judge.py),
WITHOUT re-generating anything -- cheap, since generation (not judging) was always the expensive
part. This is how to answer "how many of this run's 'successes' were judge false positives?"
for data collected before the 2026-08-06 judge fix, using the raw records that already exist
(gitignored `results/prompts_<stem>_full.jsonl`, written by scripts/run_fuzz.py).

HONEST LIMITATION, not glossed over: this can only re-score candidates that were actually
generated and recorded. If the ORIGINAL run stopped early on a false-positive success (exactly
the failure mode that motivated this fix), we have no record of what would have happened with
more iterations under the corrected judge -- the search would have kept going. Treat this tool's
`rescored_asr` as a same-data re-validation / likely-still-a-lower-bound, NOT a substitute for a
full re-run with the fixed judge. It answers "was the ORIGINAL number trustworthy," not
"what is the TRUE number" -- for that, re-run scripts/run_fuzz.py (now fixed) from scratch.

SAFETY (CLAUDE.md golden rule 1): --records is already the gitignored raw-text input; this
script's own aggregate --out is git-trackable and contains NO raw prompt/completion text, only
indices/scores/verdicts. Full text of FLIPPED examples (old vs new verdict disagree) goes to a
separate gitignored --flips-out file for human review, same split as every other raw-text
artifact in this repo.

Usage:
    python scripts/rescore_judge.py --records results/prompts_ours_smoke_full.jsonl \
        --config configs/exp.yaml --out results/rescore_ours_smoke.json
"""
import argparse
import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import torch
import yaml

import judge as judge_mod  # scripts/judge.py

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [rescore] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rescore_judge")


def git_sha():
    sha = os.environ.get("JLENS_GIT")
    if sha:
        return sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"]
        ).decode().strip()
    except Exception:  # noqa: BLE001 - provenance must never crash the run
        return "nogit"


def config_hash(config_path):
    with open(config_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def load_records(path):
    if not os.path.exists(path):
        raise SystemExit(
            f"[rescore_judge] no such records file: {path}\n"
            f"This is scripts/run_fuzz.py's gitignored raw-record side file (see its "
            f"full_records_file output field) -- it must exist locally (pulled from wherever "
            f"the original run actually happened, e.g. Kaggle) before it can be re-scored."
        )
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    ap = argparse.ArgumentParser(
        description="Re-validate an existing run's raw completions against the fixed judge "
                    "(scripts/judge.py), without re-generating. See this file's module "
                    "docstring for an important limitation on what 'rescored_asr' does and "
                    "doesn't mean."
    )
    ap.add_argument("--records", required=True,
                     help="path to a results/prompts_<stem>_full.jsonl written by run_fuzz.py")
    ap.add_argument("--config", default="configs/exp.yaml")
    ap.add_argument("--out", default=None,
                     help="default: results/rescore_<stem>.json, derived from --records")
    ap.add_argument("--flips-out", default=None,
                     help="default: results/prompts_rescore_<stem>_flips.jsonl (gitignored via "
                          "results/**/prompts_*) -- full text of examples where old/new verdict "
                          "disagree, for human review")
    args = ap.parse_args()

    stem = os.path.splitext(os.path.basename(args.records))[0]
    # records files are named prompts_<real-stem>_full.jsonl -- strip that wrapper for naming.
    if stem.startswith("prompts_") and stem.endswith("_full"):
        stem = stem[len("prompts_"):-len("_full")]
    out_path = args.out or f"results/rescore_{stem}.json"
    flips_out = args.flips_out or f"results/prompts_rescore_{stem}_flips.jsonl"

    cfg = yaml.safe_load(open(args.config))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info(f"device={device}")
    if device == "cpu":
        log.warning(
            "no CUDA available -- fine for --help/import validation, a full re-score run on "
            "CPU will be slow. Real runs happen on Kaggle GPU."
        )

    records = load_records(args.records)
    log.info(f"loaded {len(records)} raw records from {args.records}")
    if not records:
        raise SystemExit(f"[rescore_judge] {args.records} is empty -- nothing to re-score.")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(flips_out) or ".", exist_ok=True)

    judge_llm_tok, judge_llm_model, judge_device = judge_mod.load_judge_llm(
        cfg["judge_llm_model"], device
    )

    per_behavior_old = {}
    per_behavior_new = {}
    flips = []
    old_success_count = 0
    new_success_count = 0
    n_judged = 0

    for i, r in enumerate(records):
        bidx = r.get("behavior_index")
        old_success = bool(r.get("success"))
        # "candidate" is the full filled prompt actually sent to the target -- used as the
        # "harmful request" input to the rubric judge (see module docstring: we don't have the
        # bare original behavior string in these records, only the templated candidate, which
        # is in fact what the target model was actually asked, so grading against it is at
        # least as precise as grading against the abstract behavior alone).
        candidate = r.get("candidate")
        completion = r.get("completion")

        if completion is None:
            # partial-only (judge+act non-elite) candidates were never generated/judged at all
            # -- nothing to re-score for those, skip.
            continue

        n_judged += 1
        verdict = judge_mod.judge_success(
            candidate, completion, judge_llm_tok, judge_llm_model, judge_device
        )
        new_success = verdict["success"]

        old_success_count += int(old_success)
        new_success_count += int(new_success)
        per_behavior_old.setdefault(bidx, False)
        per_behavior_new.setdefault(bidx, False)
        per_behavior_old[bidx] = per_behavior_old[bidx] or old_success
        per_behavior_new[bidx] = per_behavior_new[bidx] or new_success

        if old_success != new_success:
            flips.append({
                "record_index": i,
                "behavior_index": bidx,
                "old_success": old_success,
                "new_success": new_success,
                "old_roberta_judge_score": r.get("roberta_judge_score"),
                "new_llm_reason": verdict["llm_reason"],
                "candidate": candidate,
                "completion": completion,
            })

        log.info(
            f"[{i+1}/{len(records)}] behavior_index={bidx} old_success={old_success} "
            f"new_success={new_success} {'FLIP' if old_success != new_success else ''}"
        )

    behaviors_seen = sorted(per_behavior_old.keys(), key=lambda x: (x is None, x))
    old_asr = float(np.mean([per_behavior_old[b] for b in behaviors_seen])) if behaviors_seen else None
    new_asr = float(np.mean([per_behavior_new[b] for b in behaviors_seen])) if behaviors_seen else None

    log.info(
        f"old_asr(as originally recorded)={old_asr}  "
        f"rescored_asr(same data, fixed judge)={new_asr}  "
        f"candidate-level flips={len(flips)}/{n_judged}"
    )
    if flips:
        log.warning(
            f"[FINDING] {len(flips)} candidate(s) flipped verdict under the fixed judge -- see "
            f"{flips_out} (gitignored) for full text. Remember the module docstring's "
            f"limitation: this can only re-score candidates that were actually generated; a "
            f"behavior that stopped early on a false-positive success has no record of what "
            f"more iterations would have found under the corrected judge."
        )

    # Full text of flipped examples -> gitignored side file only.
    with open(flips_out, "w") as f:
        for fl in flips:
            f.write(json.dumps(fl) + "\n")
    log.info(f"wrote {len(flips)} flip examples (full text) to {flips_out} (gitignored)")

    summary = {
        "records_file": args.records,
        "judge_llm_model": cfg["judge_llm_model"],
        "n_records_judged": n_judged,
        "n_behaviors_seen": len(behaviors_seen),
        "old_asr_as_recorded": old_asr,
        "rescored_asr_same_data": new_asr,
        "candidate_level_flip_count": len(flips),
        "candidate_level_old_success_count": old_success_count,
        "candidate_level_new_success_count": new_success_count,
        "flips_file": flips_out,
        "LIMITATION": (
            "rescored_asr_same_data re-scores only candidates that were actually generated in "
            "the original run. If a behavior's original run stopped early on a false-positive "
            "success, no record exists of what more iterations would have found under the "
            "corrected judge -- this number is a same-data re-validation, not equivalent to a "
            "full re-run. For an authoritative number, re-run scripts/run_fuzz.py (already "
            "fixed) from scratch."
        ),
        "_provenance": {
            "git_sha": git_sha(),
            "job": os.environ.get("JLENS_JOB", "rescore"),
            "config_hash": config_hash(args.config),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"wrote aggregate-only summary (no raw text) to {out_path}")


if __name__ == "__main__":
    main()
