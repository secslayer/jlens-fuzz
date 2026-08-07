#!/usr/bin/env python3
"""Orchestration controller — the resumable brain of the pipeline.

Reads experiments.yaml, infers each job's status purely from whether its `produces` file exists
on disk (so it is RESUMABLE across dead Kaggle sessions — no external state to lose), then prints:
  1. a status board (done / ready / blocked),
  2. the next batch of runnable jobs packed onto your Kaggle budget, as copy-paste launch lines.

Packing depends on whether a job calls the judge LLM (scripts/judge.py, added 2026-08-07: the
judge now lives on its own GPU, cuda:1, separate from the target on cuda:0 -- an earlier 8-bit
quantization attempt to share one GPU was abandoned as unreliable on Kaggle). Only `probes*`/
`direction*` jobs (plain feature extraction, no generation/judging at all) can still share one
notebook two-at-a-time via scripts/run_parallel.sh's `JOB_A=/JOB_B=` mode, one GPU each. Every
other ready job ("judged") needs BOTH GPUs and runs alone per notebook via `JOB=`. See PLAN.md
§11 for the full writeup of why.

Usage:
  python scripts/run_controller.py --lane core            # 1-week preprint jobs
  python scripts/run_controller.py --lane all             # + extended
  python scripts/run_controller.py --lane core --commit-slots 2
Needs only pyyaml; runs on any machine (no GPU).
"""
import argparse
import os
import yaml

UNJUDGED_PREFIXES = ("probes", "direction")


def is_unjudged(job_id):
    """True for jobs that never call the judge LLM (scripts/train_probes.py,
    scripts/extract_direction.py -- feature extraction only) and so can still share a single
    GPU / a notebook two-at-a-time. Everything else calls scripts/judge.py and needs both GPUs."""
    return job_id.startswith(UNJUDGED_PREFIXES)


def load(manifest):
    m = yaml.safe_load(open(manifest))
    return m.get("defaults", {}), m["jobs"]


def status_of(job, done_set):
    if job["_id"] in done_set:
        return "done"
    if all(n in done_set for n in job.get("needs", [])):
        return "ready"
    return "blocked"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="experiments.yaml")
    ap.add_argument("--lane", choices=["core", "extended", "all"], default="core")
    ap.add_argument("--commit-slots", type=int, default=2, help="concurrent commit notebooks "
                     "(each has its own 2 T4s; a judged job uses both of ITS notebook's GPUs, "
                     "so 2 different judged jobs can still run concurrently in 2 notebooks)")
    args = ap.parse_args()

    defaults, jobs = load(args.manifest)
    for jid, j in jobs.items():
        j["_id"] = jid

    # Lane filter: core is always in; extended only when requested.
    def in_lane(j):
        return j["lane"] == "core" or args.lane in ("extended", "all")
    selected = {jid: j for jid, j in jobs.items() if in_lane(j)}

    # Status inferred from disk (resumable).
    done = {jid for jid, j in selected.items() if os.path.exists(j["produces"])}

    board = {"done": [], "ready": [], "blocked": []}
    for jid, j in selected.items():
        board[status_of(j, done)].append(jid)

    print(f"\n=== orchestration status (lane={args.lane}) ===")
    print(f"done    ({len(board['done'])}): {', '.join(sorted(board['done'])) or '-'}")
    print(f"ready   ({len(board['ready'])}): {', '.join(sorted(board['ready'])) or '-'}")
    for jid in sorted(board["blocked"]):
        missing = [n for n in selected[jid].get("needs", []) if n not in done]
        print(f"blocked : {jid:22s} waiting on {missing}")

    ready = sorted(board["ready"])
    if not ready:
        remaining = board["blocked"]
        print("\nnothing ready to launch right now." +
              (" all selected jobs are done. run figures/paper if not." if not remaining
               else " finish in-flight jobs, then re-run me."))
        return

    # Pack: unjudged jobs (probes*/direction*) pair up 2-per-notebook, 1 GPU each -- same as
    # before. Judged jobs (everything else, calls scripts/judge.py) get 1 per notebook, both
    # GPUs. See this file's module docstring / PLAN.md §11 for why.
    unjudged = [j for j in ready if is_unjudged(j)]
    judged = [j for j in ready if not is_unjudged(j)]
    print(f"\n=== next batch (commit-slots={args.commit_slots}) ===")
    print(f"ready: {len(unjudged)} unjudged (pairs 2/notebook), {len(judged)} judged (1/notebook, both GPUs)")

    launched = []
    slot = 0
    ui = 0
    while ui + 1 < len(unjudged) and slot < args.commit_slots:
        slot += 1
        a, b = unjudged[ui], unjudged[ui + 1]
        print(f"# --- Kaggle commit notebook {slot} (jlens-run-{chr(64 + slot)}): unjudged pair, 1 GPU each ---")
        print(f"!JOB_A={a} JOB_B={b} bash scripts/run_parallel.sh")
        launched += [a, b]
        ui += 2
    if ui < len(unjudged) and slot < args.commit_slots:
        # odd one out -- runs alone via JOB_A=, GPU1 idle for this notebook (unjudged jobs
        # never need the 2nd GPU anyway).
        slot += 1
        a = unjudged[ui]
        print(f"# --- Kaggle commit notebook {slot} (jlens-run-{chr(64 + slot)}): unjudged, alone (2nd GPU idle) ---")
        print(f"!JOB_A={a} bash scripts/run_parallel.sh")
        launched.append(a)
        ui += 1

    ji = 0
    while ji < len(judged) and slot < args.commit_slots:
        slot += 1
        j = judged[ji]
        print(f"# --- Kaggle commit notebook {slot} (jlens-run-{chr(64 + slot)}): judged, both GPUs (target cuda:0, judge cuda:1) ---")
        print(f"!JOB={j} bash scripts/run_parallel.sh")
        launched.append(j)
        ji += 1

    remaining = len(ready) - len(launched)
    if remaining > 0:
        print(f"\n({remaining} more ready — launch them next round after these finish.)")
    print("\nafter each session: push results/ back to GitHub, then re-run me to get the next batch.")


if __name__ == "__main__":
    main()
