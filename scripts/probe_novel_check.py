#!/usr/bin/env python3
"""Interactive human tool for PLAN.md Gate 2's novel-prompt sanity check.

PLAN.md Stage 2 Gate 2 checklist item: "Probe separates a few *novel* hand-written
harmful/benign prompts (👤 you write 6)." This script is that check. It is NOT a pipeline
job: it is not declared in experiments.yaml's manifest, it has no `produces:` result file in
the DAG, and it writes NOTHING to disk -- it is a console-only tool for a human to run and
eyeball, the same non-manifest status as scripts/check_env.py and scripts/sanity_check.py.

It loads the two Component-2 artifacts:
  - scripts/train_probes.py     -> results/probes/probe_best_layer.npz
  - scripts/extract_direction.py -> results/direction.npz
runs 6 human-labeled novel prompts through the target model in `configs/exp.yaml` (one
forward pass each, output_hidden_states=True), scores each with both the probe and the
direction, and prints a simple separation summary.

SAFETY (CLAUDE.md golden rule 1 / .gitignore's `results/**/prompts_*`): the 6 novel prompts
you hand-write for this check are exactly the kind of "attack string" text that must never be
committed. Two ways to supply them:
  1. Edit the placeholder list below IN THIS FILE (tracked in git) -- only do this with
     obviously-benign example wording, never real harmful-request phrasing.
  2. (Recommended for real content) Write your 6 prompts to a local JSON file matching the
     gitignored `results/**/prompts_*` pattern, e.g. `results/prompts_novel_check.json`
     (already covered, no .gitignore edit needed -- verify with
     `git check-ignore -v results/prompts_novel_check.json`), and pass
     `--prompts-file results/prompts_novel_check.json`. That file is never tracked by git.
     Format: a JSON list of `{"text": "...", "label": "harmful"|"benign"}` objects.

Regardless of source, this script never logs or writes prompt text anywhere -- only
index / label / scores are printed, uniformly for both the inline list and --prompts-file,
so real content supplied via either path can never leak into logs or disk artifacts.
"""
import argparse
import hashlib
import json
import logging
import os
import subprocess

import numpy as np
import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [novel_check] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("probe_novel_check")

# ---------------------------------------------------------------------------------------------
# PLAN.md Gate 2 requires a HUMAN to write these 6 prompts fresh -- do not fill these in with
# agent-generated content. Edit this list locally before running (3 conversationally-phrased
# harmful requests, 3 benign imperatives), or -- to keep real prompt text fully out of git --
# use the --prompts-file option described in the module docstring above instead.
# ---------------------------------------------------------------------------------------------
DEFAULT_NOVEL_PROMPTS = [
    {"text": "REPLACE_ME: write your own conversational harmful-request phrasing #1 here",
     "label": "harmful"},
    {"text": "REPLACE_ME: write your own conversational harmful-request phrasing #2 here",
     "label": "harmful"},
    {"text": "REPLACE_ME: write your own conversational harmful-request phrasing #3 here",
     "label": "harmful"},
    {"text": "REPLACE_ME: write your own benign imperative-phrased prompt #1 here",
     "label": "benign"},
    {"text": "REPLACE_ME: write your own benign imperative-phrased prompt #2 here",
     "label": "benign"},
    {"text": "REPLACE_ME: write your own benign imperative-phrased prompt #3 here",
     "label": "benign"},
]


def git_sha():
    sha = os.environ.get("JLENS_GIT")
    if sha:
        return sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"]
        ).decode().strip()
    except Exception:  # noqa: BLE001 - must never crash the run
        return "nogit"


def config_hash(config_path):
    with open(config_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def require_upstream_file(path, job_name):
    """Fail loudly (no raw traceback) if an upstream artifact is missing."""
    if not os.path.exists(path):
        raise SystemExit(
            f"[probe_novel_check] missing required upstream artifact: {path}\n"
            f"This is produced by `make job JOB={job_name}` "
            f"(see experiments.yaml / ORCHESTRATION.md DAG). Run that job first."
        )


def load_probe(path):
    require_upstream_file(path, "probes")
    npz = np.load(path)
    coef = npz["coef"]              # [1, H]
    intercept = npz["intercept"]    # [1]
    layer = int(npz["layer"])       # 1-indexed
    return coef, intercept, layer


def load_direction(path):
    require_upstream_file(path, "direction")
    npz = np.load(path)
    directions = npz["directions"]                # [L, H]
    best_layer_idx = int(npz["best_layer_idx"])    # 0-indexed
    best_layer = int(npz["best_layer"])            # 1-indexed
    model_id = str(npz["model"])
    provenance = json.loads(str(npz["provenance"]))
    return directions, best_layer_idx, best_layer, model_id, provenance


def load_prompts(prompts_file):
    """Return the 6 labeled novel prompts, from --prompts-file if given, else the inline list."""
    if prompts_file is None:
        log.info(
            "using inline DEFAULT_NOVEL_PROMPTS -- if these are still REPLACE_ME placeholders, "
            "edit them locally (or use --prompts-file) before this check is meaningful"
        )
        return DEFAULT_NOVEL_PROMPTS
    with open(prompts_file) as f:
        prompts = json.load(f)
    if not isinstance(prompts, list) or not prompts:
        raise SystemExit(f"[probe_novel_check] {prompts_file} must contain a non-empty JSON list")
    for p in prompts:
        if "text" not in p or "label" not in p or p["label"] not in ("harmful", "benign"):
            raise SystemExit(
                f"[probe_novel_check] each entry in {prompts_file} needs 'text' and "
                f"'label' in {{'harmful', 'benign'}}, got: {p!r}"
            )
    log.info(f"loaded {len(prompts)} prompts from {prompts_file} (text will not be logged)")
    return prompts


def load_target(model_id, device):
    log.info(f"loading target model {model_id} on {device}")
    tok = AutoTokenizer.from_pretrained(model_id)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    ).to(device).eval()
    return tok, model


@torch.no_grad()
def extract_last_token_hidden(model, tok, prompt_text, device, max_len=256):
    """One forward pass; return hidden_states stacked [L, H] at the last token position.

    Same chat-template + left-pad + last-token pattern as train_probes.py's
    extract_layer_features() / validate_signal.py's extract_last_token_hidden() (single-prompt
    batch size 1 here since this is an interactive per-prompt check).
    """
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    chat = tok.apply_chat_template(
        [{"role": "user", "content": prompt_text}],
        add_generation_prompt=True, tokenize=False,
    )
    enc = tok(chat, return_tensors="pt", truncation=True, max_length=max_len).to(device)
    out = model(**enc, output_hidden_states=True)
    # tuple len L+1 of [1, T, H]; drop embedding layer (index 0), keep last position
    hs = torch.stack(out.hidden_states[1:], dim=0)  # [L, 1, T, H]
    last = hs[:, 0, -1, :].float().cpu().numpy()      # [L, H]
    return last


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def main():
    ap = argparse.ArgumentParser(
        description="PLAN.md Gate 2 human sanity check: does the probe/direction separate "
                    "6 novel hand-written harmful/benign prompts? Console tool only, writes "
                    "nothing to disk, not part of experiments.yaml's manifest."
    )
    ap.add_argument("--config", default="configs/exp.yaml")
    ap.add_argument("--probes", default="results/probes/probe_best_layer.npz")
    ap.add_argument("--direction", default="results/direction.npz")
    ap.add_argument(
        "--prompts-file", default=None,
        help="optional path to a JSON list of {'text':..., 'label':'harmful'|'benign'} "
             "objects, e.g. results/prompts_novel_check.json (gitignored via "
             "results/**/prompts_*). If omitted, uses the inline placeholder list in this "
             "file, which you must edit locally with your own 6 prompts first.",
    )
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info(f"device={device}")
    if device == "cpu":
        log.warning(
            "no CUDA available -- this is fine for --help / import validation, but a full "
            "check on CPU will be slow. Real checks happen on Kaggle GPU."
        )

    coef, intercept, probe_layer = load_probe(args.probes)
    directions, dir_layer_idx, dir_layer, dir_model_id, dir_provenance = load_direction(
        args.direction
    )
    log.info(
        f"loaded probe (layer={probe_layer}) and direction (layer={dir_layer}, "
        f"idx={dir_layer_idx}) from {args.probes} / {args.direction}"
    )

    target_model_id = cfg["target_model"]
    if dir_model_id and dir_model_id != target_model_id:
        log.warning(
            f"[model mismatch] direction extracted on {dir_model_id!r} but config target_model "
            f"is {target_model_id!r}"
        )

    prompts = load_prompts(args.prompts_file)
    if len(prompts) != 6:
        log.warning(
            f"PLAN.md Gate 2 asks for exactly 6 novel prompts; got {len(prompts)}. Proceeding "
            f"anyway, but this is not the checklist item as specified."
        )

    tok, model = load_target(target_model_id, device)

    probe_scores, direction_scores, my_labels = [], [], []
    for i, p in enumerate(prompts):
        prompt_text = p["text"]
        my_label = p["label"]

        hidden = extract_last_token_hidden(model, tok, prompt_text, device)  # [L, H]

        probe_h = hidden[probe_layer - 1]  # 1-indexed -> 0-indexed
        probe_logit = float(coef @ probe_h + intercept[0])
        probe_score = float(sigmoid(probe_logit))

        direction_h = hidden[dir_layer_idx]
        direction_score = float(direction_h @ directions[dir_layer_idx])

        probe_scores.append(probe_score)
        direction_scores.append(direction_score)
        my_labels.append(my_label)

        # NEVER log prompt text -- treat inline list and --prompts-file identically, uniformly.
        log.info(
            f"[{i+1}/{len(prompts)}] my_label={my_label} "
            f"probe_score={probe_score:.3f} direction_score={direction_score:.3f}"
        )

    probe_scores_arr = np.array(probe_scores)
    labels_arr = np.array(my_labels)

    # Probe: has a calibrated 0.5 threshold (probe_score > 0.5 predicts "harmful").
    probe_pred_harmful = probe_scores_arr > 0.5
    y_true_harmful = labels_arr == "harmful"
    probe_acc = float(np.mean(probe_pred_harmful == y_true_harmful))
    log.info(f"probe accuracy @0.5 threshold on {len(prompts)} novel prompts: {probe_acc:.3f}")

    # Direction: no calibrated threshold anywhere upstream -- report mean separation only.
    harmful_mask = labels_arr == "harmful"
    benign_mask = labels_arr == "benign"
    if harmful_mask.any() and benign_mask.any():
        mean_dir_harmful = float(np.mean([direction_scores[i] for i in range(len(prompts))
                                          if harmful_mask[i]]))
        mean_dir_benign = float(np.mean([direction_scores[i] for i in range(len(prompts))
                                         if benign_mask[i]]))
        expected_order = mean_dir_harmful > mean_dir_benign
        log.info(
            f"direction score: mean(harmful)={mean_dir_harmful:.3f}  "
            f"mean(benign)={mean_dir_benign:.3f}  "
            f"harmful_mean_higher={expected_order} "
            f"({'expected separation' if expected_order else 'UNEXPECTED -- inspect'})"
        )
    else:
        log.warning(
            "cannot compute direction separation -- prompts list has only one class present"
        )

    log.info(
        "PLAN.md Gate 2 checklist item ('Probe separates a few novel hand-written "
        "harmful/benign prompts') -- eyeball the per-prompt scores above and the summary "
        "just printed. This script makes no pass/fail decision for you; it is a human check."
    )
    log.info("this tool writes nothing to disk (console-only) -- no results/*.json produced.")


if __name__ == "__main__":
    main()
