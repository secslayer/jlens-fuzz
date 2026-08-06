"""Stage 0 CI placeholder + config-invariant smoke checks (PLAN.md Gate 0)."""
import yaml


def test_placeholder():
    assert True


def test_exp_config_has_required_invariant_keys():
    with open("configs/exp.yaml") as f:
        cfg = yaml.safe_load(f)

    required = [
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
    missing = [k for k in required if k not in cfg]
    assert not missing, f"configs/exp.yaml missing required keys: {missing}"
