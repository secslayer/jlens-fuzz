# jlens-fuzz — Makefile. Orchestration-aware, Kaggle-only (no paid services).
# Day-to-day you drive the pipeline with the CONTROLLER, not these targets:
#     python scripts/run_controller.py --lane core
# It prints the exact Kaggle launch lines for the next batch. See ORCHESTRATION.md.

CONFIG ?= configs/exp.yaml
PY     ?= python

.PHONY: help status next job setup probes figures paper test clean release

help:
	@echo "Primary workflow:"
	@echo "  make status              # what's done / ready / blocked (core lane)"
	@echo "  make status LANE=all     # include extended-lane jobs"
	@echo "  make job JOB=ours        # run ONE manifest job locally (needs a GPU)"
	@echo ""
	@echo "Direct targets: setup probes figures paper test clean release"
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

# Stage 7 exit preflight (PLAN.md §6/§9, reviews/stage7-human-signoff.md). Does NOT tag --
# tagging is a human action, see the printed instructions at the end. Full narrative version
# of these same steps: RUNBOOK.md's "Release checklist" (Part 7).
release:
	@echo "=== 1/4: tests ==="
	$(PY) -m pytest -q
	@echo ""
	@echo "=== 2/4: no raw jailbreak/completion text under results/ (reviews/stage7.md) ==="
	$(PY) scripts/check_no_raw_text.py
	@echo ""
	@echo "=== 3/4: DRAFT FLAGs remaining in paper/paper.tex (the submission artifact) -- read each, confirm acceptable for v1 ==="
	@grep -n "DRAFT" paper/paper.tex || echo "(none found)"
	@echo "--- paper/paper.md (source of record; should match the above) ---"
	@grep -n "DRAFT FLAG" paper/paper.md || echo "(none found)"
	@echo ""
	@echo "=== 4/4: manual confirmations before tagging ==="
	@echo "  [ ] CI is green on the branch you're releasing: https://github.com/secslayer/jlens-fuzz/actions"
	@echo "  [ ] Gate 7 is signed off: reviews/stage7-human-signoff.md"
	@echo "  [ ] The DRAFT FLAGs printed above are the expected residual ones (unbacked incident"
	@echo "      numbers, unverified bibliography page numbers) -- NOT an unresolved disclosure flag"
	@echo "      (disclosure is now a recorded plan in paper/paper.md §7, not a bracketed TODO;"
	@echo "      if you see one here, stop and fix it before tagging)."
	@echo ""
	@echo "If all of the above check out, tag manually (this target does not do it for you):"
	@echo "  git tag -a v1.0-arxiv -m 'v1.0-arxiv: Gate 7 signed off, paper frozen for arXiv'"
	@echo "  git push origin v1.0-arxiv"
