# jlens-fuzz — Makefile. Orchestration-aware, Kaggle-only (no paid services).
# Day-to-day you drive the pipeline with the CONTROLLER, not these targets:
#     python scripts/run_controller.py --lane core
# It prints the exact Kaggle launch lines for the next batch. See ORCHESTRATION.md.

CONFIG ?= configs/exp.yaml
PY     ?= python

.PHONY: help status next job setup probes figures paper test clean

help:
	@echo "Primary workflow:"
	@echo "  make status              # what's done / ready / blocked (core lane)"
	@echo "  make status LANE=all     # include extended-lane jobs"
	@echo "  make job JOB=ours        # run ONE manifest job locally (needs a GPU)"
	@echo ""
	@echo "Direct targets: setup probes figures paper test clean"
	@echo "Manifest of all jobs: experiments.yaml"

LANE ?= core
status next:
	$(PY) scripts/run_controller.py --lane $(LANE)

# Run a single job id from experiments.yaml (dispatcher resolves the command + deps)
job:
	@test -n "$(JOB)" || (echo "usage: make job JOB=<id>  (see experiments.yaml)"; exit 1)
	$(PY) scripts/run_experiment.py --job $(JOB)

setup:
	$(PY) -m pip install -r requirements.txt

# Convenience aliases for the two jobs whose scripts already exist / are reporting steps
probes:
	$(PY) scripts/train_probes.py --config $(CONFIG) --out results/probes

figures:
	$(PY) scripts/run_experiment.py --job figures

paper:
	$(PY) scripts/run_experiment.py --job paper

test:
	$(PY) -m pytest -q

clean:
	rm -rf results/figures paper/build logs __pycache__ scripts/__pycache__
