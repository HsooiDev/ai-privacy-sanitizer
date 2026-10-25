"""Unit tests for ai-privacy-sanitizer verifying sanitization, consistency, semantic IPs, GUI dictionary CRUD, and 100% restoration."""

import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src.gui import _ModernControlCenter
from src.main import SanitizerTrayApp, create_shield_lock_icon, export_shield_ico, main
from src.rules import SAMPLE_TEST_PAYLOAD, luhn_checksum_valid, my_nric_valid
from src.sanitizer import PrivacySanitizer


@pytest.fixture()
def temp_config_dir(tmp_path: Path):
    example_cfg = {
        "semantic_ip_mode": False,
        "auto_sanitize_clipboard": False,
        "hotkeys": {"sanitize": "alt+s", "restore": "alt+r"},
        "custom_dictionary": {
            "COMPANY": [
                "Acme Global",
                "Acme Global Technologies Sdn Bhd",
                "星辰科技",
                "星辰未来科技有限公司",
            ],
            "CLIENT": [
                "MegaCorp",
                "MegaCorp Bank Berhad",
            ],
            "PROJECT": [
                "Project-Hyperion",
                "Project-Hyperion-V2",
            ],
            "CUSTOM_SECRET": [
                "INTERNAL-DEPLOY-PASSPHRASE-9981",
            ],
        },
    }
    example_path = tmp_path / "config.example.json"
    config_path = tmp_path / "config.json"
    example_path.write_text(json.dumps(example_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path, example_path


def test_auto_create_config_from_example(temp_config_dir):
    config_path, example_path = temp_config_dir
    assert not config_path.exists()
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)
    assert config_path.exists()
    assert sanitizer.semantic_ip_mode is False
    assert sanitizer.auto_sanitize_clipboard is False


def test_layer1_longest_match_first_priority(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    raw = (
        "Vendor: Acme Global Technologies Sdn Bhd (short: Acme Global). "
        "Code: Project-Hyperion-V2 upgraded from Project-Hyperion."
    )
    res = sanitizer.sanitize(raw)

    assert "Technologies Sdn Bhd" not in res.sanitized_text
    assert "-V2" not in res.sanitized_text
    assert "[COMPANY_1]" in res.sanitized_text
    assert "[COMPANY_2]" in res.sanitized_text
    assert "[PROJECT_1]" in res.sanitized_text
    assert "[PROJECT_2]" in res.sanitized_text

    restored = sanitizer.restore(res.sanitized_text)
    assert restored.restored_text == raw


def test_session_consistency_same_email_five_times(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    raw = (
        "1: boss@client-a.com\n"
        "2: boss@client-a.com\n"
        "3: boss@client-a.com\n"
        "4: boss@client-a.com\n"
        "5: boss@client-a.com\n"
        "Other: second@client-b.org"
    )
    res = sanitizer.sanitize(raw)

    assert res.sanitized_text.count("[EMAIL_1]") == 5
    assert res.sanitized_text.count("[EMAIL_2]") == 1
    assert "boss@client-a.com" not in res.sanitized_text
    assert "second@client-b.org" not in res.sanitized_text
    assert res.category_counts["EMAIL"] == 6

    restored = sanitizer.restore(res.sanitized_text)
    assert restored.restored_text == raw
    assert restored.restored_count == 6


def test_layer2_api_keys_db_uris_pem_ips_and_pii(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    san_res = sanitizer.sanitize(SAMPLE_TEST_PAYLOAD)
    sanitized = san_res.sanitized_text

    forbidden_substrings = [
        "Acme Global",
        "MegaCorp",
        "Project-Hyperion",
        "boss@client-a.com",
        "ops@megacorp.com.my",
        "Sup3rS3cretDB!2026",
        "R3disP@ssw0rd99",
        "WebhookPass!99",
        "UnquotedEnvSecretPass!88",
        "MyLocalRootPassword#88",
        "custom_internal_api_token_abcdef123456",
        "sk-proj-abc123XYZ789def456GHI012jkl345MNO678",
        "ghp_1234567890abcdefABCDEF1234567890abcd",
        "AKIAIOSFODNN7EXAMPLE",
        "AIzaSyDa1234567890abcdefABCDEF123456789",
        "xoxb-123456789012-1234567890123-abcdefghijklmnopqrstuvwx",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
        "BEGIN RSA PRIVATE KEY",
        "MIIEpAIBAAKCAQEA0123456789abcdefABCDEF",
        "10.52.18.9",
        "192.168.10.45",
        "172.20.0.15",
        "8.8.8.8",
        "00:1A:2B:3C:4D:5E",
        "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        "12-345 6789",
        "011-2345 6789",
        "900307-14-5521",
        "A12345678",
        "123123",
        "asdasd",
    ]
    for secret in forbidden_substrings:
        assert secret not in sanitized, f"Secret leaked in sanitized text: {secret}"

    assert "postgres://dbadmin:[DB_PASS_1]@[PRIVATE_IP_1]:5432/hyperion_prod" in sanitized
    assert "https://deploy_user:[DB_PASS_3]@internal.api.org.my/v1/hook" in sanitized
    assert "<PRIVATE_KEY_1>" in sanitized
    assert "<API_KEY_1>" in sanitized

    restored = sanitizer.restore(sanitized)
    assert restored.restored_text == SAMPLE_TEST_PAYLOAD


def test_semantic_ip_mode_and_restoration(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)
    sanitizer.set_semantic_ip_mode(True)
    assert sanitizer.semantic_ip_mode is True

    raw = (
        "Connect from private 10.52.18.9 and 192.168.1.20 to public 8.8.8.8 "
        "(retry 10.52.18.9) using key sk-proj-1234567890abcdef1234567890 for MegaCorp."
    )
    san_res = sanitizer.sanitize(raw)

    assert san_res.sanitized_text.count("192.0.2.101") == 2
    assert "192.0.2.102" in san_res.sanitized_text
    assert "203.0.113.101" in san_res.sanitized_text
    assert "<API_KEY_1>" in san_res.sanitized_text
    assert "[CLIENT_1]" in san_res.sanitized_text

    ai_reply = (
        "Please update firewall rule on 192.0.2.101 and 203.0.113.101 "
        "for client [CLIENT_1] with token <API_KEY_1>."
    )
    res_res = sanitizer.restore(ai_reply)
    assert res_res.restored_text == (
        "Please update firewall rule on 10.52.18.9 and 8.8.8.8 "
        "for client MegaCorp with token sk-proj-1234567890abcdef1234567890."
    )
    assert res_res.restored_count == 4


def test_dictionary_crud_and_import_export(temp_config_dir, tmp_path: Path):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    assert sanitizer.add_custom_word("COMPANY", "新星量子计算有限公司") is True
    assert sanitizer.add_custom_word("COMPANY", "新星量子计算有限公司") is False  # Duplicate rejected
    assert "新星量子计算有限公司" in sanitizer.get_custom_dictionary()["COMPANY"]

    backup_file = tmp_path / "backup.json"
    sanitizer.export_config(backup_file)
    assert backup_file.exists()

    assert sanitizer.remove_custom_word("COMPANY", "新星量子计算有限公司") is True
    assert "新星量子计算有限公司" not in sanitizer.get_custom_dictionary()["COMPANY"]

    sanitizer.import_config(backup_file)
    assert "新星量子计算有限公司" in sanitizer.get_custom_dictionary()["COMPANY"]


def test_shield_lock_icon_and_ico_export(tmp_path: Path):
    img = create_shield_lock_icon(64)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"

    ico_path = export_shield_ico(tmp_path / "icon.ico")
    assert ico_path.exists()
    assert ico_path.stat().st_size > 100


def test_unquoted_env_secrets_and_case_insensitive_dictionary(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    raw = (
        "company_lower: acme global\n"
        "DB_PASSWORD=PlainTextEnvPassword2026!\n"
        "CUSTOM_API_KEY=unquoted_env_api_secret_token_998877\n"
    )
    san_res = sanitizer.sanitize(raw)
    assert "acme global" not in san_res.sanitized_text
    assert "PlainTextEnvPassword2026!" not in san_res.sanitized_text
    assert "unquoted_env_api_secret_token_998877" not in san_res.sanitized_text
    assert "[COMPANY_1]" in san_res.sanitized_text
    assert "DB_PASSWORD=[DB_PASS_1]" in san_res.sanitized_text
    assert "CUSTOM_API_KEY=<API_KEY_1>" in san_res.sanitized_text

    restored = sanitizer.restore(san_res.sanitized_text)
    assert restored.restored_text == raw


def test_shorthand_variants_id_pass_pw_ic_hp_and_json(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    raw = (
        "pass = abcd\n"
        "pw = 1234\n"
        "id = abc1234\n"
        "uid = user_kl_88\n"
        "sk = secret_val_9988\n"
        "ic = 900307145521\n"
        "hp = 0123456789\n"
        '{"pass": "json_pass_123", "id": "json_id_456", "token": "json_tok_7890"}\n'
        "curl -u admin:cli_secret_pw https://api.example.com\n"
    )
    san_res = sanitizer.sanitize(raw)
    out = san_res.sanitized_text

    assert "pass = [DB_PASS_3]" in out
    assert "pw = [DB_PASS_4]" in out
    assert "id = [USER_ID_2]" in out
    assert "uid = [USER_ID_3]" in out
    assert "sk = <API_KEY_2>" in out
    assert "ic = [ID_CARD_1]" in out
    assert "hp = [PHONE_1]" in out
    assert '"pass": "[DB_PASS_2]"' in out
    assert '"id": "[USER_ID_1]"' in out
    assert '"token": "<API_KEY_1>"' in out
    assert "curl -u admin:[DB_PASS_1]" in out

    restored = sanitizer.restore(out)
    assert restored.restored_text == raw


def test_chinese_key_value_and_hyphen_separators(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    raw = (
        "密码-123123\n"
        "账号=asdasd\n"
        "密码：888888\n"
        "登录密码 是 mySecretPass99\n"
        "用户名-admin_kl_01\n"
        "户口=user_acc_7788\n"
        "身份证-900307145521\n"
        "手机号=0123456789\n"
        "银行卡号：6222021234567890\n"
        "密钥=zh_secret_token_9988\n"
        "pass-123123\n"
        "id-abc1234\n"
    )
    san_res = sanitizer.sanitize(raw)
    out = san_res.sanitized_text

    assert "123123" not in out
    assert "asdasd" not in out
    assert "888888" not in out
    assert "mySecretPass99" not in out
    assert "admin_kl_01" not in out
    assert "user_acc_7788" not in out
    assert "900307145521" not in out
    assert "0123456789" not in out
    assert "6222021234567890" not in out
    assert "zh_secret_token_9988" not in out
    assert "abc1234" not in out

    assert "密码-[DB_PASS_1]" in out
    assert "账号=[USER_ID_1]" in out
    assert "密码：[DB_PASS_2]" in out
    assert "登录密码 是 [DB_PASS_3]" in out
    assert "用户名-[USER_ID_2]" in out
    assert "户口=[USER_ID_3]" in out
    assert "身份证-[ID_CARD_1]" in out
    assert "手机号=[PHONE_1]" in out
    assert "银行卡号：[BANK_CARD_1]" in out
    assert "密钥=<API_KEY_1>" in out
    assert "pass-[DB_PASS_1]" in out  # Same '123123' reuses [DB_PASS_1]
    assert "id-[USER_ID_4]" in out

    restored = sanitizer.restore(out)
    assert restored.restored_text == raw


def test_custom_hotkeys_quoted_spaces_odbc_and_webhooks(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    updated_hk = sanitizer.set_hotkeys("Ctrl+Shift+S", "Ctrl+Shift+R")
    assert updated_hk == {"sanitize": "ctrl+shift+s", "restore": "ctrl+shift+r"}
    assert sanitizer.hotkeys == {"sanitize": "ctrl+shift+s", "restore": "ctrl+shift+r"}

    with pytest.raises(ValueError):
        sanitizer.set_hotkeys("alt+s", "alt+s")

    raw = (
        'password = "my secret password 2026"\n'
        '密码 = "中文 空格 密码 888"\n'
        '账号 = "john doe kl"\n'
        "Server=myserver;Database=mydb;User Id=sa_admin;Password=MyOdbcPass!99;\n"
        "https://discord.com/api/webhooks/1234567890/abcdef1234567890_discord_webhook_secret\n"
    )
    san_res = sanitizer.sanitize(raw)
    out = san_res.sanitized_text

    assert "my secret password 2026" not in out
    assert "中文 空格 密码 888" not in out
    assert "john doe kl" not in out
    assert "sa_admin" not in out
    assert "MyOdbcPass!99" not in out
    assert "abcdef1234567890_discord_webhook_secret" not in out

    assert 'password = "[DB_PASS_2]"' in out
    assert '密码 = "[DB_PASS_1]"' in out
    assert '账号 = "[USER_ID_1]"' in out
    assert "User Id=[USER_ID_2];Password=[DB_PASS_3];" in out

    restored = sanitizer.restore(out)
    assert restored.restored_text == raw


def test_luhn_bank_card_and_my_nric_validators(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    # Valid Luhn Visa card vs invalid 16-digit order number starting with 4111
    assert luhn_checksum_valid("4111 1111 1111 1111") is True
    assert luhn_checksum_valid("4111 1111 1111 1112") is False

    # Valid MY NRIC (PB=14 KL) vs invalid PB=00 or PB=97
    assert my_nric_valid("900307-14-5521") is True
    assert my_nric_valid("900307-00-5521") is False
    assert my_nric_valid("900307-97-5521") is False

    raw = (
        "Valid Card: 4111-1111-1111-1111\n"
        "Fake Order Number: 4111-1111-1111-1112\n"
        "Valid NRIC: 900307-14-5521\n"
        "Invalid NRIC PB: 900307-00-5521\n"
    )
    res = sanitizer.sanitize(raw)
    assert "4111-1111-1111-1111" not in res.sanitized_text
    assert "[BANK_CARD_1]" in res.sanitized_text
    assert "4111-1111-1111-1112" in res.sanitized_text  # Not falsely masked!
    assert "900307-14-5521" not in res.sanitized_text
    assert "[ID_CARD_1]" in res.sanitized_text
    assert "900307-00-5521" in res.sanitized_text  # Invalid PB skipped!


def test_user_file_path_and_new_cloud_tokens(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    raw = (
        r"WinPath: C:\Users\dev_account\Documents\project\secret.py" + "\n"
        r"PublicPath: C:\Users\Public\Documents\readme.txt" + "\n"
        "MacPath: /Users/workstation_01/workspace/config.yaml\n"
        "LinuxPath: /home/srv_operator/.ssh/authorized_keys\n"
        "UbuntuSys: /home/ubuntu/server.js\n"
        "DO_TOKEN=dop_v1_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "SUPABASE=sbp_0123456789abcdef0123456789abcdef01234567\n"
        "AZURE_BLOB=https://myaccount.blob.core.windows.net/container/file.txt?sv=2022-11-02&sig=AbCdEfGhIjKlMnOpQrStUvWxYz0123456789%2B%3D\n"
    )
    res = sanitizer.sanitize(raw)
    out = res.sanitized_text

    assert "dev_account" not in out
    assert "workstation_01" not in out
    assert "srv_operator" not in out
    assert r"C:\Users\[USER_PATH_1]\Documents\project\secret.py" in out
    assert r"C:\Users\Public\Documents\readme.txt" in out
    assert "/Users/[USER_PATH_2]/workspace/config.yaml" in out
    assert "/home/[USER_PATH_3]/.ssh/authorized_keys" in out
    assert "/home/ubuntu/server.js" in out
    assert "dop_v1_" not in out
    assert "sbp_" not in out
    assert "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789%2B%3D" not in out

    restored = sanitizer.restore(out)
    assert restored.restored_text == raw


def test_allowlist_and_disabled_rules_and_semantic_extensions(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    assert sanitizer.add_allowlist_item("safe@company.com") is True
    sanitizer.set_rule_enabled("mac_address", False)

    raw = "Email1: safe@company.com, Email2: real_boss@company.com, MAC: 00:1A:2B:3C:4D:5E, Path: /Users/local_profile/app.py"
    sanitizer.set_semantic_ip_mode(True)
    res = sanitizer.sanitize(raw)
    out = res.sanitized_text

    # safe@company.com is allowlisted; MAC rule is disabled
    assert "safe@company.com" in out
    assert "00:1A:2B:3C:4D:5E" in out
    # real_boss@company.com and local_profile use semantic placeholders
    assert "user1@example.com" in out
    assert "/Users/dev_user_1/app.py" in out

    restored = sanitizer.restore(out)
    assert restored.restored_text == raw


def test_two_stage_fuzzy_and_case_insensitive_restore(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    raw = "key=sk-proj-1234567890abcdef1234567890 company=Acme Global"
    san = sanitizer.sanitize(raw)
    assert "<API_KEY_1>" in san.sanitized_text
    assert "[COMPANY_1]" in san.sanitized_text

    # Simulate AI response that mutates <API_KEY_1> and [COMPANY_1] into various formats
    ai_mutated_reply = (
        "1. Bracket changed: [API_KEY_1]\n"
        "2. Backtick wrapped: `API_KEY_1`\n"
        "3. Lowercase: <api_key_1>\n"
        "4. HTML entity: &lt;API_KEY_1&gt;\n"
        "5. Curly braces: {COMPANY_1}\n"
    )
    restored = sanitizer.restore(ai_mutated_reply)
    expected = (
        "1. Bracket changed: sk-proj-1234567890abcdef1234567890\n"
        "2. Backtick wrapped: sk-proj-1234567890abcdef1234567890\n"
        "3. Lowercase: sk-proj-1234567890abcdef1234567890\n"
        "4. HTML entity: sk-proj-1234567890abcdef1234567890\n"
        "5. Curly braces: Acme Global\n"
    )
    assert restored.restored_text == expected
    assert restored.restored_count == 5


def test_undo_stack_and_vault_secret_masking(temp_config_dir):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)
    app = SanitizerTrayApp(sanitizer=sanitizer)

    for i in range(7):
        app._push_undo_snapshot(f"raw_payload_{i}")

    # Stack caps at max 5 snapshots
    assert len(app._clipboard_undo_stack) == 5
    assert app._clipboard_undo_stack[-1] == "raw_payload_6"

    app.clear_session_map()
    assert len(app._clipboard_undo_stack) == 0
    assert app.gui._cmd_queue.get_nowait() == "REFRESH"

    assert _ModernControlCenter._mask_secret("1234") == "••••"
    assert _ModernControlCenter._mask_secret("abcd12") == "a••••2"
    masked = _ModernControlCenter._mask_secret_preview("sk-proj-abc123XYZ789def456GHI012jkl345MNO678")
    assert masked == "sk-••••••78"
    assert "abc123XYZ789" not in masked


def test_cli_stdin_restore_stdin_and_file_arguments(temp_config_dir, monkeypatch, capsys, tmp_path):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    raw_text = "CLI test: OPENAI_API_KEY=sk-proj-1234567890abcdef1234567890 and 密码-cliSecret88"

    # 1. Test --stdin
    monkeypatch.setattr("sys.stdin", io.StringIO(raw_text))
    code = main(["--stdin"], sanitizer=sanitizer)
    captured = capsys.readouterr()
    assert code == 0
    assert "<API_KEY_1>" in captured.out
    assert "[DB_PASS_1]" in captured.out
    assert "sk-proj-1234567890abcdef1234567890" not in captured.out
    assert "API_KEY: 1" in captured.err

    # 2. Test --restore-stdin using the same in-memory sanitizer vault
    monkeypatch.setattr("sys.stdin", io.StringIO(captured.out))
    code_restore = main(["--restore-stdin"], sanitizer=sanitizer)
    captured_restore = capsys.readouterr()
    assert code_restore == 0
    assert captured_restore.out == raw_text

    # 3. Test --file and --output
    in_file = tmp_path / "input_log.txt"
    out_file = tmp_path / "sanitized_log.txt"
    in_file.write_text(raw_text, encoding="utf-8")

    code_file = main(["--file", str(in_file), "--output", str(out_file)], sanitizer=sanitizer)
    assert code_file == 0
    file_out = out_file.read_text(encoding="utf-8")
    assert "<API_KEY_1>" in file_out
    assert "[DB_PASS_1]" in file_out
    assert "cliSecret88" not in file_out


def test_web_single_file_edition_integrity():
    web_path = Path(__file__).resolve().parent.parent / "web" / "index.html"
    assert web_path.exists()
    html = web_path.read_text(encoding="utf-8")

    # Verify required functions and rules are present in web/index.html
    assert "function isValidLuhn(" in html
    assert "function isValidMyNric(" in html
    assert "USER_PATH" in html
    assert "__WEB_RES_FUZZY_" in html
    assert "function toggleVaultMask(" in html
    assert "function toggleDiffPreview(" in html
    assert "allowlistItems" in html
    # Ensure zero storage APIs are invoked
    assert "localStorage." not in html
    assert "sessionStorage." not in html
    assert "document.cookie" not in html


def test_v031_nric_dates_stage2_boundary_and_vault_file(temp_config_dir, monkeypatch, capsys, tmp_path):
    config_path, example_path = temp_config_dir
    sanitizer = PrivacySanitizer(config_path=config_path, example_config_path=example_path)

    # 1. LICENSE, spec, and icon files exist
    root_dir = Path(__file__).resolve().parent.parent
    license_path = root_dir / "LICENSE"
    assert license_path.exists()
    assert "MIT License" in license_path.read_text(encoding="utf-8")
    assert (root_dir / "AI-Privacy-Sanitizer.spec").exists()
    assert (root_dir / "assets" / "icon.ico").exists()

    # Verify GitLab token & sentinel spoofing immunity
    spoof_res = sanitizer.sanitize("GITLAB=glpat-1234567890abcdef123456 \x00\x01__SAN_PH_1__\x01\x00")
    assert "glpat-" not in spoof_res.sanitized_text
    assert "<API_KEY_1>" in spoof_res.sanitized_text

    # 2. Strict calendar days per month in my_nric_valid & 12-digit timestamp immunity
    assert my_nric_valid("900231-14-5521") is False  # Feb 31 is invalid
    assert my_nric_valid("900431-14-5521") is False  # Apr 31 is invalid
    assert my_nric_valid("900229-14-5521") is True   # Feb 29 is valid

    ts_res = sanitizer.sanitize("OrderTimestamp: 261024081234 InvalidDateIC: 900231-14-5521")
    assert "261024081234" in ts_res.sanitized_text
    assert "900231-14-5521" in ts_res.sanitized_text

    # 3. Stage 2 Fuzzy Restore boundary: semantic unbracketed values are strictly case-sensitive in Stage 1
    sanitizer.set_semantic_ip_mode(True)
    sem_res = sanitizer.sanitize("Path: /Users/local_profile/app.py")
    assert "/Users/dev_user_1/app.py" in sem_res.sanitized_text

    # Uppercase constant DEV_USER_1 in code must NOT be overwritten by Stage 2
    code_snippet = "const DEV_USER_1 = 'constant'; path = '/Users/dev_user_1/app.py';"
    restored_sem = sanitizer.restore(code_snippet)
    assert "const DEV_USER_1 = 'constant';" in restored_sem.restored_text
    assert "path = '/Users/local_profile/app.py';" in restored_sem.restored_text

    # 4. CLI --vault-file cross-process sanitization and restoration
    vault_file = tmp_path / "cli_vault.json"
    raw_cli = "SECRET_TOKEN=sk-proj-9876543210abcdef9876543210"
    sanitizer_proc1 = PrivacySanitizer(config_path=config_path, example_config_path=example_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(raw_cli))
    assert main(["--stdin", "--vault-file", str(vault_file)], sanitizer=sanitizer_proc1) == 0
    san_out = capsys.readouterr().out
    assert "<API_KEY_1>" in san_out
    assert vault_file.exists()

    # Second separate sanitizer instance restores using --vault-file
    sanitizer_proc2 = PrivacySanitizer(config_path=config_path, example_config_path=example_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(san_out))
    assert main(["--restore-stdin", "--vault-file", str(vault_file)], sanitizer=sanitizer_proc2) == 0
    res_out = capsys.readouterr().out
    assert res_out == raw_cli
