"""Focused system-hotkey regressions; no clipboard data or arbitrary key capture."""

from pathlib import Path
import json
import queue
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.windows_hotkeys import WindowsHotkeys, parse_hotkey


class FakeAPI:
    def __init__(self, fail_at=None):
        self.messages = queue.Queue()
        self.registered = []
        self.released = []
        self.fail_at = fail_at

    def key_scan(self, key):
        return ord(key.upper()) if key.isalnum() else -1

    def thread_id(self):
        return threading.get_native_id()

    def register(self, identity, modifiers, key):
        if identity == self.fail_at:
            return False
        self.registered.append((identity, modifiers, key))
        return True

    def unregister(self, identity):
        self.released.append(identity)

    def get_message(self, message):
        result, kind, identity = self.messages.get(timeout=5)
        message.message, message.wParam = kind, identity
        return result

    def stop(self, _thread_id):
        self.messages.put((0, 0, 0))
        return True


@pytest.mark.parametrize("binding,expected", [
    ("alt+s", (1, 0x53)), ("alt+r", (1, 0x52)),
    ("ctrl+shift+s", (6, 0x53)), ("f8", (0, 0x77)),
    ("ctrl+f8", (2, 0x77)), ("alt+page up", (1, 0x21)),
])
def test_existing_chords_translate(binding, expected):
    assert parse_hotkey(binding, FakeAPI().key_scan) == expected


@pytest.mark.parametrize("binding", ["alt+", "ctrl+ctrl+s", "f25", "ctrl+s,r"])
def test_invalid_or_multistep_chords_are_explicit_errors(binding):
    with pytest.raises(ValueError):
        parse_hotkey(binding, FakeAPI().key_scan)


def test_only_system_hotkey_messages_dispatch_and_owned_ids_are_released():
    api = FakeAPI()
    first, second = threading.Event(), threading.Event()
    owner = WindowsHotkeys([("alt+s", first.set), ("alt+r", second.set)], api)
    owner.start()
    try:
        for entry in [(1, 0, 0), (1, 0x312, 999), (1, 0x312, 1), (1, 0x312, 2)]:
            api.messages.put(entry)
        assert first.wait(1) and second.wait(1)
        assert owner.active
    finally:
        owner.stop()
    assert api.released == [1, 2]


def test_partial_registration_failure_releases_first_chord():
    api = FakeAPI(fail_at=2)
    owner = WindowsHotkeys([("alt+s", Mock()), ("alt+r", Mock())], api)
    with pytest.raises(OSError, match="unavailable"):
        owner.start()
    assert api.released == [1] and not owner.active


def test_equivalent_chord_aliases_cannot_register_twice():
    api = FakeAPI()
    with pytest.raises(ValueError, match="Duplicate"):
        WindowsHotkeys([("ctrl+s", Mock()), ("control+s", Mock())], api).start()
    assert api.registered == []


def test_windows_registration_failure_restores_previous_owner(monkeypatch):
    import src.windows_hotkeys as native
    from src.main import SanitizerTrayApp
    from src import main as app_module
    previous = Mock()
    candidate = Mock()
    candidate.start.side_effect = OSError("occupied")
    monkeypatch.setattr(native, "WindowsHotkeys", Mock(return_value=candidate))
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    app = object.__new__(SanitizerTrayApp)
    app.sanitizer = SimpleNamespace(hotkeys={"sanitize": "alt+s", "restore": "alt+r"})
    app.sanitize_clipboard, app.restore_clipboard = Mock(), Mock()
    app._windows_hotkeys = previous
    assert app.register_hotkeys() is False
    previous.stop.assert_called_once()
    previous.start.assert_called_once()
    assert app._windows_hotkeys is previous


def test_invalid_candidate_does_not_stop_existing_hotkeys(monkeypatch):
    import src.windows_hotkeys as native
    from src.main import SanitizerTrayApp
    from src import main as app_module
    previous = Mock()
    monkeypatch.setattr(native, "WindowsHotkeys", Mock(side_effect=ValueError("unsupported key")))
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    app = object.__new__(SanitizerTrayApp)
    app.sanitizer = SimpleNamespace(hotkeys={"sanitize": "bad", "restore": "alt+r"})
    app.sanitize_clipboard, app.restore_clipboard = Mock(), Mock()
    app._windows_hotkeys = previous
    assert app.register_hotkeys() is False
    previous.stop.assert_not_called()


def test_registration_error_is_displayed_on_window_start(monkeypatch):
    import src.gui as gui
    root, window = Mock(), Mock()
    monkeypatch.setattr(gui, "_StableCTk", Mock(return_value=root))
    monkeypatch.setattr(gui, "_ModernControlCenter", Mock(return_value=window))
    monkeypatch.setattr(gui, "enable_high_dpi_awareness", Mock())
    monkeypatch.setattr(gui.ctk, "set_default_color_theme", Mock())
    monkeypatch.setattr(gui.ctk, "set_appearance_mode", Mock())
    controller = gui.GuiController(SimpleNamespace(theme="dark"))
    controller.startup_status = "synthetic registration conflict"
    controller.run_main_loop(show_on_start=False)
    window.status_var.set.assert_called_once_with("synthetic registration conflict")


def test_gui_registration_failure_rolls_back_saved_settings(tmp_path, monkeypatch):
    from src.gui import _ModernControlCenter
    from src.sanitizer import PrivacySanitizer
    example = tmp_path / "example.json"
    example.write_text('{"hotkeys":{"sanitize":"alt+s","restore":"alt+r"}}', encoding="utf-8")
    sanitizer = PrivacySanitizer(tmp_path / "config.json", example)
    before = json.loads(sanitizer.config_path.read_text(encoding="utf-8"))
    win = object.__new__(_ModernControlCenter)
    win.sanitizer, win.lang = sanitizer, "en"
    win.combo_hk_sanitize, win.combo_hk_restore = Mock(), Mock()
    win.combo_hk_sanitize.get.return_value = "ctrl+shift+s"
    win.combo_hk_restore.get.return_value = "ctrl+shift+r"
    win.on_reload_hotkeys = Mock(return_value=False)
    win._refresh_hotkey_labels, win.status_var, win.root = Mock(), Mock(), Mock()
    warning = Mock()
    monkeypatch.setattr("src.gui.messagebox.showwarning", warning)
    win._save_and_apply_hotkeys()
    assert sanitizer.hotkeys == {"sanitize": "alt+s", "restore": "alt+r"}
    assert json.loads(sanitizer.config_path.read_text(encoding="utf-8")) == before
    warning.assert_called_once()


def _settings(tmp_path):
    from src.sanitizer import PrivacySanitizer

    example = tmp_path / "example.json"
    example.write_text(json.dumps({
        "hotkeys": {"sanitize": "alt+s", "restore": "ctrl+shift+r"},
        "custom_dictionary": {},
    }), encoding="utf-8")
    return PrivacySanitizer(tmp_path / "config.json", example)


def test_conflict_never_persists_candidate_even_if_config_is_unwritable(tmp_path, monkeypatch):
    from src.gui import _ModernControlCenter
    from src.main import SanitizerTrayApp
    from src import main as app_module
    import src.windows_hotkeys as native

    sanitizer = _settings(tmp_path)
    before = sanitizer.config_path.read_bytes()
    app = SanitizerTrayApp(sanitizer)
    old = WindowsHotkeys([("alt+s", Mock()), ("ctrl+shift+r", Mock())], FakeAPI())
    old.start()
    app._windows_hotkeys = old
    candidate_api = FakeAPI(fail_at=2)
    monkeypatch.setattr(native, "_WindowsAPI", lambda: candidate_api)
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    write = Mock(side_effect=PermissionError("synthetic write denied"))
    monkeypatch.setattr("src.sanitizer.atomic_write_private", write)
    win = object.__new__(_ModernControlCenter)
    win.sanitizer, win.lang, win.root, win.status_var = sanitizer, "en", Mock(), Mock()
    win.combo_hk_sanitize, win.combo_hk_restore = Mock(), Mock()
    win.combo_hk_sanitize.get.return_value = "ctrl+alt+s"
    win.combo_hk_restore.get.return_value = "ctrl+alt+r"
    win.on_reload_hotkeys = app.reload_hotkeys
    win._refresh_hotkey_labels = Mock()
    warning = Mock()
    monkeypatch.setattr("src.gui.messagebox.showwarning", warning)
    try:
        win._save_and_apply_hotkeys()
        assert candidate_api.registered == [(1, 3, 0x53)]
        assert candidate_api.released == [1]
        assert app._windows_hotkeys is old and old.active
        assert sanitizer.config_path.read_bytes() == before
        assert sanitizer.hotkeys == {"sanitize": "alt+s", "restore": "ctrl+shift+r"}
        write.assert_not_called()
        warning.assert_called_once()
    finally:
        old.stop()


def test_candidate_is_registered_before_the_only_configuration_write(tmp_path, monkeypatch):
    from src.main import SanitizerTrayApp
    from src import main as app_module
    from src.secure_io import atomic_write_private

    sanitizer = _settings(tmp_path)
    app = SanitizerTrayApp(sanitizer)
    previous = sanitizer.hotkeys
    candidate = {"sanitize": "ctrl+alt+s", "restore": "ctrl+alt+r"}
    events = []

    def register(keys):
        assert sanitizer.hotkeys == previous
        assert json.loads(sanitizer.config_path.read_text())["hotkeys"] == previous
        events.append("registered")
        return True

    def write(path, text, **kwargs):
        assert events == ["registered"]
        events.append("persisted")
        atomic_write_private(path, text, **kwargs)

    app.register_hotkeys = Mock(side_effect=register)
    app.refresh_tray_i18n = Mock()
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr("src.sanitizer.atomic_write_private", write)
    assert app.reload_hotkeys({"sanitize": " CTRL + ALT + S ", "restore": "ctrl+alt+r"})
    assert events == ["registered", "persisted"]
    app.register_hotkeys.assert_called_once_with(candidate)
    assert sanitizer.hotkeys == candidate
    app.refresh_tray_i18n.assert_called_once()


def test_save_failure_restores_native_bindings_without_another_disk_write(tmp_path, monkeypatch):
    from src.main import SanitizerTrayApp
    from src import main as app_module

    sanitizer = _settings(tmp_path)
    app = SanitizerTrayApp(sanitizer)
    previous = sanitizer.hotkeys
    before = sanitizer.config_path.read_bytes()
    candidate = {"sanitize": "ctrl+alt+s", "restore": "ctrl+alt+r"}
    app.register_hotkeys = Mock(side_effect=[True, True])
    app.refresh_tray_i18n = Mock()
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    write = Mock(side_effect=PermissionError("synthetic persistence failure"))
    monkeypatch.setattr("src.sanitizer.atomic_write_private", write)
    with pytest.raises(PermissionError):
        app.reload_hotkeys(candidate)
    assert [call.args[0] for call in app.register_hotkeys.call_args_list] == [candidate, previous]
    assert sanitizer.config_path.read_bytes() == before
    assert sanitizer.hotkeys == previous
    assert write.call_count == 1
    app.refresh_tray_i18n.assert_not_called()


def test_save_and_native_rollback_failure_are_reported_explicitly(tmp_path, monkeypatch):
    from src.main import SanitizerTrayApp
    from src import main as app_module
    from src.gui import _ModernControlCenter

    sanitizer = _settings(tmp_path)
    app = SanitizerTrayApp(sanitizer)
    previous = sanitizer.hotkeys
    app.register_hotkeys = Mock(side_effect=[True, False])
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr("src.sanitizer.atomic_write_private", Mock(side_effect=PermissionError("synthetic")))
    win = object.__new__(_ModernControlCenter)
    win.sanitizer, win.lang, win.root, win.status_var = sanitizer, "en", Mock(), Mock()
    win.combo_hk_sanitize, win.combo_hk_restore = Mock(), Mock()
    win.combo_hk_sanitize.get.return_value = "ctrl+alt+s"
    win.combo_hk_restore.get.return_value = "ctrl+alt+r"
    win.on_reload_hotkeys = app.reload_hotkeys
    win._refresh_hotkey_labels = Mock()
    warning = Mock()
    monkeypatch.setattr("src.gui.messagebox.showwarning", warning)
    win._save_and_apply_hotkeys()
    assert sanitizer.hotkeys == previous
    assert app.register_hotkeys.call_count == 2
    assert warning.call_args.args[1] == win._t("msg_hk_rollback_err")
    assert win.status_var.set.call_args.args[0] == win._t("msg_hk_rollback_err")
    assert "could not be confirmed" in win._t("msg_hk_rollback_err")


def test_gui_success_persists_and_displays_the_registered_candidate(tmp_path, monkeypatch):
    from src.gui import _ModernControlCenter
    from src.main import SanitizerTrayApp
    from src import main as app_module

    sanitizer = _settings(tmp_path)
    app = SanitizerTrayApp(sanitizer)
    app.register_hotkeys = Mock(return_value=True)
    app.refresh_tray_i18n = Mock()
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    win = object.__new__(_ModernControlCenter)
    win.sanitizer, win.lang, win.root, win.status_var = sanitizer, "en", Mock(), Mock()
    win.combo_hk_sanitize, win.combo_hk_restore = Mock(), Mock()
    win.combo_hk_sanitize.get.return_value = " CTRL + ALT + S "
    win.combo_hk_restore.get.return_value = "ctrl+alt+r"
    win.on_reload_hotkeys = app.reload_hotkeys
    win._refresh_hotkey_labels = Mock()
    warning = Mock()
    monkeypatch.setattr("src.gui.messagebox.showwarning", warning)
    win._save_and_apply_hotkeys()
    candidate = {"sanitize": "ctrl+alt+s", "restore": "ctrl+alt+r"}
    assert sanitizer.hotkeys == candidate
    assert json.loads(sanitizer.config_path.read_text())["hotkeys"] == candidate
    app.register_hotkeys.assert_called_once_with(candidate)
    win._refresh_hotkey_labels.assert_called_once()
    app.refresh_tray_i18n.assert_called_once()
    assert "CTRL+ALT+S" in win.status_var.set.call_args.args[0]
    warning.assert_not_called()


def test_non_windows_save_failure_reinstalls_previous_keyboard_bindings(tmp_path, monkeypatch):
    from src.main import SanitizerTrayApp
    from src import main as app_module

    sanitizer = _settings(tmp_path)
    app = SanitizerTrayApp(sanitizer)
    previous = sanitizer.hotkeys
    candidate = {"sanitize": "ctrl+alt+s", "restore": "ctrl+alt+r"}
    app.register_hotkeys = Mock(side_effect=[True, True])
    keyboard = SimpleNamespace(unhook_all_hotkeys=Mock())
    monkeypatch.setitem(sys.modules, "keyboard", keyboard)
    monkeypatch.setattr(app_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr("src.sanitizer.atomic_write_private", Mock(side_effect=PermissionError("synthetic")))
    with pytest.raises(PermissionError):
        app.reload_hotkeys(candidate)
    assert [call.args[0] for call in app.register_hotkeys.call_args_list] == [candidate, previous]
    assert keyboard.unhook_all_hotkeys.call_count == 2
    assert sanitizer.hotkeys == previous


def test_invalid_candidate_cannot_change_registration_or_disk(tmp_path, monkeypatch):
    from src.main import SanitizerTrayApp
    from src import main as app_module

    sanitizer = _settings(tmp_path)
    app = SanitizerTrayApp(sanitizer)
    before = sanitizer.config_path.read_bytes()
    app.register_hotkeys = Mock()
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    with pytest.raises(ValueError):
        app.reload_hotkeys({"sanitize": "alt+s", "restore": "alt+s"})
    app.register_hotkeys.assert_not_called()
    assert sanitizer.config_path.read_bytes() == before


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows hotkeys")
def test_native_registration_delivery_cleanup_and_reregistration():
    code = r'''
import ctypes, threading
from ctypes import wintypes
from src.windows_hotkeys import WindowsHotkeys
first, second = threading.Event(), threading.Event()
bindings = [('ctrl+alt+shift+f23', first.set), ('ctrl+alt+shift+f24', second.set)]
owner = WindowsHotkeys(bindings)
native = ctypes.WinDLL('user32', use_last_error=True)
native.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
native.PostThreadMessageW.restype = wintypes.BOOL
owner.start()
try:
    assert native.PostThreadMessageW(owner._thread_id, 0, 0, 0)
    assert native.PostThreadMessageW(owner._thread_id, 0x312, 1, 0)
    assert native.PostThreadMessageW(owner._thread_id, 0x312, 2, 0)
    assert first.wait(2) and second.wait(2) and owner.active
finally:
    owner.stop()
# A second owner can obtain the same chords only if the first released them.
next_owner = WindowsHotkeys(bindings)
next_owner.start()
next_owner.stop()
'''
    subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parent.parent,
                   check=True, capture_output=True, timeout=10)
