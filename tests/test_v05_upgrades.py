"""Regression tests for v0.3.2 -> v0.5.0 security fixes, GUI/Tray upgrades, Vault encryption, CLI, and Extension."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.main import SanitizerTrayApp, main as cli_main
from src.rules import (
    BUILTIN_RULES,
    RULE_PRESETS,
    SAMPLE_TEST_PAYLOAD,
    cn_id_valid,
    luhn_checksum_valid,
)
from src.sanitizer import (
    AI_PROMPT_HINTS,
    InputTooLargeError,
    MAX_SANITIZE_CHARS,
    PrivacySanitizer,
    SessionVault,
)
from src.vault_crypto import (
    ENVELOPE_MAGIC,
    ENVELOPE_VERSION,
    decrypt_vault_payload,
    encrypt_vault_payload,
    has_vault_crypto_support,
    is_encrypted_vault_payload,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_sanitizer(tmp_path: Path, extra_cfg: dict | None = None) -> PrivacySanitizer:
    cfg = tmp_path / "config.json"
    ex = tmp_path / "example.json"
    base = {"language": "en", "custom_dictionary": {}}
    if extra_cfg:
        base.update(extra_cfg)
    ex.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return PrivacySanitizer(cfg, ex)


# ==================== Milestone 1: Security & Engine Hardening ====================


def test_sample_payload_has_zero_leaks_and_roundtrips(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    res = sanitizer.sanitize(SAMPLE_TEST_PAYLOAD)
    for secret in (
        "R3disP@ssw0rd99",
        "ssw0rd99",
        "MyS3cretP@ss!",
        "Sup3rSecret99!",
        "2001:db8::8a2e:370:7334",
        "dXNlcjpzdXBlcl9zZWNyZXRfcGFzczk5",
        "alice_dev",
    ):
        assert secret not in res.sanitized_text, f"Leaked {secret!r} in sanitized sample"
    restored = sanitizer.restore(res.sanitized_text)
    assert restored.restored_text == SAMPLE_TEST_PAYLOAD


def test_db_uri_and_url_basic_auth_with_at_in_password(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    cases = [
        ("redis://:R3disP@ssw0rd99@192.168.10.45:6379/0", "R3disP@ssw0rd99", "redis://:"),
        ("postgres://db_admin:P@ss@word!9@10.0.0.5:5432/app", "P@ss@word!9", "postgres://db_admin:"),
        ("https://ci_bot:Tok@n!234@git.internal.local/repo.git", "Tok@n!234", "https://ci_bot:"),
    ]
    for raw, secret, expected_prefix in cases:
        res = sanitizer.sanitize(raw)
        assert secret not in res.sanitized_text
        assert "ssw0rd99" not in res.sanitized_text
        assert res.sanitized_text.startswith(expected_prefix)
        assert sanitizer.restore(res.sanitized_text).restored_text == raw


def test_compressed_ipv6_and_public_ipv4_zero_octet(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    raw = "ipv6=2001:db8::8a2e:370:7334 short=2001:db8::1 mapped=::ffff:192.0.2.128 gw=8.8.8.0"
    res = sanitizer.sanitize(raw)
    for token in ("2001:db8::8a2e:370:7334", "2001:db8::1", "::ffff:192.0.2.128", "8.8.8.0"):
        assert token not in res.sanitized_text
    assert ":7334" not in res.sanitized_text
    assert sanitizer.restore(res.sanitized_text).restored_text == raw


def test_http_basic_auth_and_pgp_private_key(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    raw = (
        "Authorization: Basic dXNlcjpzdXBlcl9zZWNyZXRfcGFzczk5\n"
        "-----BEGIN PGP PRIVATE KEY BLOCK-----\n"
        "lQOYBGdummyPGPkeyBody1234567890\n"
        "-----END PGP PRIVATE KEY BLOCK-----"
    )
    res = sanitizer.sanitize(raw)
    assert "dXNlcjpzdXBlcl9zZWNyZXRfcGFzczk5" not in res.sanitized_text
    assert "dummyPGPkeyBody" not in res.sanitized_text
    assert res.sanitized_text.startswith("Authorization: Basic <API_KEY_")
    assert "<PRIVATE_KEY_" in res.sanitized_text
    assert sanitizer.restore(res.sanitized_text).restored_text == raw


def test_user_file_path_trailing_free_and_unicode(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    raw = "HOME=/Users/alice_dev DOC=/Users/张三/report.txt WIN=C:\\Users\\bob_ops"
    res = sanitizer.sanitize(raw)
    for user in ("alice_dev", "张三", "bob_ops"):
        assert user not in res.sanitized_text
    assert "HOME=/Users/[USER_PATH_" in res.sanitized_text
    assert "/report.txt" in res.sanitized_text
    assert sanitizer.restore(res.sanitized_text).restored_text == raw


def test_kv_word_boundaries_and_query_string_stop_char(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    harmless = "compass=north bypass=true spin=fast highpass=300Hz"
    res_safe = sanitizer.sanitize(harmless)
    assert res_safe.sanitized_text == harmless
    assert res_safe.total_count == 0

    query = "https://example.org/v1/items?api_key=mysecret12345&page=2"
    res_q = sanitizer.sanitize(query)
    assert "mysecret12345" not in res_q.sanitized_text
    assert "&page=2" in res_q.sanitized_text
    assert sanitizer.restore(res_q.sanitized_text).restored_text == query


def test_cn_id_validator_and_amex_unionpay_cards(tmp_path: Path):
    # Valid GB 11643-1999 synthetic ID (11010519491231002X) vs invalid checksum & Feb 29 non-leap year
    assert cn_id_valid("11010519491231002X") is True
    assert cn_id_valid("110105194912310021") is False
    assert cn_id_valid("110101202302291234") is False

    # Synthetic Luhn-valid Amex (15 digits) and Mastercard 2-series (2221-2720)
    assert luhn_checksum_valid("378282246310005") is True
    assert luhn_checksum_valid("2223000048400011") is True

    sanitizer = _make_sanitizer(tmp_path)
    raw = "id=11010519491231002X bad=110105194912310021 amex=378282246310005 mc2=2223000048400011"
    res = sanitizer.sanitize(raw)
    assert "11010519491231002X" not in res.sanitized_text
    assert "110105194912310021" in res.sanitized_text  # invalid checksum not misclassified
    assert "378282246310005" not in res.sanitized_text
    assert "2223000048400011" not in res.sanitized_text
    assert sanitizer.restore(res.sanitized_text).restored_text == raw


def test_custom_word_ascii_whole_word_boundary(tmp_path: Path):
    sanitizer = _make_sanitizer(
        tmp_path,
        {"custom_dictionary": {"PROJECT": ["art", "星辰计划"]}, "custom_word_whole_word": True},
    )
    raw = "Start party for art and 星辰计划核心"
    res = sanitizer.sanitize(raw)
    assert "Start" in res.sanitized_text
    assert "party" in res.sanitized_text
    assert "for [PROJECT_" in res.sanitized_text
    assert "星辰计划" not in res.sanitized_text
    assert sanitizer.restore(res.sanitized_text).restored_text == raw

    # Disabling whole-word reverts to substring matching
    sanitizer.set_custom_word_whole_word(False)
    res_sub = sanitizer.sanitize("Start")
    assert "Start" not in res_sub.sanitized_text


def test_restore_enforces_max_input_length(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    with pytest.raises(InputTooLargeError):
        sanitizer.restore("x" * (MAX_SANITIZE_CHARS + 1))


def test_normalize_hotkeys_rejects_bare_keys_and_allows_function_keys():
    for bad in ("a", "space", "esc", "escape", "ctrl+"):
        with pytest.raises(ValueError):
            PrivacySanitizer.normalize_hotkeys(bad, "alt+r")
    assert PrivacySanitizer.normalize_hotkeys("F8", "Ctrl+Shift+R") == {
        "sanitize": "f8",
        "restore": "ctrl+shift+r",
    }
    assert PrivacySanitizer.normalize_hotkeys("Alt+S", "Alt+R") == {
        "sanitize": "alt+s",
        "restore": "alt+r",
    }


def test_validate_config_dict_and_dictionary_only_import(tmp_path: Path):
    validated = PrivacySanitizer.validate_config_dict(
        {
            "language": "zh",
            "theme": "light",
            "idle_wipe_minutes": 15,
            "custom_dictionary": {"COMPANY": ["Acme Corp"]},
            "unknown_future_option": {"keep": True},
        }
    )
    assert validated["unknown_future_option"] == {"keep": True}
    with pytest.raises(ValueError):
        PrivacySanitizer.validate_config_dict({"language": "fr"})
    with pytest.raises(ValueError):
        PrivacySanitizer.validate_config_dict({"hotkeys": {"sanitize": "a", "restore": "alt+r"}})

    sanitizer = _make_sanitizer(tmp_path, {"language": "en", "theme": "dark"})
    imp = tmp_path / "dict_only.json"
    imp.write_text(
        json.dumps(
            {
                "language": "zh",
                "theme": "light",
                "custom_dictionary": {"CLIENT": ["Imported Client"]},
            }
        ),
        encoding="utf-8",
    )
    sanitizer.import_config(imp, dictionary_only=True)
    # Language & theme preserved while dictionary merged/updated
    assert sanitizer.language == "en"
    assert sanitizer.theme == "dark"
    assert "Imported Client" in sanitizer.get_custom_dictionary()["CLIENT"]


def test_performance_500kb_log_and_unclosed_pem(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    line = "2026-01-01 INFO user=alice ip=10.20.30.40 msg=request completed ok status=200\n"
    payload = line * 6500  # ~500 KB
    t0 = time.perf_counter()
    res = sanitizer.sanitize(payload)
    elapsed = time.perf_counter() - t0
    assert res.total_count > 0
    assert elapsed < 3.0, f"500KB log took too long: {elapsed:.2f}s"

    unclosed_pem = "-----BEGIN RSA PRIVATE KEY-----\n" + ("A" * 500_000)
    t1 = time.perf_counter()
    res_pem = sanitizer.sanitize(unclosed_pem)
    elapsed_pem = time.perf_counter() - t1
    assert res_pem.sanitized_text == unclosed_pem
    assert elapsed_pem < 1.0, f"Unclosed 500KB PEM backtracked: {elapsed_pem:.2f}s"


# ==================== Milestone 2: Presets, Sandbox Isolation, Tray & Idle Wipe ====================


def test_rule_presets_and_active_counts(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    total = len(BUILTIN_RULES)
    active, reported_total = sanitizer.active_rule_counts()
    assert active == total and reported_total == total

    sanitizer.apply_rule_preset("dev")
    active_dev, _ = sanitizer.active_rule_counts()
    assert 0 < active_dev < total
    disabled = set(sanitizer.get_disabled_rules())
    assert set(RULE_PRESETS["dev"]).isdisjoint(disabled)

    sanitizer.apply_rule_preset("strict")
    assert sanitizer.get_disabled_rules() == []
    assert sanitizer.active_rule_counts() == (total, total)


def test_isolated_sandbox_vault_and_merge(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path)
    sandbox_vault = SessionVault()
    res = sanitizer.sanitize("secret_key=TopSecretSandbox99", vault=sandbox_vault)
    assert sanitizer.vault.size == 0
    assert sandbox_vault.size == 1
    assert sanitizer.restore(res.sanitized_text, vault=sandbox_vault).restored_text == "secret_key=TopSecretSandbox99"

    merged = sanitizer.vault.merge_from(sandbox_vault)
    assert merged == 1
    assert sanitizer.vault.size == 1
    assert sanitizer.restore(res.sanitized_text).restored_text == "secret_key=TopSecretSandbox99"


def test_merge_from_preserves_tag_style_and_avoids_alias_collisions(tmp_path: Path):
    pytest.importorskip("cryptography")
    sanitizer = _make_sanitizer(tmp_path)
    sanitizer.sanitize("api_key=PrimaryKey11111")  # <API_KEY_1>

    sandbox = SessionVault()
    sanitizer.sanitize("api_key=SandboxKey22222 api_key=SandboxKey33333", vault=sandbox)  # <API_KEY_1>, <API_KEY_2>

    merged = sanitizer.vault.merge_from(sandbox)
    assert merged == 2
    phs = sorted(ph for ph, _orig, _cat in sanitizer.vault.snapshot_placeholders())
    assert len(phs) == 3
    assert all(p.startswith("<API_KEY_") and p.endswith(">") for p in phs)

    vault_file = tmp_path / "merged.vault.json"
    sanitizer.vault.save_to_file(vault_file, passphrase="MergePass#2026")
    sanitizer.vault.clear()
    assert sanitizer.vault.size == 0
    sanitizer.vault.load_from_file(vault_file, passphrase="MergePass#2026")
    assert sanitizer.vault.size == 3


def test_tray_states_idle_wipe_zero_restore_and_copy_to_clipboard(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path, {"idle_wipe_minutes": 1})
    app = SanitizerTrayApp(sanitizer=sanitizer)
    assert app._compute_tray_state() == "ready"

    sanitizer.sanitize("token=AlphaSecret99")
    assert app._compute_tray_state() == "vault"

    sanitizer.set_auto_sanitize_clipboard(True)
    assert app._compute_tray_state() == "cruise"
    sanitizer.set_auto_sanitize_clipboard(False)

    # Zero-restore must NOT emit the "original data restored" warning
    notices: list[tuple[str, str]] = []
    app.notify = lambda msg, tone="info": notices.append((msg, tone))
    with patch("src.main._safe_clipboard_paste", return_value="harmless text without placeholders"):
        app.restore_clipboard()
    assert notices
    assert "original values" not in notices[-1][0].lower()
    assert notices[-1][1] == "info"

    # copy_to_clipboard records _last_written_clipboard to avoid cruise re-triggering
    with patch("src.main._safe_clipboard_copy") as mock_copy:
        ok = app.copy_to_clipboard("copied-sanitized-text")
    assert ok is True
    assert app._last_written_clipboard == "copied-sanitized-text"
    mock_copy.assert_called_once_with("copied-sanitized-text")

    # Idle auto-wipe triggers once elapsed >= idle_wipe_minutes * 60
    assert sanitizer.vault.size == 1
    app._last_activity_ts = time.monotonic() - 120
    app._check_idle_wipe()
    assert sanitizer.vault.size == 0


# ==================== Milestone 3: AI Hint, Encrypted Vault, CLI & Browser Extension ====================


def test_ai_prompt_hint_prepend_and_lossless_restore(tmp_path: Path):
    sanitizer = _make_sanitizer(tmp_path, {"language": "zh", "ai_prompt_hint": True})
    raw = "Connect to 10.9.8.7 with password=HintSecret88"
    san = sanitizer.sanitize(raw)
    assert san.sanitized_text.startswith(AI_PROMPT_HINTS["zh"])
    assert "HintSecret88" not in san.sanitized_text
    res = sanitizer.restore(san.sanitized_text)
    assert res.restored_text == raw

    # English hint stripping also works
    sanitizer.set_language("en")
    san_en = sanitizer.sanitize(raw)
    assert san_en.sanitized_text.startswith(AI_PROMPT_HINTS["en"])
    assert sanitizer.restore(san_en.sanitized_text).restored_text == raw


def test_encrypted_vault_envelope_detection_and_roundtrip(tmp_path: Path):
    assert is_encrypted_vault_payload({ENVELOPE_MAGIC: ENVELOPE_VERSION}) is True
    assert is_encrypted_vault_payload({"placeholder_to_original": {}}) is False

    pytest.importorskip("cryptography")
    assert has_vault_crypto_support() is True

    payload = {"placeholder_to_original": {"<API_KEY_1>": "sk-test-secret-1234567890"}}
    envelope = encrypt_vault_payload(payload, "StrongPass#2026")
    assert is_encrypted_vault_payload(envelope) is True
    assert "sk-test-secret-1234567890" not in json.dumps(envelope)
    assert decrypt_vault_payload(envelope, "StrongPass#2026") == payload

    # Wrong passphrase rejected
    with pytest.raises(ValueError):
        decrypt_vault_payload(envelope, "WrongPass#2026")

    # Tampered ciphertext rejected
    tampered = dict(envelope)
    tampered["ciphertext"] = "A" + envelope["ciphertext"][1:]
    with pytest.raises(ValueError):
        decrypt_vault_payload(tampered, "StrongPass#2026")

    # Excessive Scrypt cost rejected against DoS
    dos_env = dict(envelope)
    dos_env["kdf_params"] = {"n": 2**24, "r": 8, "p": 1}
    with pytest.raises(ValueError):
        decrypt_vault_payload(dos_env, "StrongPass#2026")


def test_cli_file_and_restore_file_with_encrypted_vault(tmp_path: Path, monkeypatch):
    pytest.importorskip("cryptography")
    raw_file = tmp_path / "app.env"
    san_file = tmp_path / "app.sanitized.env"
    restored_file = tmp_path / "app.restored.env"
    vault_file = tmp_path / "vault.enc.json"
    raw_text = "DB_URL=postgres://ops:TopSecret@123@10.2.3.4:5432/prod\n"
    raw_file.write_text(raw_text, encoding="utf-8")

    monkeypatch.setenv("TEST_VAULT_PASS", "VaultKey#999")
    s1 = _make_sanitizer(tmp_path)
    code1 = cli_main(
        [
            "--file", str(raw_file),
            "--output", str(san_file),
            "--vault-file", str(vault_file),
            "--encrypt",
            "--passphrase-env", "TEST_VAULT_PASS",
        ],
        sanitizer=s1,
    )
    assert code1 == 0
    assert "TopSecret@123" not in san_file.read_text(encoding="utf-8")
    vault_raw = vault_file.read_text(encoding="utf-8")
    assert "TopSecret@123" not in vault_raw
    assert ENVELOPE_MAGIC in vault_raw

    # Wrong passphrase fails closed with status 2 and creates no output file
    monkeypatch.setenv("TEST_VAULT_PASS", "WrongVaultKey")
    s_bad = _make_sanitizer(tmp_path)
    code_bad = cli_main(
        [
            "--restore-file", str(san_file),
            "--output", str(restored_file),
            "--vault-file", str(vault_file),
            "--passphrase-env", "TEST_VAULT_PASS",
        ],
        sanitizer=s_bad,
    )
    assert code_bad == 2
    assert not restored_file.exists()

    # Correct passphrase restores losslessly
    monkeypatch.setenv("TEST_VAULT_PASS", "VaultKey#999")
    s2 = _make_sanitizer(tmp_path)
    code2 = cli_main(
        [
            "--restore-file", str(san_file),
            "--output", str(restored_file),
            "--vault-file", str(vault_file),
            "--passphrase-env", "TEST_VAULT_PASS",
        ],
        sanitizer=s2,
    )
    assert code2 == 0
    assert restored_file.read_text(encoding="utf-8") == raw_text


def test_cli_stdin_to_output_file(tmp_path: Path, monkeypatch):
    out_file = tmp_path / "pipe.sanitized.txt"
    monkeypatch.setattr(sys, "stdin", io.StringIO("Authorization: Basic dXNlcjpzdXBlcl9zZWNyZXRfcGFzczk5"))
    s = _make_sanitizer(tmp_path)
    code = cli_main(["--stdin", "--output", str(out_file)], sanitizer=s)
    assert code == 0
    out_text = out_file.read_text(encoding="utf-8")
    assert "dXNlcjpzdXBlcl9zZWNyZXRfcGFzczk5" not in out_text
    assert "<API_KEY_1>" in out_text


def test_cross_platform_rule_parity_script():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "sync_web_rules.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "OK:" in proc.stdout


def test_browser_extension_manifest_zero_permissions_and_core_roundtrip():
    ext_dir = REPO_ROOT / "browser-extension"
    manifest = json.loads((ext_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["permissions"] == []
    assert "host_permissions" not in manifest
    for js_file in ("sanitizer_core.js", "content.js", "popup.js"):
        src_text = (ext_dir / js_file).read_text(encoding="utf-8")
        assert "localStorage" not in src_text
        assert "fetch(" not in src_text
        assert "XMLHttpRequest" not in src_text

    # Execute sanitizer_core.js in Node and assert sanitize + fuzzy restore roundtrip
    node_check = (
        "const fs = require('fs'), vm = require('vm');"
        "const code = fs.readFileSync(process.argv[1], 'utf8');"
        "const ctx = vm.createContext({ globalThis: {} }); ctx.globalThis = ctx;"
        "vm.runInContext(code, ctx);"
        "const eng = ctx.SanitizerExtCore.createSessionEngine();"
        "const raw = 'redis://:R3disP@ssw0rd99@10.0.0.1:6379/0 Authorization: Basic dXNlcjpzdXBlcl9zZWNyZXRfcGFzczk5';"
        "const s = eng.sanitize(raw);"
        "if (s.text.includes('R3disP@ssw0rd99') || s.text.includes('dXNlcjpzdXBlcl9zZWNyZXRfcGFzczk5')) process.exit(1);"
        "const r = eng.restore(s.text);"
        "if (r.text !== raw) process.exit(2);"
        "process.stdout.write('EXT_OK');"
    )
    proc = subprocess.run(
        ["node", "-e", node_check, str(ext_dir / "sanitizer_core.js")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "EXT_OK"


def test_gui_esc_cancels_hotkey_recording_and_sandbox_right_click_allowlist(tmp_path: Path):
    import tkinter as tk
    import customtkinter as ctk
    from src.gui import _ModernControlCenter, _StableCTk

    sanitizer = _make_sanitizer(tmp_path)
    ctk.set_appearance_mode("Dark")
    try:
        root = _StableCTk()
    except tk.TclError as exc:
        if "display" in str(exc).lower():
            pytest.skip("Tk display unavailable")
        raise
    root.withdraw()
    try:
        win = _ModernControlCenter(root, sanitizer)
        root.update_idletasks()

        # Esc cancels hotkey recording cleanly
        win._start_hotkey_recording("sanitize")
        assert win._recording_target == "sanitize"
        win._on_hotkey_keypress(SimpleNamespace(keysym="Escape", state=0))
        assert win._recording_target is None

        # Sandbox isolated vault + right-click allowlist + sync to global vault
        win.sandbox_input.delete("1.0", "end")
        win.sandbox_input.insert("1.0", "ip=10.55.66.77 token=SandboxSecret99")
        win._run_sandbox_sanitize()
        assert sanitizer.vault.size == 0
        assert win._sandbox_vault.size == 2

        # Sync to global vault
        win._sync_sandbox_to_global_vault()
        assert sanitizer.vault.size == 2

        # Right-click allowlist on placeholder resolves original & unmasks in sandbox
        ph_ip = next(ph for ph, orig, _cat in win._sandbox_vault.snapshot_placeholders() if orig == "10.55.66.77")
        resolved_orig = win._sandbox_vault.lookup_original(ph_ip)
        assert resolved_orig == "10.55.66.77"
        win._allowlist_from_sandbox_tag(resolved_orig)
        assert "10.55.66.77" in sanitizer.get_allowlist()
        assert "10.55.66.77" in win.sandbox_output.get("1.0", "end")
    finally:
        for timer in root.tk.splitlist(root.tk.call("after", "info")):
            root.tk.call("after", "cancel", timer)
        root.destroy()
