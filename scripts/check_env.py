#!/usr/bin/env python3
"""Fast, CPU-only environment diagnostic — Stage 0/1 prep (RUNBOOK.md Day 1).

Run this BEFORE any heavy job, locally or on a fresh Kaggle kernel right after
`pip install -r requirements.txt`. It must succeed (exit 0) on a machine with no GPU: GPU
absence is informational, not a failure, because the Kaggle CPU dry run (PLAN.md Gate 0) has to
pass without a T4 attached.

Checks:
  1. Every package pinned in requirements.txt imports and reports a version.
  2. configs/exp.yaml exists and has all keys the pipeline invariants depend on.
  3. CUDA availability (report only, never fails).
  4. Hugging Face Hub reachability (best-effort; network failure is a warning, not a failure —
     offline dev must still pass, model pulls happen in the heavy-job scripts).
  5. results/, results/probes/, logs/ exist (created if missing).

Usage:
    python scripts/check_env.py --config configs/exp.yaml

Exit code 0 iff all HARD checks pass. Nonzero otherwise, so `make setup`-style CI can gate on it.
This is a diagnostic CLI, not a metrics job — it does not write results/*.json, so the
`_provenance` block convention does not apply here.
"""
import argparse
import importlib
import logging
import os
import sys

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [check_env] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("check_env")

# (requirements.txt name, importable module name)
REQUIRED_PACKAGES = [
    ("torch", "torch"),
    ("transformers", "transformers"),
    ("accelerate", "accelerate"),
    ("datasets", "datasets"),
    ("scikit-learn", "sklearn"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("pyyaml", "yaml"),
    ("matplotlib", "matplotlib"),
    ("joblib", "joblib"),
    ("huggingface_hub", "huggingface_hub"),
    # scripts/run_fuzz.py's corpus_self_bleu() imports this unconditionally, but only in the
    # aggregate-metrics step AFTER every behavior's generation+judging is done -- a missing
    # nltk would otherwise waste an entire run's GPU budget before failing. Catch it here instead.
    ("nltk", "nltk"),
]

# Config keys that every downstream script relies on as shared invariants (CLAUDE.md rule 3).
REQUIRED_CONFIG_KEYS = [
    "seed",
    "target_model",
    "judge_model",
    "judge_llm_model",
    "benchmark",
    "human_seed_templates",
    "n_behaviors",
    "smoke_behaviors",
    "query_budget",
    "max_iterations",
    "mutate_model",
    "decode_temperature",
    "decode_top_p",
    "probe_batch_size",
    "partial_forward",
    "transfer_target_local",
]

REQUIRED_DIRS = ["results", "results/probes", "logs"]


def check_packages():
    """Import every required package; return (ok, rows) where rows are (name, version_or_error)."""
    ok = True
    rows = []
    for pkg_name, mod_name in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(mod_name)
            version = getattr(mod, "__version__", "unknown")
            rows.append((pkg_name, version, True))
            log.info(f"PASS  import {pkg_name:<16} version={version}")
        except Exception as exc:  # noqa: BLE001 - we want to catch and report any import failure
            ok = False
            rows.append((pkg_name, str(exc), False))
            log.error(f"FAIL  import {pkg_name:<16} error={exc}")
    return ok, rows


def check_config(config_path):
    """Load YAML config and validate required keys. Return (ok, cfg_or_none, missing_keys)."""
    if not os.path.isfile(config_path):
        log.error(f"FAIL  config file not found: {config_path}")
        return False, None, REQUIRED_CONFIG_KEYS

    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
    except Exception as exc:  # noqa: BLE001
        log.error(f"FAIL  could not parse {config_path}: {exc}")
        return False, None, REQUIRED_CONFIG_KEYS

    if not isinstance(cfg, dict):
        log.error(f"FAIL  {config_path} did not parse to a mapping")
        return False, None, REQUIRED_CONFIG_KEYS

    missing = [k for k in REQUIRED_CONFIG_KEYS if k not in cfg]
    if missing:
        log.error(f"FAIL  {config_path} missing required keys: {missing}")
        return False, cfg, missing

    log.info(f"PASS  {config_path} present with all {len(REQUIRED_CONFIG_KEYS)} required keys")
    return True, cfg, []


def check_cuda():
    """Report CUDA availability. Informational only — never fails (CPU dry run must pass)."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            log.info(f"INFO  CUDA available: {name} (device count={torch.cuda.device_count()})")
            return True, name
        else:
            log.warning("INFO  CUDA not available — running on CPU (expected for Kaggle dry run)")
            return False, None
    except Exception as exc:  # noqa: BLE001
        log.warning(f"WARN  could not query torch.cuda: {exc}")
        return False, None


def check_hf_hub():
    """Best-effort check that the HF Hub is reachable/configured. Failure is a warning only."""
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        api.whoami() if os.environ.get("HF_TOKEN") else api.model_info("gpt2")
        log.info("PASS  Hugging Face Hub reachable")
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning(f"WARN  Hugging Face Hub not reachable / not configured (non-fatal): {exc}")
        return False


def ensure_dirs(dirs):
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        log.info(f"PASS  directory ready: {d}")
    return True


def main():
    ap = argparse.ArgumentParser(description="Stage 0/1 environment diagnostic (CPU-safe).")
    ap.add_argument("--config", default="configs/exp.yaml", help="Path to the shared exp config.")
    args = ap.parse_args()

    log.info("=== jlens-fuzz environment check ===")

    hard_failures = []

    log.info("--- 1/5 package imports ---")
    pkgs_ok, _pkg_rows = check_packages()
    if not pkgs_ok:
        hard_failures.append("package imports")

    log.info("--- 2/5 config validation ---")
    cfg_ok, cfg, missing_keys = check_config(args.config)
    if not cfg_ok:
        hard_failures.append("config validation")

    log.info("--- 3/5 CUDA availability (informational) ---")
    check_cuda()

    log.info("--- 4/5 Hugging Face Hub reachability (best-effort) ---")
    check_hf_hub()

    log.info("--- 5/5 required directories ---")
    ensure_dirs(REQUIRED_DIRS)

    log.info("=== summary ===")
    if hard_failures:
        log.error(f"OVERALL FAIL — failing checks: {', '.join(hard_failures)}")
        if not cfg_ok and missing_keys:
            log.error(f"  missing config keys: {missing_keys}")
        sys.exit(1)
    else:
        log.info("OVERALL PASS — environment is ready.")
        sys.exit(0)


if __name__ == "__main__":
    main()
