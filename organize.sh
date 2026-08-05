#!/usr/bin/env bash
# organize.sh — turn a FLAT zip of scaffold files into the proper jlens-fuzz repo layout.
#
# Usage:
#   1. put this script in the SAME folder as file.zip
#   2. bash organize.sh
#   3. it creates ./jlens-fuzz/ with correct subfolders and tells you what's still missing
#
# Safe to re-run: it overwrites destinations and skips files that aren't present.

set -uo pipefail
ZIP=${1:-file.zip}
OUT=jlens-fuzz
TMP=_unzipped

if [ ! -f "$ZIP" ]; then
  echo "ERROR: $ZIP not found. cd to the folder containing it, or: bash organize.sh /path/to/file.zip"
  exit 1
fi

echo "==> unzipping $ZIP"
rm -rf "$TMP" && mkdir -p "$TMP"
unzip -q -o "$ZIP" -d "$TMP"
# macOS zips often carry these; drop them
rm -rf "$TMP/__MACOSX" "$TMP/.DS_Store" 2>/dev/null

echo "==> creating repo structure"
mkdir -p "$OUT"/{scripts,configs,results,reviews,logs} "$OUT"/.claude/{agents,commands}

# place <filename> <destination-relative-to-$OUT>
place() {
  local name="$1" dest="$2"
  # find it anywhere inside the unzipped tree (handles zips with a wrapper folder)
  local src
  src=$(find "$TMP" -type f -name "$name" ! -path '*__MACOSX*' | head -1)
  if [ -n "$src" ]; then
    mkdir -p "$OUT/$(dirname "$dest")"
    cp "$src" "$OUT/$dest"
    echo "   ok      $name  ->  $dest"
  else
    echo "   MISSING $name  (needed at $dest)"
    echo "$name" >> "$TMP/.missing"
  fi
}

echo "==> filing root docs"
place PLAN.md            PLAN.md
place ORCHESTRATION.md   ORCHESTRATION.md
place RUNBOOK.md         RUNBOOK.md
place CLAUDE.md          CLAUDE.md
place Makefile           Makefile
place experiments.yaml   experiments.yaml
place requirements.txt   requirements.txt
place .gitignore         .gitignore

echo "==> filing configs/"
# the config was presented as exp.yaml; it must land as configs/exp.yaml
place exp.yaml           configs/exp.yaml

echo "==> filing scripts/"
place train_probes.py    scripts/train_probes.py
place run_controller.py  scripts/run_controller.py
place run_experiment.py  scripts/run_experiment.py
place run_parallel.sh    scripts/run_parallel.sh

echo "==> filing .claude/ (NOTE: reviewer.md -> agents, review.md -> commands)"
place reviewer.md        .claude/agents/reviewer.md
place builder.md         .claude/agents/builder.md
place review.md          .claude/commands/review.md
place orchestrate.md     .claude/commands/orchestrate.md

chmod +x "$OUT/scripts/run_parallel.sh" 2>/dev/null

# .gitignore is hidden and often absent from zips — generate it if missing
if [ ! -f "$OUT/.gitignore" ]; then
  echo "==> .gitignore absent from zip; generating the required one"
  cat > "$OUT/.gitignore" <<'GI'
.env
*.key
.kaggle/
kaggle.json
__pycache__/
*.pyc
.venv/
checkpoints/
logs/
# never commit generated attack strings
results/**/prompts_*
results/**/*jailbreak*
paper/build/
GI
  # it's handled — don't report it as missing
  if [ -f "$TMP/.missing" ]; then
    grep -v '^\.gitignore$' "$TMP/.missing" > "$TMP/.m2" || true
    mv "$TMP/.m2" "$TMP/.missing"
    [ -s "$TMP/.missing" ] || rm -f "$TMP/.missing"
  fi
fi

echo
echo "==> resulting structure"
find "$OUT" -type f | sort | sed 's/^/   /'

echo
if [ -f "$TMP/.missing" ]; then
  echo "==> STILL MISSING (download these from the chat, drop them in this folder, re-run):"
  sort -u "$TMP/.missing" | sed 's/^/   - /'
else
  echo "==> complete: all expected files present."
fi
rm -rf "$TMP"
