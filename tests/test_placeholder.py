"""Stage 0 CI placeholder + config-invariant smoke checks (PLAN.md Gate 0)."""
import glob

import pytest
import yaml

ALL_CONFIGS = sorted(glob.glob("configs/exp*.yaml"))

REQUIRED_KEYS = [
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

# Per CLAUDE.md rule 3 ("identical conditions for baselines") and every configs/exp_*.yaml's own
# "MUST match" / "must match configs/exp.yaml exactly" comments: these keys are fuzzing-method or
# judge/benchmark invariants, not per-target choices, so every config variant must agree on them.
# target_model/mutate_model vary by design (that's the whole point of the target ladder);
# probe_batch_size is an intentional per-target VRAM tuning knob (configs/exp_gemma9b.yaml halves
# it and says so).
SHARED_ACROSS_TARGETS = [
    "seed",
    "judge_model",
    "judge_llm_model",
    "benchmark",
    "human_seed_templates",
    "seed_pool_size",
    "n_behaviors",
    "smoke_behaviors",
    "query_budget",
    "max_iterations",
    "decode_temperature",
    "decode_top_p",
    "partial_forward",
    "transfer_target_local",
]


def test_placeholder():
    assert True


@pytest.mark.parametrize("path", ALL_CONFIGS)
def test_exp_config_has_required_invariant_keys(path):
    with open(path) as f:
        cfg = yaml.safe_load(f)
    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    assert not missing, f"{path} missing required keys: {missing}"


def test_shared_invariants_match_across_all_targets():
    """Guards CLAUDE.md rule 3: a comparison run is only valid if judge/benchmark/budget/decoding
    stay fixed and only target_model/mutate_model vary. Every configs/exp_*.yaml comment claims
    this is already true by hand -- this test makes that claim self-enforcing so a future edit to
    one config can't silently drift the others out of sync."""
    assert len(ALL_CONFIGS) > 1, "expected multiple configs/exp*.yaml to compare"
    configs = {}
    for path in ALL_CONFIGS:
        with open(path) as f:
            configs[path] = yaml.safe_load(f)
    baseline_path, baseline_cfg = ALL_CONFIGS[0], configs[ALL_CONFIGS[0]]

    mismatches = []
    for key in SHARED_ACROSS_TARGETS:
        baseline_value = baseline_cfg.get(key)
        for path, cfg in configs.items():
            if cfg.get(key) != baseline_value:
                mismatches.append(
                    f"{key}: {baseline_path}={baseline_value!r} vs. {path}={cfg.get(key)!r}"
                )
    assert not mismatches, "config invariants drifted across targets:\n" + "\n".join(mismatches)
