# Repo publicity vs. disclosure timing — human decision — 2026-08-17

- **Decided by:** muhammed muiz arummal (abdulmuiz3570@gmail.com)
- **Date:** 2026-08-17
- **Action taken:** `github.com/secslayer/jlens-fuzz` was changed from private to public visibility
  today, as part of Gate 8 (Communicate — blog + slides + demo).

## What this deviates from

PLAN.md §8 (the non-negotiable, 👤 ethics gate): "Disclose to the affected open-weight
maintainer(s) **before publicizing** transfer results." The Gate 7 sign-off
(`reviews/stage7-human-signoff.md`, 2026-08-08) recorded a plan to send disclosure notices to
Microsoft/MSRC (Phi-4-mini-instruct, Phi-3.5-mini-instruct) and Alibaba/Qwen
(Qwen2.5-3B-Instruct) **at the time of arXiv posting** — treating arXiv posting, not GitHub
visibility, as the publicity trigger. Making the repo public today, ahead of both arXiv posting
and disclosure, is a real deviation from that recorded plan's literal trigger condition.

## The decision

Made deliberately and explicitly, not silently: the repo goes public today. Disclosure to MSRC and
Alibaba/Qwen has **not** been sent as of this record and is not automated by this decision — it
remains a separate, still-open action. Per PLAN.md §8's own bar, disclosure should now happen
promptly given the repo's content (aggregate scalars, redacted attribution logs, the paper
describing the judge-reliability and null-result findings) is publicly visible as of this date.

## What is and isn't covered by this decision

- Covered: GitHub repo visibility (public).
- **Not covered, still requires separate action:** actually sending the MSRC and Alibaba/Qwen
  disclosure notices; no LICENSE file exists yet (README.md's License section: "Do not treat this
  repo as licensed for reuse until one is added") — that remains true and unaffected by this
  decision; arXiv submission itself, `CITATION.cff`, `v1.0-arxiv` tag, `make release` (Stage 7's
  broader Exit condition, already noted as outstanding in `reviews/stage7-human-signoff.md`).

## Outcome — recorded 2026-08-19

Disclosure notices to **Microsoft (MSRC)** and **Alibaba/Qwen** were **sent on 2026-08-19**, two
days after the repository went public. **No acknowledgement received from either vendor** as of
this record.

That closes the open action from this decision. It does not retroactively make the ordering
correct: PLAN.md §8 says notify *before* publicizing, and the repo went public first. Both facts
stay on the record — the deviation and its remedy — rather than the second being used to quietly
erase the first.

Non-response is not treated as a blocker. These were courtesy notifications claiming no novel
vulnerability, using published techniques on a public benchmark; vendors routinely do not reply to
such notices, and the §8 obligation is discharged by notifying, not by receiving an answer.

**Open caveat worth naming:** MSRC has a documented intake (the Researcher Portal) and Alibaba has
ASRC, but **no QwenLM model repository publishes a `SECURITY.md` or security address** (checked
2026-08-18 across `QwenLM/Qwen`, `Qwen2.5`, `Qwen3`). If the Qwen notice went to an address that
is not a monitored security channel, the notification may not have actually landed. Worth
confirming the channel used, and re-sending via ASRC if it was a guessed address.

## Cross-references updated as a result

- `README.md` — disclosure-plan line updated to note the repo went public 2026-08-17, ahead of the
  original "at arXiv posting" trigger; the stale "Gate 7 currently FAIL" line corrected to point at
  the actual 2026-08-08 sign-off.
- `paper/paper.md` §7 — disclosure paragraph updated to describe the actual current state (public
  repo, disclosure still pending) rather than the superseded "at arXiv posting" plan as if it were
  still the operative trigger.
