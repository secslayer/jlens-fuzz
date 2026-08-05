---
description: Show pipeline status and the next batch of jobs to launch on Kaggle.
argument-hint: [core|all]
---

Run `python scripts/run_controller.py --lane ${ARGUMENTS:-core}` and show me the output verbatim.
Then, in one line each: name any job whose dependency just completed, and flag any job that has
been "ready" for more than one round (it may be stuck — check its log under logs/). Do not launch
anything yourself; I run the emitted Kaggle cells.
