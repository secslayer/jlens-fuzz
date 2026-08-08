#!/usr/bin/env python3
"""Build paper/paper.pdf from paper/paper.md via pandoc + xelatex.

Resolves the gap RUNBOOK.md Part 7 previously flagged ("no automated pipeline for this yet").
Not run in CI (requires a full TeX install, ~1GB+, not worth adding to the CI image for a
step that's only needed right before submission) -- run manually:

    python scripts/build_paper_pdf.py

Requires `pandoc` and `xelatex` on PATH. Does three things paper.md's own frontmatter isn't
meant for in a submission PDF:
  1. Strips paper.md's informal YAML frontmatter (title/status/date, meant for repo readers
     tracking draft status) and rebuilds clean PDF metadata (title/author/date) instead.
  2. Extracts the "## Abstract" section's content and renders it as a real title-page abstract
     (LaTeX `abstract` environment) rather than a numbered body section, removing it from the
     body so it isn't duplicated.
  3. Leaves everything else -- every §-cross-reference, every `[REDACTED ...]` marker, every
     `[DRAFT FLAG]`, all numbered section headings, the References list, Appendix A -- verbatim.
     This script does not reword or restructure paper content; see paper/pandoc-header.tex for
     the LaTeX-layer fixes (font/table-width issues) applied instead of touching the source.

Verifies, after building, that every §/REDACTED/DRAFT FLAG occurrence in the source markdown
(minus the one intentionally-dropped § in the stripped frontmatter's status line, and any in
the Abstract, which has none) survived into the rendered PDF text -- fails loudly if not,
rather than silently shipping a PDF with dropped content.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "paper" / "paper.md"
HEADER = REPO_ROOT / "paper" / "pandoc-header.tex"
OUT_PDF = REPO_ROOT / "paper" / "paper.pdf"

AUTHOR = "Muhammed Muiz Arummal"  # reviews/stage7-human-signoff.md's signed name


def require_tool(name):
    if subprocess.run(["which", name], capture_output=True).returncode != 0:
        sys.exit(f"required tool not found on PATH: {name}")


def extract_abstract_and_body(text):
    parts = text.split("---", 2)
    if len(parts) != 3:
        sys.exit("expected exactly one YAML frontmatter block delimited by ---")
    body = parts[2].lstrip("\n")

    m = re.search(r"^## Abstract\n\n(.*?)\n\n## ", body, re.S | re.M)
    if not m:
        sys.exit("could not find '## Abstract ... ## ' pattern in paper.md")
    abstract_text = m.group(1).strip()
    body_wo_abstract = body[: m.start()] + body[m.end() - 4 :]  # -4 keeps the trailing '## '

    if "## Abstract" in body_wo_abstract:
        sys.exit("failed to remove the Abstract section from the body")
    return abstract_text, body_wo_abstract


def build_final_markdown(abstract_text, body, title, date_str):
    indented_abstract = "\n".join(
        "  " + line if line.strip() else "" for line in abstract_text.split("\n")
    )
    frontmatter = (
        "---\n"
        f'title: "{title}"\n'
        f'author: "{AUTHOR}"\n'
        f'date: "{date_str}"\n'
        "abstract: |\n"
        f"{indented_abstract}\n"
        "fontsize: 11pt\n"
        "geometry: margin=1in\n"
        "colorlinks: false\n"
        "---\n\n"
    )
    return frontmatter + body


def verify_content_preserved(src_text, pdf_path):
    def count(text, marker):
        return text.count(marker)

    pdf_text = subprocess.run(
        ["pdftotext", str(pdf_path), "-"], capture_output=True, text=True, check=True
    ).stdout

    # str.split("---", 2) on a file starting with "---" yields ["", frontmatter, body] -- the
    # frontmatter's own status line (not paper content) has exactly one '§'; everything else in
    # the source must survive verbatim.
    _, frontmatter, body = src_text.split("---", 2)
    expected_section_refs = count(src_text, "§") - count(frontmatter, "§")
    for label, marker, expected in [
        ("§ cross-references", "§", expected_section_refs),
        ("[REDACTED ...] markers", "REDACTED", count(body, "REDACTED")),
        ("[DRAFT FLAG] markers", "DRAFT FLAG", count(body, "DRAFT FLAG")),
    ]:
        got = count(pdf_text, marker)
        if got != expected:
            sys.exit(
                f"CONTENT MISMATCH: {label} -- expected {expected} (from paper.md), "
                f"found {got} in the rendered PDF. Do not ship this PDF; inspect the pandoc/"
                f"xelatex output before retrying."
            )
        print(f"  {label}: {got}/{expected} OK")


def main():
    require_tool("pandoc")
    require_tool("xelatex")

    src_text = SRC.read_text(encoding="utf-8")
    title_m = re.search(r"^title: >\s*\n((?:  .*\n)+)", src_text, re.M)
    title = " ".join(line.strip() for line in title_m.group(1).splitlines()) if title_m else "jlens-fuzz"
    date_m = re.search(r"^date: (.+)$", src_text, re.M)
    date_str = f"DRAFT --- pre-arXiv --- {date_m.group(1).strip()}" if date_m else "DRAFT --- pre-arXiv"

    abstract_text, body = extract_abstract_and_body(src_text)
    final_md = build_final_markdown(abstract_text, body, title, date_str)

    with tempfile.TemporaryDirectory() as tmp:
        final_path = Path(tmp) / "final.md"
        final_path.write_text(final_md, encoding="utf-8")

        print(f"Running pandoc -> xelatex ({final_path} -> {OUT_PDF}) ...")
        subprocess.run(
            [
                "pandoc",
                str(final_path),
                "-o",
                str(OUT_PDF),
                "--pdf-engine=xelatex",
                f"--include-in-header={HEADER}",
                "-V",
                "linkcolor=black",
                "--standalone",
            ],
            check=True,
        )

    print(f"Built {OUT_PDF} ({OUT_PDF.stat().st_size} bytes). Verifying content preserved...")
    verify_content_preserved(src_text, OUT_PDF)
    print("OK -- all §-references, redaction markers, and DRAFT FLAGs verified intact.")


if __name__ == "__main__":
    main()
