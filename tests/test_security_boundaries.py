"""Focused synthetic regressions for the APS remediation boundaries (no visual checks)."""

import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import main as app_module
from src.gui import _ModernControlCenter, _StableCTk
from src.main import SanitizerTrayApp, main
from src.sanitizer import InputTooLargeError, MAX_SANITIZE_CHARS, PrivacySanitizer, SessionVault
from src.secure_io import atomic_write_private


@pytest.fixture
def sanitizer(tmp_path):
    template = tmp_path / "example.json"
    template.write_text(json.dumps({"language": "en", "custom_dictionary": {}}), encoding="utf-8")
    return PrivacySanitizer(tmp_path / "config.json", template)


def test_oversize_engine_fails_closed(sanitizer):
    with pytest.raises(InputTooLargeError, match="limit"):
        sanitizer.sanitize("x" * (MAX_SANITIZE_CHARS + 1))
    assert sanitizer.vault.size == 0
    assert sanitizer.sanitize("").sanitized_text == ""
    assert sanitizer.sanitize("ordinary text").sanitized_text == "ordinary text"


@pytest.mark.parametrize("mode", ["stdin", "file"])
def test_oversize_cli_no_output(sanitizer, tmp_path, monkeypatch, capsys, mode):
    raw = "password=synthetic-only\n" + "x" * MAX_SANITIZE_CHARS
    output = tmp_path / "output.txt"
    vault = tmp_path / "mapping.json"
    if mode == "stdin":
        monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
        args = ["--stdin"]
    else:
        source = tmp_path / "input.txt"
        source.write_text(raw, encoding="utf-8")
        output.write_text("existing", encoding="utf-8")
        args = ["--file", str(source), "--output", str(output), "--overwrite"]
    assert main(args + ["--vault-file", str(vault)], sanitizer) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "1,500,000" in captured.err
    assert "synthetic-only" not in captured.err
    assert not vault.exists()
    if mode == "file":
        assert output.read_text() == "existing"
        assert source.read_text() == raw


def test_oversize_manual_and_cruise_clipboard(sanitizer, monkeypatch):
    raw = "x" * (MAX_SANITIZE_CHARS + 1)
    app = SanitizerTrayApp(sanitizer)
    app.notify = Mock()
    copy = Mock()
    monkeypatch.setattr(app_module, "_safe_clipboard_paste", lambda: raw)
    monkeypatch.setattr(app_module, "_safe_clipboard_copy", copy)
    app.sanitize_clipboard()
    assert "UNSANITIZED" in app.notify.call_args.args[0]
    sanitizer.set_auto_sanitize_clipboard(True)
    app.notify.reset_mock()
    assert app._cruise_once("") == raw
    assert app._cruise_once("") == raw
    assert app.notify.call_count == 1  # repeated oversize changes do not flood notifications
    copy.assert_not_called()
    assert app._last_written_clipboard == ""
    assert app._clipboard_undo_stack == []


def test_oversize_sandbox_clears_previous_output(sanitizer):
    win = object.__new__(_ModernControlCenter)
    win.sanitizer = sanitizer
    win.lang = "en"
    win.sandbox_input = Mock()
    win.sandbox_input.get.return_value = "x" * (MAX_SANITIZE_CHARS + 1)
    win.sandbox_output = Mock()
    win.status_var = Mock()
    win._render_sandbox_category_pills = Mock()
    win._run_sandbox_sanitize()
    win.sandbox_output.delete.assert_called_once()
    win.sandbox_output.insert.assert_not_called()
    assert win._saved_sandbox_output == ""
    assert "UNSANITIZED" in win.status_var.set.call_args.args[0]


def test_private_vault_ram_and_roundtrip(sanitizer, tmp_path):
    original_files = set(tmp_path.iterdir())
    sanitized = sanitizer.sanitize("password=synthetic-only")
    assert set(tmp_path.iterdir()) == original_files
    target = tmp_path / "mapping.json"
    sanitizer.vault.save_to_file(target)
    loaded = SessionVault()
    loaded.load_from_file(target)
    sanitizer.vault = loaded
    assert sanitizer.restore(sanitized.sanitized_text).restored_text == "password=synthetic-only"
    assert not list(tmp_path.glob(".aps-*.tmp"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode test; Windows uses a protected DACL")
def test_private_permissions_before_publication(sanitizer, tmp_path, monkeypatch):
    from src import secure_io

    target = tmp_path / "mapping.json"
    observed = []
    replace = secure_io.os.replace

    def check_private(source, destination):
        observed.append(stat.S_IMODE(Path(source).stat().st_mode))
        assert Path(source).read_text()  # permission checked on the populated staging file
        replace(source, destination)

    monkeypatch.setattr(secure_io.os, "replace", check_private)
    previous = os.umask(0o022)
    try:
        sanitizer.vault.save_to_file(target)
        sanitizer.save_config()
        sanitizer.export_config(tmp_path / "backup.json")
    finally:
        os.umask(previous)
    assert observed == [0o600, 0o600, 0o600]
    assert stat.S_IMODE(sanitizer.config_path.stat().st_mode) == 0o600


def _assert_windows_private_acl(target):
    # Inspect actual NTFS ACL; do not confuse chmod's read-only bit with a DACL.
    script = "$ErrorActionPreference='Stop'; $a=Get-Acl -LiteralPath $env:APS_TEST_ACL_PATH; $me=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; if(-not $a.AreAccessRulesProtected){exit 1}; foreach($r in $a.Access){if($r.IsInherited -or $r.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -ne $me -or $r.AccessControlType -ne 'Allow' -or $r.FileSystemRights -ne 'FullControl'){exit 2}}; if(@($a.Access).Count -ne 1){exit 3}"
    environment = os.environ.copy()
    # pwsh's module search path is incompatible with Windows PowerShell 5.1.
    environment["PSModulePath"] = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/Modules")
    environment["APS_TEST_ACL_PATH"] = str(target)
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script], env=environment, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


@pytest.mark.skipif(os.name != "nt", reason="Requires a real Windows ACL implementation")
@pytest.mark.parametrize("operation", ["vault", "config", "export", "cli_new", "cli_overwrite"])
def test_private_windows_acl(tmp_path, sanitizer, capsys, operation):
    target = tmp_path / "mapping.json"
    if operation == "vault":
        sanitizer.sanitize("password=synthetic-only")
        sanitizer.vault.save_to_file(target)
    elif operation == "config":
        target = sanitizer.config_path
        sanitizer.set_language("zh")
    elif operation == "export":
        sanitizer.export_config(target)
    else:
        source = tmp_path / "input.txt"
        source.write_text("password=synthetic-only", encoding="utf-8")
        extra = []
        if operation == "cli_overwrite":
            target.write_text("existing", encoding="utf-8")
            extra = ["--overwrite"]
        assert main(["--file", str(source), "--output", str(target)] + extra, sanitizer) == 0
        assert capsys.readouterr().out == ""
    _assert_windows_private_acl(target)


@pytest.mark.skipif(os.name != "nt", reason="Requires a real Windows ACL implementation")
def test_private_windows_acl_exists_at_creation(tmp_path, monkeypatch):
    from src import secure_io

    restrict = secure_io._restrict_fd
    checked = []

    def inspect_new_file(fd, path):
        assert os.fstat(fd).st_size == 0
        _assert_windows_private_acl(path)
        checked.append(path)
        restrict(fd, path)

    monkeypatch.setattr(secure_io, "_restrict_fd", inspect_new_file)
    atomic_write_private(tmp_path / "mapping.json", "synthetic-only")
    assert len(checked) == 1


@pytest.mark.skipif(os.name != "nt", reason="Requires Windows native file creation")
@pytest.mark.parametrize("failure", ["descriptor", "create", "verify", "unprotected", "fd"])
def test_private_windows_creation_failure_cleans(tmp_path, monkeypatch, failure):
    import ctypes
    import msvcrt

    target = tmp_path / "output.txt"
    target.write_text("existing", encoding="utf-8")
    if failure == "fd":
        monkeypatch.setattr(msvcrt, "open_osfhandle", Mock(side_effect=OSError("synthetic conversion failure")))
    else:
        load = ctypes.WinDLL
        failed_api = {
            "descriptor": "ConvertStringSecurityDescriptorToSecurityDescriptorW",
            "create": "CreateFileW",
            "verify": "GetSecurityInfo",
            "unprotected": "GetSecurityDescriptorControl",
        }[failure]

        def fail(*_args):
            ctypes.set_last_error(5)
            if failure == "verify":
                return 5
            if failure == "unprotected":
                return 1  # successful API call, but no protected-DACL control flag
            return 0 if failure == "descriptor" else ctypes.c_void_p(-1).value

        class NativeProxy:
            def __init__(self, native):
                self.native = native
                setattr(self, failed_api, Mock(side_effect=fail))

            def __getattr__(self, name):
                return getattr(self.native, name)

        monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: NativeProxy(load(*args, **kwargs)))
    with pytest.raises(OSError):
        atomic_write_private(target, "synthetic-only")
    assert target.read_text() == "existing"
    assert not list(tmp_path.glob(".aps-*.tmp"))


@pytest.mark.parametrize("failure", ["permissions", "replace", "sync"])
def test_private_failure_preserves_destination_and_cleans(tmp_path, monkeypatch, failure):
    from src import secure_io

    target = tmp_path / "backup.json"
    target.write_text("original", encoding="utf-8")
    fail = Mock(side_effect=OSError("synthetic-only"))
    if failure == "permissions":
        monkeypatch.setattr(secure_io, "_restrict_fd", fail)
    else:
        monkeypatch.setattr(secure_io.os, "replace" if failure == "replace" else "fsync", fail)
    with pytest.raises(OSError):
        atomic_write_private(target, "new synthetic value")
    assert target.read_text() == "original"
    assert not list(tmp_path.glob(".aps-*.tmp"))


def test_private_rejects_links_and_no_clobber(tmp_path):
    target = tmp_path / "original.txt"
    target.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        atomic_write_private(target, "new", overwrite=False)
    if os.name == "posix":
        link = tmp_path / "alias"
        link.symlink_to(target)
        with pytest.raises(OSError):
            atomic_write_private(link, "new")
        link.unlink()
        os.link(target, link)
        with pytest.raises(OSError):
            atomic_write_private(link, "new")
    assert target.read_text() == "original"


def test_private_reparse_point_rejected_on_pre312_api(tmp_path, monkeypatch):
    from src.secure_io import validate_private_path

    junction = tmp_path / "simulated-junction"
    junction.mkdir()
    lstat = Path.lstat

    def attributes(path, **kwargs):
        info = lstat(path, **kwargs)
        if path == junction:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", attributes)
    with pytest.raises(OSError, match="Linked paths"):
        validate_private_path(junction / "output.json")


def test_private_no_clobber_race_keeps_other_writer(tmp_path, monkeypatch):
    from src import secure_io

    target = tmp_path / "output.txt"
    link = secure_io.os.link

    def concurrent_create(source, destination):
        target.write_text("other writer", encoding="utf-8")
        link(source, destination)

    monkeypatch.setattr(secure_io.os, "link", concurrent_create)
    with pytest.raises(FileExistsError):
        atomic_write_private(target, "synthetic-only", overwrite=False)
    assert target.read_text() == "other writer"
    assert not list(tmp_path.glob(".aps-*.tmp"))


def test_private_export_import_and_failure(sanitizer, tmp_path, monkeypatch):
    sanitizer.add_custom_word("COMPANY", "Fictional Nebula Company")
    sanitizer.add_custom_word("CUSTOM_SECRET", "fake-credential-only")
    backup = tmp_path / "backup.json"
    sanitizer.export_config(backup)
    sanitizer.clear_custom_dictionary()
    sanitizer.import_config(backup)
    assert "fake-credential-only" in sanitizer.get_custom_dictionary()["CUSTOM_SECRET"]
    before = backup.read_bytes()
    monkeypatch.setattr("src.secure_io.os.replace", Mock(side_effect=OSError()))
    with pytest.raises(OSError):
        sanitizer.export_config(backup)
    assert backup.read_bytes() == before
    assert not list(tmp_path.glob(".aps-*.tmp"))


def test_private_config_failure_restores_active_settings(sanitizer, monkeypatch):
    before = sanitizer.config_path.read_bytes()
    monkeypatch.setattr("src.secure_io.os.replace", Mock(side_effect=OSError()))
    with pytest.raises(OSError):
        sanitizer.set_language("zh")
    assert sanitizer.config_path.read_bytes() == before
    assert sanitizer.language == "en"


@pytest.mark.parametrize("alias", ["same", "hardlink", "symlink", "vault_input", "vault_output", "config_output"])
def test_cli_rejects_path_aliases(sanitizer, tmp_path, capsys, alias):
    source = tmp_path / "input.txt"
    source.write_text("password=synthetic-only", encoding="utf-8")
    output = tmp_path / "output.txt"
    extra = []
    if alias == "same":
        output = source
    elif alias in ("hardlink", "symlink"):
        if alias == "symlink" and os.name != "posix":
            pytest.skip("symlink creation requires additional Windows privileges")
        os.link(source, output) if alias == "hardlink" else output.symlink_to(source)
    elif alias == "vault_input":
        extra = ["--vault-file", str(source)]
    elif alias == "vault_output":
        extra = ["--vault-file", str(output)]
    else:
        output = sanitizer.config_path
    before_config = sanitizer.config_path.read_bytes()
    assert main(["--file", str(source), "--output", str(output), "--overwrite"] + extra, sanitizer) == 2
    assert source.read_text() == "password=synthetic-only"
    assert sanitizer.config_path.read_bytes() == before_config
    captured = capsys.readouterr()
    assert captured.out == "" and "synthetic-only" not in captured.err


def test_cli_explicit_overwrite_and_new_output(sanitizer, tmp_path, capsys):
    source, output = tmp_path / "input.txt", tmp_path / "output.txt"
    source.write_text("password=synthetic-only", encoding="utf-8")
    args = ["--file", str(source), "--output", str(output)]
    assert main(args, sanitizer) == 0
    assert "synthetic-only" not in output.read_text()
    output.write_text("existing", encoding="utf-8")
    assert main(args, sanitizer) == 2
    assert output.read_text() == "existing"
    assert main(args + ["--overwrite"], sanitizer) == 0
    assert sanitizer.restore(output.read_text()).restored_text == source.read_text()


@pytest.mark.parametrize("action", ["sanitize", "restore", "cruise", "undo"])
def test_clipboard_change_cancels_write(sanitizer, monkeypatch, action):
    raw = "password=synthetic-only"
    sanitized = sanitizer.sanitize(raw).sanitized_text
    original = sanitized if action == "restore" else raw
    values = iter([original, "new clipboard content"])
    monkeypatch.setattr(app_module, "_safe_clipboard_paste", lambda: next(values))
    copy = Mock()
    monkeypatch.setattr(app_module, "_safe_clipboard_copy", copy)
    app = SanitizerTrayApp(sanitizer)
    app.notify = Mock()
    app._last_written_clipboard = "previous"
    if action == "cruise":
        sanitizer.set_auto_sanitize_clipboard(True)
        app._cruise_once("")
    elif action == "undo":
        app._push_undo_snapshot(raw)
        app.undo_last_sanitize()
    else:
        getattr(app, action + "_clipboard")()
    copy.assert_not_called()
    assert app._last_written_clipboard == ("" if action == "cruise" else "previous")
    assert app._clipboard_undo_stack == ([raw] if action == "undo" else [])


@pytest.mark.parametrize("action", ["sanitize", "restore", "cruise", "undo"])
def test_clipboard_write_failure_keeps_state(sanitizer, monkeypatch, action):
    raw = "password=synthetic-only"
    sanitized = sanitizer.sanitize(raw).sanitized_text
    monkeypatch.setattr(app_module, "_safe_clipboard_paste", lambda: sanitized if action == "restore" else raw)
    monkeypatch.setattr(app_module, "_safe_clipboard_copy", Mock(side_effect=OSError("fake-credential-only")))
    monkeypatch.setattr(app_module.time, "sleep", lambda _s: None)
    app = SanitizerTrayApp(sanitizer)
    app.notify = Mock()
    if action == "cruise":
        sanitizer.set_auto_sanitize_clipboard(True)
        assert app._cruise_once("last successful read") == "last successful read"
    elif action == "undo":
        app._push_undo_snapshot(raw)
        app.undo_last_sanitize()
    else:
        getattr(app, action + "_clipboard")()
    assert app._last_written_clipboard == ""
    assert app._clipboard_undo_stack == ([raw] if action == "undo" else [])
    for call in app.notify.call_args_list:
        assert "fake-credential-only" not in call.args[0]


def test_clipboard_retry_rechecks_source(monkeypatch):
    monkeypatch.setattr(app_module, "_safe_clipboard_paste", Mock(side_effect=["old", "new"]))
    copy = Mock(side_effect=OSError())
    monkeypatch.setattr(app_module, "_safe_clipboard_copy", copy)
    monkeypatch.setattr(app_module.time, "sleep", lambda _s: None)
    assert not app_module._replace_clipboard_if_unchanged("old", "masked")
    assert copy.call_count == 1


def test_gui_clear_vault_uses_clipboard_lock_and_clears_undo(sanitizer):
    app = SanitizerTrayApp(sanitizer)
    app._push_undo_snapshot("password=synthetic-only")
    sanitizer.sanitize("password=synthetic-only")
    win = object.__new__(_ModernControlCenter)
    win.sanitizer = sanitizer
    win.on_clear_session = app.gui.on_clear_session
    win.refresh_all = Mock()
    win.status_var = Mock()
    win._clear_vault_from_gui()
    assert sanitizer.vault.size == 0
    assert app._clipboard_undo_stack == []
    app.notify = Mock()
    app.undo_last_sanitize()
    assert "No previous" in app.notify.call_args.args[0]


def test_cruise_expires_old_self_write_after_another_value(sanitizer, monkeypatch):
    raw = "password=synthetic-only"
    clipboard = {"text": raw}
    monkeypatch.setattr(app_module, "_safe_clipboard_paste", lambda: clipboard["text"])
    monkeypatch.setattr(app_module, "_safe_clipboard_copy", lambda value, **_kw: clipboard.update(text=value))
    sanitizer.set_auto_sanitize_clipboard(True)
    app = SanitizerTrayApp(sanitizer)
    app._last_written_clipboard = raw  # an intentional restore/undo must not immediately be remasked
    assert app._cruise_once("") == raw
    clipboard["text"] = "ordinary text"
    assert app._cruise_once(raw) == "ordinary text"
    clipboard["text"] = raw
    result = app._cruise_once("ordinary text")
    assert "synthetic-only" not in result
    assert clipboard["text"] == result


def test_restore_semantic_token_boundaries(sanitizer):
    sanitizer.set_semantic_ip_mode(True)
    raw = "10.5.6.7 boss@fictional.test /Users/fake_operator/code.py"
    masked = sanitizer.sanitize(raw).sanitized_text
    assert sanitizer.restore(masked).restored_text == raw
    invalid = "192.0.2.1010 xuser1@example.com user1@example.com.evil dev_user_10 https://192.0.2.101.evil.test !user1@example.com dev_user_1-other dev_user_1.other 中dev_user_1"
    assert sanitizer.restore(invalid).restored_text == invalid
    assert sanitizer.restore("192.0.2.101.").restored_text == "10.5.6.7."


@pytest.mark.parametrize("text", ["API_KEY_1", "<API_KEY_10>", "<API_KEY_1]", "{API_KEY_1'", "<API_KEY_1_extra>"])
def test_restore_fuzzy_invalid_remains_text(sanitizer, text):
    sanitizer.sanitize("token=fake-credential-only")
    result = sanitizer.restore(text)
    assert result.restored_text == text and result.restored_count == 0


def test_gui_layout_swap_keeps_old_until_ready():
    win = object.__new__(_ModernControlCenter)
    events = []
    old, new = Mock(), Mock()
    old.pack_forget.side_effect = lambda: events.append("unmap old")
    old.grid_forget.side_effect = lambda: events.append("unmap old")
    old.destroy.side_effect = lambda: events.append("destroy old")
    new.grid.side_effect = lambda **_kw: events.append("map new")
    new.lower.side_effect = lambda _old: events.append("stage behind old")
    new.lift.side_effect = lambda: events.append("show new")
    win._main_container = old
    win.root = Mock()
    win.root.update_idletasks.side_effect = lambda: events.append("layout ready")

    def construct():
        old.destroy.assert_not_called()
        old.pack_forget.assert_not_called()
        events.append("build complete")
        win._main_container = new

    win._construct_layout = construct
    win._build_layout()
    assert events == ["build complete", "map new", "stage behind old", "layout ready", "show new", "destroy old"]
    old.grid_forget.assert_not_called()


def test_gui_layout_failure_preserves_old():
    win = object.__new__(_ModernControlCenter)
    old, partial = Mock(), Mock()
    win._main_container = old

    def fail():
        win._main_container = partial
        raise RuntimeError("synthetic construction error")

    win._construct_layout = fail
    with pytest.raises(RuntimeError):
        win._build_layout()
    assert win._main_container is old
    old.destroy.assert_not_called()
    old.pack_forget.assert_not_called()
    partial.destroy.assert_called_once()


@pytest.mark.parametrize("failure", ["map", "layout"])
def test_gui_layout_swap_failure_remaps_old(failure):
    win = object.__new__(_ModernControlCenter)
    old, new = Mock(), Mock()
    win._main_container = old
    win.root = Mock()
    win._construct_layout = lambda: setattr(win, "_main_container", new)
    if failure == "map":
        new.grid.side_effect = RuntimeError("synthetic map failure")
    else:
        win.root.update_idletasks.side_effect = RuntimeError("synthetic layout failure")
    with pytest.raises(RuntimeError):
        win._build_layout()
    assert win._main_container is old
    old.grid_forget.assert_not_called()
    old.pack_forget.assert_not_called()
    old.destroy.assert_not_called()
    new.destroy.assert_called_once()


def test_gui_language_failure_reverts_saved_preference(sanitizer):
    win = object.__new__(_ModernControlCenter)
    win.sanitizer = sanitizer
    win.lang = "en"
    win.root = Mock()
    win.status_var = Mock()
    win._snapshot_ui_state = Mock()
    win._refresh_translations = Mock(side_effect=RuntimeError("synthetic translation error"))
    win.on_language_changed = Mock()
    win._toggle_language()
    assert win.lang == sanitizer.language == "en"
    win.on_language_changed.assert_not_called()


def test_gui_language_save_failure_restores_layout_and_preference(sanitizer, monkeypatch):
    win = object.__new__(_ModernControlCenter)
    old, new = Mock(), Mock()
    win.sanitizer = sanitizer
    win.lang = "en"
    win.root = Mock()
    win.status_var = Mock()
    win._main_container = old
    win._snapshot_ui_state = Mock()
    win._refresh_translations = Mock()
    win.on_language_changed = Mock()
    before = sanitizer.config_path.read_bytes()
    monkeypatch.setattr("src.secure_io.os.replace", Mock(side_effect=OSError("synthetic save failure")))
    win._toggle_language()
    assert win.lang == sanitizer.language == "en"
    assert sanitizer.config_path.read_bytes() == before
    assert win._main_container is old
    old.grid_forget.assert_not_called()
    old.pack_forget.assert_not_called()
    old.destroy.assert_not_called()
    win.on_language_changed.assert_not_called()


def test_gui_windows_theme_never_hides_window(monkeypatch):
    import src.gui as gui

    win = Mock()
    win.winfo_id.return_value = 42
    get_parent, set_attribute = Mock(return_value=43), Mock(return_value=0)
    native = SimpleNamespace(user32=SimpleNamespace(GetParent=get_parent), dwmapi=SimpleNamespace(DwmSetWindowAttribute=set_attribute))
    monkeypatch.setattr(gui.platform, "system", lambda: "Windows")
    monkeypatch.setattr(gui.ctypes, "windll", native, raising=False)
    _StableCTk._windows_set_titlebar_color(win, "Dark")
    set_attribute.assert_called_once()
    win.withdraw.assert_not_called()
    win.deiconify.assert_not_called()
    win.update.assert_not_called()


def test_cruise_uses_engine_limit_and_successful_write(sanitizer, monkeypatch):
    sanitizer.rules = []
    sanitizer.add_custom_word("CUSTOM_SECRET", "fake-credential-only")
    sanitizer.set_auto_sanitize_clipboard(True)
    raw = "fake-credential-only " + "x" * 1_000_000
    monkeypatch.setattr(app_module, "_safe_clipboard_paste", lambda: raw)
    copy = Mock()
    monkeypatch.setattr(app_module, "_safe_clipboard_copy", copy)
    app = SanitizerTrayApp(sanitizer)
    result = app._cruise_once("")
    assert "fake-credential-only" not in result
    assert app._last_written_clipboard == result
    assert app._clipboard_undo_stack == [raw]
    copy.assert_called_once_with(result, retries=1)


@pytest.mark.parametrize("raw, secret", [
    ('ToKeN = "FictionalValue99"', "FictionalValue99"),
    ('密码 = "虚构 密码 888"', "虚构 密码 888"),
    ('postgres://test_user:fake%2Fpassword@localhost/db', "fake%2Fpassword"),
    ('password=fake-one\npassword=fake-two', "fake-one"),
])
def test_rule_bounded_synthetic_variants(sanitizer, raw, secret):
    result = sanitizer.sanitize(raw)
    assert secret not in result.sanitized_text
    assert sanitizer.restore(result.sanitized_text).restored_text == raw
    control = "ordinary prose; localhost; example.com; <API_KEY_unknown>"
    assert sanitizer.sanitize(control).sanitized_text == control


def test_rule_repetition_and_semantic_exhaustion_are_bounded(sanitizer):
    # A subprocess deadline prevents a regression from hanging the test process.
    code = """
import sys
from src.sanitizer import PrivacySanitizer
s = PrivacySanitizer(sys.argv[1], sys.argv[2])
ordinary = ('a' * 127 + '\\n') * 128
assert s.sanitize(ordinary).sanitized_text == ordinary
s.set_semantic_ip_mode(True)
raw = ' '.join('10.1.0.' + str(i) for i in range(1, 153))
masked = s.sanitize(raw).sanitized_text
assert '[PRIVATE_IP_151]' in masked
assert s.vault.size == 152
assert s.restore(masked).restored_text == raw
"""
    subprocess.run([sys.executable, "-c", code, str(sanitizer.config_path), str(sanitizer.example_config_path)], check=True, timeout=5, capture_output=True)


@pytest.mark.parametrize("form", ["leading", "adjacent", "surrounded"])
def test_mixed_placeholder_password_is_not_treated_as_already_sanitized(sanitizer, form):
    first = sanitizer.sanitize("password=synthetic-first").sanitized_text.split("=", 1)[1]
    values = {
        "leading": first + " synthetic-second",
        "adjacent": "synthetic-second" + first + "tail",
        "surrounded": "left " + first + " synthetic-tail",
    }
    raw = 'password="' + values[form] + '"'
    result = sanitizer.sanitize(raw)
    assert "synthetic-second" not in result.sanitized_text
    assert "synthetic-tail" not in result.sanitized_text
    assert sanitizer.restore(result.sanitized_text).restored_text == raw
    assert sanitizer.sanitize(result.sanitized_text).sanitized_text == result.sanitized_text


def test_short_custom_words_cannot_rewrite_internal_marker_fragments(sanitizer):
    for word in ["X", "SAN", "_"]:
        sanitizer.add_custom_word("COMPANY", word)
    result = sanitizer.sanitize("X")
    assert "\x00" not in result.sanitized_text
    assert sanitizer.restore(result.sanitized_text).restored_text == "X"


def test_known_semantic_prefix_does_not_hide_a_longer_username(sanitizer):
    sanitizer.set_semantic_ip_mode(True)
    sanitizer.sanitize("/home/fake_operator/file")
    for raw in ["/home/dev_user_1suffix/file", "/home/dev_user_1-other/file"]:
        result = sanitizer.sanitize(raw)
        assert result.total_count == 1
        assert "dev_user_1suffix" not in result.sanitized_text
        assert "dev_user_1-other" not in result.sanitized_text
        assert sanitizer.restore(result.sanitized_text).restored_text == raw
