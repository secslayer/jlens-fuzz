#!/usr/bin/env python3
"""Train per-layer linear probes that detect refusal-relevant state from the residual stream.

Idea (well-established "refusal direction" / linear-probe approach):
  - Harmful instructions tend to drive the model toward a refusal-associated internal state.
  - Harmless instructions do not.
  - We extract the last-token hidden state at every layer (the position where the model is
    about to start generating), label harmful=1 / harmless=0, and fit one logistic-regression
    probe per layer. The best held-out layer gives us a cheap fitness signal for the fuzzing
    loop (probability the model is "about to refuse"): lower = better jailbreak candidate.

This trains the probes. The fuzzing loop later loads best_layer + weights and scores a
candidate via a PARTIAL forward pass to that layer (see scripts/run_fuzz.py).

Human gate (PLAN.md Stage 2): require best-layer held-out AUC >= 0.85, and hand-check a few
novel prompts, before building anything on top of this.
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import torch
import yaml
from datasets import load_dataset
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score
from sklearn.model_selection import train_test_split
from transformers import AutoModelForCausalLM, AutoTokenizer


def set_seed(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/exp.yaml")
    ap.add_argument("--out", default="results/probes")
    ap.add_argument("--n-per-class", type=int, default=300)
    ap.add_argument("--auc-threshold", type=float, default=0.85)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    set_seed(cfg.get("seed", 0))
    os.makedirs(args.out, exist_ok=True)

    model_id = cfg["target_model"]  # e.g. Qwen/Qwen2.5-3B-Instruct
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[probes] loading {model_id} on {device}")

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    ).to(device).eval()

    texts, labels = load_instructions(cfg["benchmark"], args.n_per_class, cfg.get("seed", 0))
    y = np.array(labels)
    print(f"[probes] extracting features for {len(texts)} prompts")
    X = extract_layer_features(model, tok, texts, device,
                               batch_size=cfg.get("probe_batch_size", 16))
    n, L, H = X.shape
    print(f"[probes] features {X.shape}  ({L} layers)")

    Xtr_i, Xte_i = train_test_split(np.arange(n), test_size=0.25,
                                    random_state=cfg.get("seed", 0), stratify=y)
    per_layer = []
    for layer in range(L):
        Xl = X[:, layer, :]
        clf = LogisticRegression(max_iter=2000, C=1.0)
        clf.fit(Xl[Xtr_i], y[Xtr_i])
        p = clf.predict_proba(Xl[Xte_i])[:, 1]
        auc = roc_auc_score(y[Xte_i], p)
        acc = accuracy_score(y[Xte_i], (p > 0.5).astype(int))
        per_layer.append({"layer": layer + 1, "auc": float(auc), "acc": float(acc)})
        print(f"  layer {layer+1:2d}  AUC {auc:.3f}  acc {acc:.3f}")

    best = max(per_layer, key=lambda d: d["auc"])
    print(f"[probes] BEST layer {best['layer']}  AUC {best['auc']:.3f}")

    # Refit best-layer probe on all data and save weights for the loop.
    bl = best["layer"] - 1
    clf = LogisticRegression(max_iter=2000, C=1.0).fit(X[:, bl, :], y)

    provenance = {
        "git_sha": git_sha(),
        "job": os.environ.get("JLENS_JOB", "probes"),
        "config_hash": config_hash(args.config),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    np.savez(os.path.join(args.out, "probe_best_layer.npz"),
             coef=clf.coef_, intercept=clf.intercept_, layer=best["layer"],
             provenance=json.dumps(provenance))

    summary = {
        "model": model_id,
        "best_layer": best["layer"],
        "best_auc": best["auc"],
        "auc_threshold": args.auc_threshold,
        "passes_gate": bool(best["auc"] >= args.auc_threshold),
        "per_layer": per_layer,
        "n_per_class": args.n_per_class,
        "_provenance": provenance,
    }
    json.dump(summary, open(os.path.join(args.out, "best_layer.json"), "w"), indent=2)

    if not summary["passes_gate"]:
        print(f"\n[GATE 2 FAIL] best AUC {best['auc']:.3f} < {args.auc_threshold}. "
              f"Do NOT proceed. Try: mean-pool tokens, multi-layer ensemble, or more data. "
              f"See PLAN.md Stage 2.")
    else:
        print(f"\n[GATE 2 pass — still requires human check on novel prompts]")


if __name__ == "__main__":
    main()
