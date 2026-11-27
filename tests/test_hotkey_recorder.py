"""Tests for Antigravity IDE-style arbitrary hotkey recorder, validation, VK mapping, and Quick Guide sync."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tkinter as tk

import customtkinter as ctk
import pytest

from src.gui import _ModernControlCenter, _StableCTk, format_hotkey_display, normalize_tk_key_event
from src.sanitizer import PrivacySanitizer
from src.windows_hotkeys import parse_hotkey


def _make_win(tmp_path: Path, hotkeys=None):
    example = tmp_path / "example.json"
    example.write_text(
        json.dumps(
            {
                "language": "zh",
                "theme": "dark",
                "hotkeys": hotkeys or {"sanitize": "alt+s", "restore": "alt+r"},
                "custom_dictionary": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sanitizer = PrivacySanitizer(tmp_path / "config.json", example)
    ctk.set_appearance_mode("Dark")
    try:
        root = _StableCTk()
    except tk.TclError as exc:
        if "display" in str(exc).lower():
            pytest.skip("Tk display unavailable")
        raise
    root.withdraw()
    win = _ModernControlCenter(root, sanitizer)
    root.update_idletasks()
    return root, win, sanitizer


def _destroy_root(root):
    for timer in root.tk.splitlist(root.tk.call("after", "info")):
        root.tk.call("after", "cancel", timer)
    root.destroy()


@pytest.mark.parametrize(
    "raw_san,raw_res,expected_san,expected_res,vk_san,vk_res",
    [
        ("ctrl+`", "ctrl+;", "ctrl+`", "ctrl+;", (2, 0xC0), (2, 0xBA)),
        ("shift+ctrl+[", "ctrl+]", "ctrl+shift+[", "ctrl+]", (6, 0xDB), (2, 0xDD)),
        ("ctrl+,", "ctrl+.", "ctrl+,", "ctrl+.", (2, 0xBC), (2, 0xBE)),
        ("ctrl+=", "alt+-", "ctrl+=", "alt+-", (2, 0xBB), (1, 0xBD)),
        ("ctrl+/", "ctrl+\\", "ctrl+/", "ctrl+\\", (2, 0xBF), (2, 0xDC)),
        ("ctrl+alt+left", "ctrl+alt+right", "ctrl+alt+left", "ctrl+alt+right", (3, 0x25), (3, 0x27)),
        ("ctrl+num1", "alt+num_add", "ctrl+num1", "alt+num_add", (2, 0x61), (1, 0x6B)),
        ("win+alt+s", "f12", "alt+win+s", "f12", (9, 0x53), (0, 0x7B)),
    ],
)
def test_arbitrary_hotkeys_normalize_and_parse(raw_san, raw_res, expected_san, expected_res, vk_san, vk_res):
    res = PrivacySanitizer.normalize_hotkeys(raw_san, raw_res)
    assert res == {"sanitize": expected_san, "restore": expected_res}
    scan = lambda k: ord(k.upper()) if k.isalnum() else -1
    assert parse_hotkey(res["sanitize"], scan) == vk_san
    assert parse_hotkey(res["restore"], scan) == vk_res


@pytest.mark.parametrize("bad", ["a", "space", "esc", "escape", ",", "`", "ctrl+", "ctrl++", "f25", "ctrl+s,r"])
def test_invalid_or_bare_hotkeys_rejected(bad):
    with pytest.raises(ValueError):
        PrivacySanitizer.normalize_hotkeys(bad, "alt+r")


def test_normalize_tk_key_event_handles_modifiers_punctuation_numpad_and_shifted_symbols():
    assert normalize_tk_key_event(SimpleNamespace(keysym="Control_L", state=0, keycode=0)) == (["ctrl"], None, True)
    assert normalize_tk_key_event(SimpleNamespace(keysym="Win_L", state=0x0004, keycode=0)) == (["ctrl", "win"], None, True)
    assert normalize_tk_key_event(SimpleNamespace(keysym="grave", state=0x0004, keycode=0xC0)) == (["ctrl"], "`", False)
    assert normalize_tk_key_event(SimpleNamespace(keysym="colon", state=0x0005, keycode=0xBA)) == (["ctrl", "shift"], ";", False)
    assert normalize_tk_key_event(SimpleNamespace(keysym="exclam", state=0x0005, keycode=0x31)) == (["ctrl", "shift"], "1", False)
    # Windows Tk sets 0x0008 when NumLock is ON and 0x20000 for Alt; must NEVER inject bogus ALT.
    assert normalize_tk_key_event(SimpleNamespace(keysym="F9", state=0x0008, keycode=0x78), is_windows=True) == ([], "f9", False)
    assert normalize_tk_key_event(SimpleNamespace(keysym="Left", state=0x000C, keycode=0x25), is_windows=True) == (["ctrl"], "left", False)
    assert normalize_tk_key_event(SimpleNamespace(keysym="s", state=0x000D, keycode=0x53), is_windows=True) == (["ctrl", "shift"], "s", False)
    assert normalize_tk_key_event(SimpleNamespace(keysym="KP_Add", state=0x20008, keycode=0x6B), is_windows=True) == (["alt"], "num_add", False)
    assert normalize_tk_key_event(SimpleNamespace(keysym="Left", state=0x2000C, keycode=0x25), is_windows=True) == (["ctrl", "alt"], "left", False)
    # Non-Windows (X11/macOS) continues treating Mod1 (0x0008) as Alt.
    assert normalize_tk_key_event(SimpleNamespace(keysym="Left", state=0x000C, keycode=0x25), is_windows=False) == (["ctrl", "alt"], "left", False)
    assert normalize_tk_key_event(SimpleNamespace(keysym="KP_Add", state=0x0008, keycode=0x6B), is_windows=False) == (["alt"], "num_add", False)
    assert format_hotkey_display("ctrl+shift+`") == "CTRL + SHIFT + `"


def test_recorder_live_preview_auto_apply_and_quick_guide_sync(tmp_path: Path):
    root, win, sanitizer = _make_win(tmp_path)
    applied = []
    win.on_reload_hotkeys = lambda cand: (sanitizer.set_hotkeys(cand["sanitize"], cand["restore"]), applied.append(dict(cand)), True)[-1]
    numlock_bit = 0x0008 if sys.platform == "win32" else 0
    try:
        # 1. Start recording on sanitize -> live modifier preview -> capture ctrl+` (with NumLock bit on Windows)
        win._start_hotkey_recording("sanitize")
        assert win._recording_target == "sanitize"
        win._on_hotkey_keypress(SimpleNamespace(keysym="Control_L", state=numlock_bit, keycode=0x11))
        assert win.combo_hk_sanitize._pill_btn.cget("text") == "CTRL + ..."

        # Bare unmodified letter must stay in recording mode with status hint
        win._on_hotkey_keypress(SimpleNamespace(keysym="a", state=numlock_bit, keycode=0x41))
        assert win._recording_target == "sanitize"

        # Capture ctrl+` -> auto-applies & updates Quick Guide, hero button, workflow, and empty vault hint
        win._on_hotkey_keypress(SimpleNamespace(keysym="grave", state=0x0004 | numlock_bit, keycode=0xC0))
        assert win._recording_target is None
        assert sanitizer.hotkeys["sanitize"] == "ctrl+`"
        assert applied[-1] == {"sanitize": "ctrl+`", "restore": "alt+r"}
        assert "CTRL+`" in win.guide_box.get("1.0", "end-1c")
        assert "CTRL+`" in win.btn_hero_san.cget("text")
        assert "CTRL+`" in win.lbl_workflow.cget("text")

        # 2. Capture ctrl+alt+left (0x20004) for restore -> Quick Guide shows both custom chords
        win._start_hotkey_recording("restore")
        win._on_hotkey_keypress(SimpleNamespace(keysym="Left", state=0x20004, keycode=0x25))
        assert sanitizer.hotkeys == {"sanitize": "ctrl+`", "restore": "ctrl+alt+left"}
        guide_text = win.guide_box.get("1.0", "end-1c")
        assert "CTRL+`" in guide_text
        assert "CTRL+ALT+LEFT" in guide_text

        # 3. Swapped Alt+R / Alt+S must render both cleanly without single-pass collision
        win.combo_hk_sanitize.set("alt+r")
        win.combo_hk_restore.set("alt+s")
        win._save_and_apply_hotkeys()
        swapped_guide = win.guide_box.get("1.0", "end-1c")
        assert "脱敏 (ALT+R)" in swapped_guide
        assert "还原 (ALT+S)" in swapped_guide

        # 4. Manual inline edit: clicking ✏️ toggles to ✓; clicking ✓ saves immediately and restores ✏️
        win.btn_edit_san.invoke()
        assert win.combo_hk_sanitize._editing is True
        assert win.btn_edit_san.cget("text") == "✓"
        win.combo_hk_sanitize._entry.delete(0, "end")
        win.combo_hk_sanitize._entry.insert(0, "f9")
        win.btn_edit_san.invoke()
        assert win.combo_hk_sanitize._editing is False
        assert win.btn_edit_san.cget("text") == "✏️"
        assert sanitizer.hotkeys["sanitize"] == "f9"
        assert win.combo_hk_sanitize._pill_btn.cget("text") == "F9"
        assert "F9" in win.guide_box.get("1.0", "end-1c")

        # 5. Pencil edit + Enter commit also works cleanly and restores ✏️
        win.btn_edit_res.invoke()
        assert win.combo_hk_restore._editing is True
        assert win.btn_edit_res.cget("text") == "✓"
        win.combo_hk_restore._entry.delete(0, "end")
        win.combo_hk_restore._entry.insert(0, "ctrl+shift+j")
        win.combo_hk_restore._handle_entry_return()
        assert win.combo_hk_restore._editing is False
        assert win.btn_edit_res.cget("text") == "✏️"
        assert sanitizer.hotkeys["restore"] == "ctrl+shift+j"
        assert win.combo_hk_restore._pill_btn.cget("text") == "CTRL + SHIFT + J"

        # 6. Pencil edit + Reset Default closes editing box cleanly, restores ✏️ and resets alt+s / alt+r
        win.btn_edit_san.invoke()
        assert win.combo_hk_sanitize._editing is True
        assert win.btn_edit_san.cget("text") == "✓"
        win.combo_hk_sanitize._entry.delete(0, "end")
        win.combo_hk_sanitize._entry.insert(0, "ctrl+1")
        win._reset_default_hotkeys()
        assert win.combo_hk_sanitize._editing is False
        assert win.btn_edit_san.cget("text") == "✏️"
        assert sanitizer.hotkeys == {"sanitize": "alt+s", "restore": "alt+r"}
        assert win.combo_hk_sanitize._pill_btn.cget("text") == "ALT + S"
        assert win.combo_hk_restore._pill_btn.cget("text") == "ALT + R"

        # 7. Esc cancel or switching page away from Settings restores ✏️ cleanly
        win.btn_edit_san.invoke()
        assert win.combo_hk_sanitize._editing is True and win.btn_edit_san.cget("text") == "✓"
        win.combo_hk_sanitize._handle_entry_escape()
        assert win.combo_hk_sanitize._editing is False and win.btn_edit_san.cget("text") == "✏️"
        win._show_page("settings")
        win.btn_edit_san.invoke()
        assert win.combo_hk_sanitize._editing is True
        win._show_page("sandbox")
        assert win.combo_hk_sanitize._editing is False
        assert win.btn_edit_san.cget("text") == "✏️"
    finally:
        _destroy_root(root)


def test_recorder_reverts_box_when_registration_fails(tmp_path: Path, monkeypatch):
    root, win, sanitizer = _make_win(tmp_path)
    win.on_reload_hotkeys = lambda _cand: False
    monkeypatch.setattr("src.gui.messagebox.showwarning", lambda *args, **kwargs: None)
    try:
        win._start_hotkey_recording("sanitize")
        win._on_hotkey_keypress(SimpleNamespace(keysym="grave", state=0x0004, keycode=0xC0))
        assert sanitizer.hotkeys["sanitize"] == "alt+s"
        assert win.combo_hk_sanitize.get() == "alt+s"
        assert win.combo_hk_sanitize._pill_btn.cget("text") == "ALT + S"
    finally:
        _destroy_root(root)


def test_reset_default_falls_back_cleanly_when_alt_r_is_occupied(tmp_path: Path, monkeypatch):
    root, win, sanitizer = _make_win(tmp_path, hotkeys={"sanitize": "ctrl+a", "restore": "ctrl+shift+b"})
    conflict_state = {"key": None}
    warnings = []
    monkeypatch.setattr("src.gui.messagebox.showwarning", lambda *a, **kw: warnings.append((a, kw)))

    def _reload(cand):
        if cand["restore"] == "alt+r":
            conflict_state["key"] = "alt+r"
            return False
        conflict_state["key"] = None
        sanitizer.set_hotkeys(cand["sanitize"], cand["restore"])
        return True

    win.on_reload_hotkeys = _reload
    win.get_last_hotkey_conflict = lambda: conflict_state["key"]
    try:
        win._reset_default_hotkeys()
        assert not warnings
        assert sanitizer.hotkeys == {"sanitize": "alt+s", "restore": "ctrl+shift+r"}
        assert win.combo_hk_sanitize._pill_btn.cget("text") == "ALT + S"
        assert win.combo_hk_restore._pill_btn.cget("text") == "CTRL + SHIFT + R"
        assert "CTRL+SHIFT+R" in win.guide_box.get("1.0", "end-1c")
        assert "ALT+R" in win.status_var.get()
    finally:
        _destroy_root(root)


def test_save_and_apply_reports_specific_occupied_hotkey_name(tmp_path: Path, monkeypatch):
    root, win, sanitizer = _make_win(tmp_path)
    warnings = []
    monkeypatch.setattr("src.gui.messagebox.showwarning", lambda *a, **kw: warnings.append(a))
    win.on_reload_hotkeys = lambda _cand: False
    win.get_last_hotkey_conflict = lambda: "alt+r"
    try:
        win._toggle_manual_hotkey_edit("restore")
        win.combo_hk_restore._entry.delete(0, "end")
        win.combo_hk_restore._entry.insert(0, "alt+r")
        win._save_and_apply_hotkeys()
        assert warnings
        assert "ALT+R" in warnings[0][1]
        assert "ALT+R" in win.status_var.get()
        assert win.combo_hk_restore._editing is False
    finally:
        _destroy_root(root)


def test_startup_hotkey_registration_auto_fallbacks_when_default_conflicts(tmp_path: Path, monkeypatch):
    from src.main import SanitizerTrayApp
    from src import main as app_module

    example = tmp_path / "example.json"
    example.write_text(json.dumps({"language": "en", "hotkeys": {"sanitize": "alt+s", "restore": "alt+r"}}), encoding="utf-8")
    sanitizer = PrivacySanitizer(tmp_path / "config.json", example)
    app = SanitizerTrayApp(sanitizer=sanitizer)
    monkeypatch.setattr(app_module.platform, "system", lambda: "Windows")

    def _mock_reg(hk=None):
        target = sanitizer.hotkeys if hk is None else hk
        if target["restore"] == "alt+r":
            app._last_hotkey_conflict = "alt+r"
            return False
        app._last_hotkey_conflict = None
        return True

    monkeypatch.setattr(app, "register_hotkeys", _mock_reg)
    status = app._register_startup_hotkeys()
    assert status is not None and "ALT+R" in status and "CTRL+SHIFT+R" in status
    assert sanitizer.hotkeys == {"sanitize": "alt+s", "restore": "ctrl+shift+r"}

    # Custom user bindings stay fail-closed and report exact conflicting chord
    sanitizer.set_hotkeys("ctrl+shift+j", "alt+r")
    status_custom = app._register_startup_hotkeys()
    assert status_custom is not None and "ALT+R" in status_custom
    assert sanitizer.hotkeys == {"sanitize": "ctrl+shift+j", "restore": "alt+r"}
