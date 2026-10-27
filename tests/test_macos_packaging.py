"""Nonvisual checks for native packaging boundaries and macOS startup integration."""

from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_macos
from src import main as app_module
from src import sanitizer as engine
from src.gui import _ModernControlCenter
from src.main import SanitizerTrayApp


@pytest.fixture
def sanitizer(tmp_path):
    return engine.PrivacySanitizer(tmp_path / "config.json", tmp_path / "unused-example.json")


def test_config_for_frozen_macos_lives_outside_app_bundle(tmp_path, monkeypatch):
    monkeypatch.setattr(engine.sys, "frozen", True, raising=False)
    monkeypatch.setattr(engine.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert engine.get_default_config_path() == tmp_path / "Library" / "Application Support" / "AI-Privacy-Sanitizer" / "config.json"
    monkeypatch.setattr(engine.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert engine.get_default_config_path() == tmp_path / "Local" / "Sanitizer" / "config.json"


def test_build_rejects_non_macos_and_mismatched_architecture(monkeypatch):
    monkeypatch.setattr(build_macos.platform, "system", lambda: "Linux")
    with pytest.raises(RuntimeError, match="native macOS"):
        build_macos.validate_host("arm64")
    monkeypatch.setattr(build_macos.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(build_macos.platform, "machine", lambda: "arm64")
    with pytest.raises(RuntimeError, match="matching"):
        build_macos.validate_host("x86_64")
    build_macos.validate_host("arm64")


def test_self_test_uses_only_its_own_temporary_config(tmp_path, monkeypatch, capsys):
    forbidden = tmp_path / "user-config.json"
    monkeypatch.setattr(engine, "DEFAULT_CONFIG_PATH", forbidden)
    original = engine.PrivacySanitizer
    created = []

    def create(**kwargs):
        created.append(kwargs["config_path"])
        return original(**kwargs)

    monkeypatch.setattr(app_module, "PrivacySanitizer", create)
    assert app_module.main(["--self-test"]) == 0
    assert len(created) == 1 and created[0] != forbidden
    assert not created[0].exists() and not forbidden.exists()
    assert "已还原" in capsys.readouterr().out


def test_macos_menu_bar_starts_after_tk_and_uses_detached_loop(sanitizer, monkeypatch):
    app = SanitizerTrayApp(sanitizer)
    app._start_clipboard_cruise_watcher = Mock()
    events = []
    native_app = object()

    class Menu:
        SEPARATOR = object()

        def __init__(self, *items):
            pass

    icon = Mock()
    icon.run_detached.side_effect = lambda: events.append("detached")

    def make_icon(**kwargs):
        assert events[0] == "Tk ready"
        assert kwargs["darwin_nsapplication"] is native_app
        events.append("icon")
        return icon

    monkeypatch.setitem(sys.modules, "pystray", SimpleNamespace(Icon=make_icon, Menu=Menu, MenuItem=lambda *args, **kwargs: object()))
    monkeypatch.setitem(sys.modules, "AppKit", SimpleNamespace(NSApplication=SimpleNamespace(sharedApplication=lambda: native_app)))
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")

    def gui_loop(*, show_on_start, before_mainloop):
        events.append("Tk ready")
        before_mainloop()
        events.append("Tk loop")

    app.gui.run_main_loop = gui_loop
    app.run(show_gui_on_start=True)
    assert app.gui.startup_status == app._t("macos_preview_hotkeys")
    assert events == ["Tk ready", "icon", "detached", "Tk loop"]
    icon.run.assert_not_called()


def test_other_platforms_keep_background_tray_loop(sanitizer, monkeypatch):
    app = SanitizerTrayApp(sanitizer)
    app.icon = Mock()
    thread = Mock()
    constructor = Mock(return_value=thread)
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(app_module.threading, "Thread", constructor)
    app._start_tray_loop()
    constructor.assert_called_once_with(target=app.icon.run, daemon=True)
    thread.start.assert_called_once()
    app.icon.run_detached.assert_not_called()


def test_macos_preview_does_not_request_root_keyboard_listener(sanitizer, monkeypatch):
    app = SanitizerTrayApp(sanitizer)
    keyboard = SimpleNamespace(add_hotkey=Mock(), unhook_all_hotkeys=Mock())
    monkeypatch.setitem(sys.modules, "keyboard", keyboard)
    monkeypatch.setattr(app_module.platform, "system", lambda: "Darwin")
    assert not app.register_hotkeys()
    keyboard.add_hotkey.assert_not_called()
    assert not app.reload_hotkeys()
    app.exit_app()
    keyboard.unhook_all_hotkeys.assert_not_called()
    win = object.__new__(_ModernControlCenter)
    win.lang = "en"
    assert "disabled" in win._t("status_ready")
