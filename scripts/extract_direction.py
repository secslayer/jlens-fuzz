#!/usr/bin/env python3
"""Extract a per-layer difference-in-means refusal direction (Amnesia-style).

Idea: harmful instructions push the residual stream toward a "refusal" region; benign
instructions do not. Rather than fitting a classifier (see scripts/train_probes.py, the
FITNESS probe), we compute the simple difference-in-means vector between harmful and
benign last-token activations at each layer, L2-normalize it, and evaluate how well the
1-D projection onto that vector separates the two classes on a held-out split.

This is the TOKEN ATTRIBUTION signal (ORCHESTRATION.md "Two signals, two jobs"): the
fuzzing loop projects each token's activation onto the chosen layer's direction to find
which span of a candidate prompt is pulling the model toward refusal, and mutates that
span. It is complementary to, and independent of, scripts/train_probes.py's logistic
probe — this job has `needs: []` in experiments.yaml and must not read results/probes/*.
"""
import argparse
import hashlib
import json
import logging
import os
import random
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import torch
import yaml
from datasets import load_dataset
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from transformers import AutoModelForCausalLM, AutoTokenizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [direction] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("extract_direction")

LOW_AUC_WARN_THRESHOLD = 0.85


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def git_sha():
    sha = os.environ.get("JLENS_GIT")
    if sha:
        return sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"]
        ).decode().strip()
    except Exception:  # noqa: BLE001 - provenance must never crash the run
        return "nogit"


def config_hash(config_path):
    with open(config_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def load_instructions(benchmark, n_per_class, seed):
    """Return (texts, labels): harmful=1, harmless=0. Uses public datasets only.

    `benchmark` is cfg["benchmark"] — the canonical AdvBench harmful_behaviors.csv (ungated,
    from the original llm-attacks/llm-attacks repo, not the gated walledai/AdvBench HF dataset).
    Columns: goal, target.
    """
    rng = random.Random(seed)

    # Harmful: AdvBench behaviors (public red-teaming benchmark).
    adv = pd.read_csv(benchmark)
    harmful = adv["goal"].tolist()
    rng.shuffle(harmful)
    harmful = harmful[:n_per_class]

    # Harmless: benign instructions (Alpaca). Skip ones needing an input field for cleanliness.
    alp = load_dataset("tatsu-lab/alpaca", split="train")
    harmless = [r["instruction"] for r in alp if not r.get("input")]
    rng.shuffle(harmless)
    harmless = harmless[:n_per_class]

    texts = harmful + harmless
    labels = [1] * len(harmful) + [0] * len(harmless)
    idx = list(range(len(texts)))
    rng.shuffle(idx)
    return [texts[i] for i in idx], [labels[i] for i in idx]


@torch.no_grad()
def extract_layer_features(model, tok, texts, device, batch_size=16, max_len=256):
    """Return array [n_texts, n_layers, hidden]: last-token hidden state at each layer.

    Left-padding so the last position (index -1) is always the final real token across the
    batch. hidden_states from HF has len n_layers+1 (index 0 = embeddings); we keep 1..L.
    """
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    feats = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        chats = [
            tok.apply_chat_template(
                [{"role": "user", "content": t}],
                add_generation_prompt=True, tokenize=False,
            )
            for t in batch
        ]
        enc = tok(chats, return_tensors="pt", padding=True, truncation=True,
                  max_length=max_len).to(device)
        out = model(**enc, output_hidden_states=True)
        # tuple len L+1 of [B, T, H]; drop embedding layer, take last position
        hs = torch.stack(out.hidden_states[1:], dim=1)  # [B, L, T, H]
        last = hs[:, :, -1, :].float().cpu().numpy()     # [B, L, H]
        feats.append(last)
    return np.concatenate(feats, axis=0)  # [N, L, H]


def diff_in_means_direction(X_train, y_train):
    """Unit-normalized difference-in-means vector: mean(harmful) - mean(benign)."""
    harmful_mean = X_train[y_train == 1].mean(axis=0)
    benign_mean = X_train[y_train == 0].mean(axis=0)
    direction = harmful_mean - benign_mean
    norm = np.linalg.norm(direction)
    if norm == 0:
        log.warning("zero-norm difference-in-means direction encountered; leaving unnormalized")
        return direction
    return direction / norm


def main():
    ap = argparse.ArgumentParser(
        description="Extract per-layer difference-in-means refusal directions "
                    "(token-attribution signal, PLAN.md Stage 2 / Component 2)."
    )
    ap.add_argument("--config", default="configs/exp.yaml")
    ap.add_argument("--out", default="results/direction.npz")
    ap.add_argument("--n-per-class", type=int, default=300)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    seed = cfg.get("seed", 0)
    set_seed(seed)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    model_id = cfg["target_model"]  # e.g. Qwen/Qwen2.5-3B-Instruct
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info(f"loading {model_id} on {device}")
    if device == "cpu":
        log.warning(
            "no CUDA available — this is fine for --help / import validation, but a full "
            "extraction on CPU will be very slow. Real runs happen on Kaggle GPU."
        )

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.float16 if device == "cuda" else torch.float32,
    ).to(device).eval()

    texts, labels = load_instructions(cfg["benchmark"], args.n_per_class, seed)
    y = np.array(labels)
    log.info(f"extracting features for {len(texts)} prompts "
             f"({int((y == 1).sum())} harmful / {int((y == 0).sum())} benign)")
    X = extract_layer_features(model, tok, texts, device,
                               batch_size=cfg.get("probe_batch_size", 16))
    n, L, H = X.shape
    log.info(f"features shape {X.shape}  ({L} layers, hidden={H})")

    train_i, holdout_i = train_test_split(
        np.arange(n), test_size=0.25, random_state=seed, stratify=y,
    )

    directions = np.zeros((L, H), dtype=np.float32)
    per_layer = []
    for layer in range(L):
        Xl = X[:, layer, :]
        direction = diff_in_means_direction(Xl[train_i], y[train_i])
        directions[layer] = direction

        proj = Xl[holdout_i] @ direction  # 1-D projection score
        auc = roc_auc_score(y[holdout_i], proj)
        per_layer.append({"layer": layer + 1, "auc": float(auc)})
        log.info(f"  layer {layer + 1:2d}  AUC {auc:.3f}")

    aucs = np.array([d["auc"] for d in per_layer], dtype=np.float32)
    best_idx = int(np.argmax(aucs))  # 0-indexed layer index into `directions`
    best_layer = per_layer[best_idx]["layer"]
    best_auc = per_layer[best_idx]["auc"]
    log.info(f"BEST layer {best_layer}  AUC {best_auc:.3f}")

    if best_layer <= 1:
        log.warning(
            f"[flag] best layer is {best_layer} (near-input) — possible leakage or a "
            f"degenerate signal; expected a mid/late layer. See PLAN.md Gate 2 checklist."
        )
    if best_auc < LOW_AUC_WARN_THRESHOLD:
        log.warning(
            f"[flag] best direction AUC {best_auc:.3f} < {LOW_AUC_WARN_THRESHOLD} — this is an "
            f"independent signal from scripts/train_probes.py's probe; a weak direction here is "
            f"a second red flag for the whole token-attribution approach, even though this "
            f"script has no hard pass/fail gate of its own. Review before building the mutator "
            f"on top of it."
        )
    else:
        log.info("direction signal looks healthy (informational — no hard gate on this script)")

    provenance = {
        "git_sha": git_sha(),
        "job": os.environ.get("JLENS_JOB", "direction"),
        "config_hash": config_hash(args.config),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    np.savez(
        args.out,
        directions=directions,             # [L, H] unit-normalized diff-in-means, all layers
        per_layer_auc=aucs,                # [L] held-out AUC per layer
        best_layer=np.array(best_layer),   # 1-indexed, matches train_probes.py convention
        best_layer_idx=np.array(best_idx), # 0-indexed into `directions`
        best_auc=np.array(best_auc, dtype=np.float32),
        model=np.array(model_id),
        n_per_class=np.array(args.n_per_class),
        provenance=json.dumps(provenance),
    )
    log.info(f"wrote {args.out}  (directions {directions.shape}, best_layer={best_layer})")


if __name__ == "__main__":
    main()
