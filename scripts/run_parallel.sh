#!/usr/bin/env bash
# Run two manifest jobs in parallel, one per GPU, on a Kaggle T4x2 session (or any 2-GPU box).
# Job ids come from experiments.yaml. The controller (run_controller.py) prints the exact
# JOB_A/JOB_B values for the next batch. tmux gives no persistence on Kaggle — commits do —
# so this uses background processes + logs, which work in both interactive and commit runs.
#
# Usage (from a Kaggle cell):  !JOB_A=ours JOB_B=gptfuzzer bash scripts/run_parallel.sh
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs results

JOB_A=${JOB_A:?set JOB_A to a job id from experiments.yaml}
JOB_B=${JOB_B:-}

echo "[parallel] GPU0 <- $JOB_A${JOB_B:+    GPU1 <- $JOB_B}"
CUDA_VISIBLE_DEVICES=0 nohup python scripts/run_experiment.py --job "$JOB_A" > "logs/$JOB_A.log" 2>&1 &
PID_A=$!
if [ -n "$JOB_B" ]; then
  CUDA_VISIBLE_DEVICES=1 nohup python scripts/run_experiment.py --job "$JOB_B" > "logs/$JOB_B.log" 2>&1 &
  PID_B=$!
fi

echo "[parallel] tail -f logs/*.log to watch"
wait $PID_A; RA=$?; echo "[parallel] $JOB_A exit=$RA"
if [ -n "$JOB_B" ]; then wait $PID_B; RB=$?; echo "[parallel] $JOB_B exit=$RB"; fi
echo "[parallel] DONE — push results/ to GitHub, then re-run run_controller.py for the next batch"
