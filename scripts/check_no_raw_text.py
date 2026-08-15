#!/usr/bin/env python3
"""Content-based guard against committing raw jailbreak/completion text (CLAUDE.md golden rule 1,
PLAN.md §8). Built after `/review 7` (reviews/stage7.md) found that filename-pattern .gitignore
matching alone let results/debug_attribution_{qwen,phi}.log slip through with assembled
jailbreak-template fragments -- the file didn't match `prompts_*`/`*jailbreak*`.

This scans file CONTENT, not just filenames, so it isn't defeated by a future file having a name
the .gitignore patterns don't anticipate. It is one layer, not a guarantee: it looks for known
field-name shapes (`text=`, `completion=`/`"completion"`, `candidate=`/`"candidate"`,
`"prompt"`) used by this project's own logging/JSON output. A field carrying raw text under a
name this script doesn't know about would not be caught -- pair this with human review at
generation time, not as the only safeguard.

Usage:
  python scripts/check_no_raw_text.py [FILE ...]     # check specific files (pre-commit use)
  python scripts/check_no_raw_text.py                # check every tracked file under results/ (CI use)

Exits 1 and prints every offending line (path:line:content) if anything is found; exits 0
otherwise. Never writes/modifies anything.
"""
import re
import subprocess
import sys

# The one sanctioned way a "text="-shaped field may appear: the redaction marker itself
# (results/debug_attribution_*.log, paper/paper.md §5.3 -- see reviews/stage7.md).
SAFE_MARKER = "[REDACTED — jailbreak-template fragment]"

# (label, compiled pattern). Patterns match the FIELD, not content generically, to keep false
# positives low against this project's own results/*.json schema (PLAN.md §7), which never uses
# these field names for aggregate scalars.
PATTERNS = [
    ("text= field", re.compile(r"""\btext=['"]""")),
    ("JSON/py \"completion\" field", re.compile(r"""["']completion["']\s*[:=]""")),
    ("JSON/py \"candidate\" field", re.compile(r"""["']candidate["']\s*[:=]""")),
    ("JSON/py \"prompt\" field", re.compile(r"""["']prompt["']\s*:""")),
    ("JSON/py \"template\" field", re.compile(r"""["']template["']\s*[:=]""")),
]

# Filename-pattern check kept as defense-in-depth even though content scanning is now primary --
# catches the case where someone force-adds a gitignored file (git add -f).
FILENAME_PATTERNS = [re.compile(r"prompts_"), re.compile(r"jailbreak", re.IGNORECASE)]


def tracked_results_files():
    out = subprocess.run(
        ["git", "ls-files", "results/"], capture_output=True, text=True, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


# How far past a matched field name to look for the redaction marker before deciding this
# specific occurrence is safe. Must comfortably cover `='[REDACTED ... fragment]'` /
# `: "[REDACTED ... fragment]"` wrapping -- SAFE_MARKER itself is ~41 chars.
MARKER_PROXIMITY_CHARS = 80


def check_file(path):
    findings = []
    for fp in FILENAME_PATTERNS:
        if fp.search(path):
            findings.append((path, 0, f"[filename] matches {fp.pattern!r}"))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, start=1):
                for label, pat in PATTERNS:
                    for m in pat.finditer(line):
                        # Check proximity to THIS match, not marker-presence anywhere in the
                        # line -- a line can legitimately hold one redacted field (e.g.
                        # "template") next to a separate, unredacted one (e.g. "completion");
                        # a whole-line skip would silently miss the second field entirely.
                        window = line[m.end():m.end() + MARKER_PROXIMITY_CHARS]
                        if SAFE_MARKER in window:
                            continue
                        findings.append((path, lineno, f"[{label}] {line.strip()[:160]}"))
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        pass
    return findings


def main():
    targets = sys.argv[1:]
    if not targets:
        targets = [p for p in tracked_results_files() if not p.endswith((".npz", ".gitkeep"))]

    all_findings = []
    for path in targets:
        all_findings.extend(check_file(path))

    if all_findings:
        print("BLOCKED: possible raw jailbreak/completion text found (CLAUDE.md golden rule 1):")
        for path, lineno, msg in all_findings:
            loc = f"{path}:{lineno}" if lineno else path
            print(f"  {loc}: {msg}")
        print(
            "\nIf this is a genuine false positive (e.g. a new field name that only ever holds "
            "safe scalar data), extend PATTERNS' allowlist logic in scripts/check_no_raw_text.py "
            "deliberately -- do not just delete the finding. If it's real: redact it "
            f"(replace the value with the literal string {SAFE_MARKER!r}) before committing."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
