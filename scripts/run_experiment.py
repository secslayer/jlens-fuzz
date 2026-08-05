#!/usr/bin/env python3
"""run_experiment.py — dispatch a single job id from experiments.yaml.

Keeps orchestration decoupled from the underlying scripts: the manifest says what each job runs;
this just resolves deps, stamps provenance, and executes the command. run_parallel.sh calls this
with one job id per GPU.

Usage:  python scripts/run_experiment.py --job ours
"""
import argparse
import subprocess
import sys
import yaml


def git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:
        return "nogit"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="experiments.yaml")
    ap.add_argument("--job", required=True)
    args = ap.parse_args()

    m = yaml.safe_load(open(args.manifest))
    defaults, jobs = m.get("defaults", {}), m["jobs"]
    if args.job not in jobs:
        sys.exit(f"[dispatch] unknown job '{args.job}'. known: {', '.join(jobs)}")
    job = jobs[args.job]

    # Guard: deps must have produced their outputs (defends against launching out of order).
    import os
    for dep in job.get("needs", []):
        p = jobs[dep]["produces"]
        if not os.path.exists(p):
            sys.exit(f"[dispatch] job '{args.job}' needs '{dep}' but {p} is missing. run it first.")

    cmd = job["cmd"].format(**defaults)
    print(f"[dispatch] {args.job} @ {git_sha()}  ->  {cmd}")
    # Underlying scripts are responsible for writing the `_provenance` block into their JSON
    # (git sha, config hash, job id, timestamp) — see CLAUDE.md.
    env = dict(os.environ, JLENS_JOB=args.job, JLENS_GIT=git_sha())
    rc = subprocess.run(cmd, shell=True, env=env).returncode
    sys.exit(rc)


if __name__ == "__main__":
    main()
