#!/usr/bin/env python3
"""Orchestration controller — the resumable brain of the pipeline.

Reads experiments.yaml, infers each job's status purely from whether its `produces` file exists
on disk (so it is RESUMABLE across dead Kaggle sessions — no external state to lose), then prints:
  1. a status board (done / ready / blocked),
  2. the next batch of runnable jobs packed onto your Kaggle budget
     (GPUS per session x COMMIT_SLOTS sessions), as copy-paste launch lines.

Usage:
  python scripts/run_controller.py --lane core            # 1-week preprint jobs
  python scripts/run_controller.py --lane all             # + extended
  python scripts/run_controller.py --lane core --gpus 2 --commit-slots 2
Needs only pyyaml; runs on any machine (no GPU).
"""
import argparse
import os
import yaml


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
    ap.add_argument("--gpus", type=int, default=2, help="GPUs per session (Kaggle T4x2 = 2)")
    ap.add_argument("--commit-slots", type=int, default=2, help="concurrent commit notebooks")
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

    # Pack: each commit notebook runs `gpus` jobs in parallel; you have `commit-slots` notebooks.
    capacity = args.gpus * args.commit_slots
    batch = ready[:capacity]
    print(f"\n=== next batch ({len(batch)} of {len(ready)} ready; capacity {capacity}) ===")
    per_nb = args.gpus
    for nb in range(0, len(batch), per_nb):
        pair = batch[nb:nb + per_nb]
        slot = nb // per_nb + 1
        env = " ".join(f"JOB_{chr(65+i)}={jid}" for i, jid in enumerate(pair))
        print(f"# --- Kaggle commit notebook {slot} (jlens-run-{chr(64+slot)}): put this after the bootstrap cell ---")
        print(f"!{env} bash scripts/run_parallel.sh")
    if len(ready) > capacity:
        print(f"\n({len(ready) - capacity} more ready — launch them next round after these finish.)")
    print("\nafter each session: push results/ back to GitHub, then re-run me to get the next batch.")


if __name__ == "__main__":
    main()
