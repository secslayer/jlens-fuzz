#!/usr/bin/env bash
# Two launch modes, depending on which GPUs the job(s) actually need. Job ids come from
# experiments.yaml; run_controller.py's printed batch already picks the right mode per job --
# use its output rather than guessing.
#
#   MODE 1 -- two UNJUDGED jobs in parallel, one GPU each. Only scripts/train_probes.py /
#   scripts/extract_direction.py (job ids probes*/direction*) qualify: plain feature
#   extraction, no generation/judging at all.
#     !JOB_A=probes JOB_B=direction bash scripts/run_parallel.sh
#
#   MODE 2 -- one JUDGED job, BOTH GPUs visible (no CUDA_VISIBLE_DEVICES restriction): target
#   model on cuda:0, judge LLM on cuda:1 (scripts/judge.py's target/judge GPU split, added
#   2026-08-07 after an earlier 8-bit/bitsandbytes quantization attempt proved unreliable on
#   Kaggle and still OOM'd). This is basically every other job (gptfuzzer/ours/abl_*/validate) --
#   anything that calls the judge. Only ONE such job runs at a time in a given notebook/session;
#   a judged job already consumes both of that session's GPUs, there is no parallel slot left in
#   the SAME notebook (a second notebook/session has its own separate 2 GPUs and can run a
#   different judged job concurrently just fine -- see PLAN.md §11).
#     !JOB=ours bash scripts/run_parallel.sh
#
# tmux gives no persistence on Kaggle -- commits do -- so this uses background processes + logs,
# which work in both interactive and commit runs.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs results

JOB=${JOB:-}
JOB_A=${JOB_A:-}
JOB_B=${JOB_B:-}

if [ -n "$JOB" ]; then
  # MODE 2: single judged job, full 2-GPU visibility.
  echo "[parallel] both GPUs <- $JOB (judged job: target cuda:0, judge cuda:1)"
  nohup python scripts/run_experiment.py --job "$JOB" > "logs/$JOB.log" 2>&1 &
  PID=$!
  echo "[parallel] tail -f logs/$JOB.log to watch"
  wait $PID; RC=$?; echo "[parallel] $JOB exit=$RC"

elif [ -n "$JOB_A" ]; then
  # MODE 1: up to two unjudged jobs, one GPU each. Do NOT use this for a judged job -- it would
  # only ever see one GPU (CUDA_VISIBLE_DEVICES-restricted), so the judge would try to share
  # that single GPU with the target and risk the exact OOM this split exists to avoid
  # (scripts/judge.py's resolve_judge_device() will warn loudly if this happens, but it's
  # better to just launch judged jobs correctly via MODE 2 in the first place).
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

else
  echo "[parallel] usage: JOB_A=<id> [JOB_B=<id>] bash scripts/run_parallel.sh   (unjudged pair, 1 GPU each)" >&2
  echo "[parallel]     or JOB=<id> bash scripts/run_parallel.sh                  (judged job, both GPUs)" >&2
  exit 1
fi

echo "[parallel] DONE — push results/ to GitHub, then re-run run_controller.py for the next batch"
