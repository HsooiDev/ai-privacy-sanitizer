"""Synthetic import validation regressions; malformed files never mutate a live vault."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sanitizer import PrivacySanitizer, SessionVault


def valid_payload():
    return {
        "original_to_placeholder": {"synthetic-only": "[DB_PASS_1]"},
        "placeholder_to_original": {"[DB_PASS_1]": "synthetic-only"},
        "original_to_category": {"synthetic-only": "DB_PASS"},
        "category_counters": {"DB_PASS": 1},
        "total_intercepted_hits": 1,
    }


def invalid_payloads():
    yield {"original_to_placeholder": {"synthetic-only": "synthetic-only"}}
    yield {"placeholder_to_original": {"password": "synthetic-only"}}
    yield {"placeholder_to_original": {"": "synthetic-only"}}
    yield []
    for field, value in [
        ("original_to_placeholder", []),
        ("original_to_placeholder", {"synthetic-only": "[DB_PASS_2]"}),
        ("placeholder_to_original", {"[DB_PASS_1]": "different synthetic"}),
        ("original_to_category", {}),
        ("original_to_category", {"synthetic-only": "EMAIL"}),
        ("category_counters", {"DB_PASS": -1}),
        ("category_counters", {"DB_PASS": True}),
        ("category_counters", {"DB_PASS": "not a counter"}),
        ("total_intercepted_hits", -1),
    ]:
        payload = valid_payload()
        payload[field] = value
        yield payload
    for placeholder in ["password", "", "[DB_PASS_0]", "192.0.2.100", "synthetic-only"]:
        payload = valid_payload()
        payload["original_to_placeholder"] = {"synthetic-only": placeholder}
        payload["placeholder_to_original"] = {placeholder: "synthetic-only"}
        yield payload


@pytest.mark.parametrize("payload", list(invalid_payloads()))
def test_invalid_import_rejected_atomically(tmp_path, payload):
    vault = SessionVault()
    vault.get_or_create_placeholder("existing synthetic", "COMPANY")
    vault.record_hits(3)
    before = vault.snapshot_placeholders(), vault.total_intercepted_hits
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        vault.load_from_file(source)
    assert (vault.snapshot_placeholders(), vault.total_intercepted_hits) == before


@pytest.mark.parametrize("semantic", [False, True])
def test_exported_native_mappings_and_custom_categories_remain_compatible(tmp_path, semantic):
    vault = SessionVault()
    entries = [
        ("synthetic-only", "DB_PASS", "[DB_PASS_{index}]"),
        ("10.9.8.7", "PRIVATE_IP", "[PRIVATE_IP_{index}]"),
        ("8.8.8.8", "PUBLIC_IP", "[PUBLIC_IP_{index}]"),
        ("fake@fictional.test", "EMAIL", "[EMAIL_{index}]"),
        ("fake_operator", "USER_PATH", "[USER_PATH_{index}]"),
        ("00:11:22:33:44:55", "MAC_ADDR", "[MAC_{index}]"),
        ("fictional project", "内部_分类", "[{category}_{index}]"),
        ("fictional marker", "APSINDEX", "[{category}_{index}]"),
    ]
    for original, category, template in entries:
        vault.get_or_create_placeholder(original, category, template, semantic_ip_mode=semantic)
    path = tmp_path / "mapping.json"
    vault.save_to_file(path)
    loaded = SessionVault()
    loaded.load_from_file(path)
    assert loaded.snapshot_placeholders() == vault.snapshot_placeholders()
    assert loaded.get_or_create_placeholder("another synthetic", "DB_PASS") == "[DB_PASS_2]"


def test_string_counters_and_identical_live_import(tmp_path):
    payload = valid_payload()
    payload["category_counters"]["DB_PASS"] = "500"
    source = tmp_path / "mapping.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    vault = SessionVault()
    vault.load_from_file(source)
    vault.load_from_file(source)
    assert vault.size == 1
    assert vault.get_or_create_placeholder("another synthetic", "DB_PASS") == "[DB_PASS_501]"


def test_conflicting_live_import_preserves_existing_state(tmp_path):
    payload = valid_payload()
    payload["original_to_placeholder"]["new synthetic"] = "[COMPANY_1]"
    payload["placeholder_to_original"]["[COMPANY_1]"] = "new synthetic"
    payload["original_to_category"]["new synthetic"] = "COMPANY"
    source = tmp_path / "mapping.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    vault = SessionVault()
    vault.get_or_create_placeholder("existing synthetic", "DB_PASS")
    before = vault.snapshot_placeholders()
    with pytest.raises(ValueError):
        vault.load_from_file(source)
    assert vault.snapshot_placeholders() == before


@pytest.mark.parametrize("second_category", ["API_KEY", "api_key"])
def test_fuzzy_alias_imports_are_rejected_before_mutating_session(tmp_path, second_category):
    payload = {
        "original_to_placeholder": {"first synthetic": "<API_KEY_1>", "second synthetic": f"[{second_category}_1]"},
        "placeholder_to_original": {"<API_KEY_1>": "first synthetic", f"[{second_category}_1]": "second synthetic"},
        "original_to_category": {"first synthetic": "API_KEY", "second synthetic": second_category},
    }
    source = tmp_path / "ambiguous.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    vault = SessionVault()
    with pytest.raises(ValueError, match="aliases"):
        vault.load_from_file(source)
    assert vault.size == 0


def test_fuzzy_alias_conflict_with_live_session_is_rejected(tmp_path):
    vault = SessionVault()
    vault.get_or_create_placeholder("existing synthetic", "API_KEY", "<API_KEY_{index}>")
    source = tmp_path / "mapping.json"
    source.write_text(json.dumps({
        "original_to_placeholder": {"new synthetic": "[API_KEY_1]"},
        "placeholder_to_original": {"[API_KEY_1]": "new synthetic"},
        "original_to_category": {"new synthetic": "API_KEY"},
    }), encoding="utf-8")
    before = vault.snapshot_placeholders()
    with pytest.raises(ValueError, match="aliases"):
        vault.load_from_file(source)
    assert vault.snapshot_placeholders() == before


def test_missing_file_and_empty_legacy_vault_are_safe(tmp_path):
    vault = SessionVault()
    vault.load_from_file(tmp_path / "missing.json")
    source = tmp_path / "empty.json"
    source.write_text("{}", encoding="utf-8")
    vault.load_from_file(source)
    assert vault.size == 0


def test_placeholder_cannot_equal_original():
    vault = SessionVault()
    assert vault.get_or_create_placeholder("[COMPANY_1]", "COMPANY") == "[COMPANY_2]"
    with pytest.raises(ValueError, match="distinct"):
        vault.get_or_create_placeholder("fixed", "CUSTOM", template="fixed")


def test_invalid_import_cli_emits_no_text_and_preserves_files(tmp_path, monkeypatch, capsys):
    import io
    from src.main import main

    config = tmp_path / "config.json"
    example = tmp_path / "example.json"
    example.write_text(json.dumps({"custom_dictionary": {}}), encoding="utf-8")
    sanitizer = PrivacySanitizer(config, example)
    vault = tmp_path / "invalid.json"
    vault.write_text(json.dumps({"original_to_placeholder": {"synthetic-only": "synthetic-only"}}), encoding="utf-8")
    before = vault.read_bytes()
    monkeypatch.setattr(sys, "stdin", io.StringIO("password=synthetic-only"))
    assert main(["--stdin", "--vault-file", str(vault)], sanitizer) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "synthetic-only" not in captured.err
    assert vault.read_bytes() == before and sanitizer.vault.size == 0
