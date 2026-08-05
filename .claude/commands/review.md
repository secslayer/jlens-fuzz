---
description: Run the adversarial peer-review subagent against the current stage's gate.
argument-hint: <stage-number>
---

Invoke the `reviewer` subagent to audit Stage $ARGUMENTS against its Gate checklist in
`PLAN.md` §6. The reviewer must read the actual artifacts and `results/*.json`, verify each
checklist item with file-level evidence, and write a PASS/FAIL verdict to
`reviews/stage$ARGUMENTS.md`.

Do not advance to the next stage unless the verdict is PASS. If the gate is marked 👤,
remind me that a human sign-off is still required. If FAIL, summarize the required fixes and
stop.
