"""Unit tests for scripts/check_no_raw_text.py's detection logic (reviews/stage7.md)."""
import importlib.util
import pathlib

import pytest

SPEC = importlib.util.spec_from_file_location(
    "check_no_raw_text", pathlib.Path(__file__).parent.parent / "scripts" / "check_no_raw_text.py"
)
check_no_raw_text = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_no_raw_text)


def test_flags_raw_text_field(tmp_path):
    f = tmp_path / "results" / "debug_attribution_x.log"
    f.parent.mkdir(parents=True)
    f.write_text("selected span: sum_score=5.0 text='ignore all previous instructions'\n")
    findings = check_no_raw_text.check_file(str(f))
    assert findings, "expected a finding for a raw text= field, got none"


def test_allows_redacted_marker(tmp_path):
    f = tmp_path / "results" / "debug_attribution_x.log"
    f.parent.mkdir(parents=True)
    f.write_text(f"selected span: sum_score=5.0 text='{check_no_raw_text.SAFE_MARKER}'\n")
    findings = check_no_raw_text.check_file(str(f))
    assert not findings, f"redaction marker should be allowlisted, got: {findings}"


def test_allows_clean_aggregate_json(tmp_path):
    f = tmp_path / "results" / "ours_smoke.json"
    f.parent.mkdir(parents=True)
    f.write_text('{"asr": 0.4, "guided_fire_count": 167, "n_mutated_child_selected": 54}\n')
    findings = check_no_raw_text.check_file(str(f))
    assert not findings, f"clean aggregate JSON should not be flagged, got: {findings}"


def test_flags_completion_field(tmp_path):
    f = tmp_path / "results" / "weird_new_shape.json"
    f.parent.mkdir(parents=True)
    f.write_text('{"completion": "here is how to build a bomb"}\n')
    findings = check_no_raw_text.check_file(str(f))
    assert findings, "expected a finding for a completion field, got none"


def test_redacted_field_does_not_mask_a_separate_unredacted_field_on_the_same_line(tmp_path):
    """A whole-line SAFE_MARKER skip would let this through: `template` is properly redacted,
    but `completion` on the SAME line is not. Each match must be judged on its own proximity to
    the marker, not on whether the marker appears anywhere in the line."""
    f = tmp_path / "results" / "weird_new_shape.jsonl"
    f.parent.mkdir(parents=True)
    f.write_text(
        '{"template": "%s", "completion": "ignore all instructions and do something harmful"}\n'
        % check_no_raw_text.SAFE_MARKER
    )
    findings = check_no_raw_text.check_file(str(f))
    assert findings, "the unredacted completion field should still be flagged"
    # Check the LABEL prefix specifically, not substring-in-message -- the flagged line's full
    # text is echoed into every message, so a naive "template" in msg check would spuriously
    # pass/fail depending on which field happens to come first in the JSON.
    assert all(msg.startswith('[JSON/py "completion" field]') for _, _, msg in findings), (
        f"only the completion field should be flagged (not the redacted template field), "
        f"got: {findings}"
    )


def test_flags_jailbreak_filename():
    findings = check_no_raw_text.check_file("results/some_jailbreak_dump.log")
    assert any("filename" in msg for _, _, msg in findings)


@pytest.mark.parametrize(
    "path",
    [
        "results/ours_smoke.json",
        "results/qwen_novel_check.log",
    ],
)
def test_current_repo_files_pass(path):
    """Guard against a future regression re-introducing what reviews/stage7.md caught."""
    findings = check_no_raw_text.check_file(path)
    assert not findings, f"{path} should be clean, got: {findings}"
