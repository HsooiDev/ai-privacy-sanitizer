"""Comprehensive verification tests for AI Privacy Sanitizer v0.6.0 upgrades."""

import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk

import customtkinter as ctk
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import __version__
from src.file_batch import process_batch_paths
from src.gui import _ModernControlCenter, _StableCTk
from src.main import LastClipboardSanitizeRecord, SanitizerTrayApp
from src.regex_safety import (
    RegexSafetyError,
    RegexTimeoutError,
    validate_custom_regex,
)
from src.rules import is_high_entropy_secret, shannon_entropy
from src.sanitizer import PrivacySanitizer
from src.scanner import format_scan_report, mask_secret_for_terminal, scan_git_staged, scan_path
from src.win_drop import WindowsFileDropTarget
from src.windows_clipboard_watcher import WindowsClipboardWatcher


REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_sanitizer(tmp_path: Path, extra_cfg: dict | None = None) -> PrivacySanitizer:
    tmp_path.mkdir(parents=True, exist_ok=True)
    example = tmp_path / "example.json"
    base = {
        "language": "en",
        "theme": "dark",
        "hotkeys": {"sanitize": "alt+s", "restore": "ctrl+shift+r"},
        "custom_dictionary": {"COMPANY": ["Acme Global Sdn Bhd"]},
    }
    if extra_cfg:
        base.update(extra_cfg)
    example.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return PrivacySanitizer(tmp_path / "config.json", example)


def _new_tk_window(sanitizer: PrivacySanitizer, **kwargs):
    ctk.set_appearance_mode("Dark")
    try:
        root = _StableCTk()
    except tk.TclError as exc:
        if "display" in str(exc).lower():
            pytest.skip("Tk display unavailable")
        raise
    root.geometry("980x700+20000+20000")
    root.deiconify()
    win = _ModernControlCenter(root, sanitizer, **kwargs)
    root.update()
    return root, win


def _close_tk(root: tk.Misc) -> None:
    for timer in root.tk.splitlist(root.tk.call("after", "info")):
        root.tk.call("after", "cancel", timer)
    root.destroy()


# ---------------------------------------------------------------------------
# Feature 1: Global Hotkey Status Visibility & Auto-Shift Conflict Fix
# ---------------------------------------------------------------------------

def test_tray_hotkey_status_and_auto_fix_conflict(tmp_path: Path, monkeypatch) -> None:
    sanitizer = _make_sanitizer(tmp_path)
    app = SanitizerTrayApp(sanitizer)

    def fake_register(hotkeys=None):
        target = hotkeys or app.sanitizer.hotkeys
        san_hk = target.get("sanitize", "alt+s")
        if san_hk in ("alt+s", "ctrl+alt+s"):
            app._last_hotkey_conflict = san_hk
            app._hotkey_status = {
                "state": "conflict",
                "conflict_key": san_hk,
                "bound": {},
                "configured": dict(target),
            }
            return False
        app._last_hotkey_conflict = None
        app._hotkey_status = {
            "state": "ready",
            "conflict_key": None,
            "bound": dict(target),
            "configured": dict(target),
        }
        return True

    monkeypatch.setattr(app, "register_hotkeys", fake_register)
    msg = app._register_startup_hotkeys()
    assert msg is not None
    st = app.get_hotkey_status()
    assert st["state"] == "conflict"
    assert st["conflict_key"] == "alt+s"

    fixed, new_hotkeys, conflict_key = app.auto_fix_hotkey_conflict()
    assert fixed is True
    assert conflict_key == "alt+s"
    assert new_hotkeys["sanitize"] != "alt+s"
    assert sanitizer.hotkeys["sanitize"] == new_hotkeys["sanitize"]
    st_after = app.get_hotkey_status()
    assert st_after["state"] == "ready"
    assert st_after["conflict_key"] is None


def test_tray_hotkey_auto_fix_rolls_back_when_all_candidates_busy(tmp_path: Path, monkeypatch) -> None:
    sanitizer = _make_sanitizer(tmp_path)
    app = SanitizerTrayApp(sanitizer)

    def always_conflict(hotkeys=None):
        target = hotkeys or app.sanitizer.hotkeys
        conflict_hk = target.get("sanitize", "alt+s")
        app._last_hotkey_conflict = conflict_hk
        app._hotkey_status = {
            "state": "conflict",
            "conflict_key": conflict_hk,
            "bound": {},
            "configured": dict(target),
        }
        return False

    monkeypatch.setattr(app, "register_hotkeys", always_conflict)
    app.register_hotkeys()
    fixed, current, conflict = app.auto_fix_hotkey_conflict()
    assert fixed is False
    assert conflict == "alt+s"
    assert current["sanitize"] == "alt+s"
    assert sanitizer.hotkeys["sanitize"] == "alt+s"


def test_gui_e2e_hotkey_conflict_badges_and_auto_fix_journey(tmp_path: Path) -> None:
    sanitizer = _make_sanitizer(tmp_path)
    state = {"fixed": False}

    def get_status():
        if not state["fixed"]:
            return {
                "state": "conflict",
                "conflict_key": "alt+s",
                "bound": {},
                "configured": {"sanitize": "alt+s", "restore": "ctrl+shift+r"},
            }
        return {
            "state": "ready",
            "conflict_key": None,
            "bound": {"sanitize": "ctrl+alt+s", "restore": "ctrl+shift+r"},
            "configured": {"sanitize": "ctrl+alt+s", "restore": "ctrl+shift+r"},
        }

    def do_fix():
        sanitizer.set_hotkeys("ctrl+alt+s", "ctrl+shift+r")
        state["fixed"] = True
        return True, dict(sanitizer.hotkeys), "alt+s"

    root, win = _new_tk_window(sanitizer, get_hotkey_status=get_status, on_auto_fix_hotkeys=do_fix)
    try:
        assert "alt+s" in win.lbl_side_hk_status.cget("text").lower()
        assert win.btn_side_hk_fix.winfo_manager() == "pack"
        assert win.btn_home_hk_fix.winfo_manager() == "pack"

        win._show_page("settings")
        root.update()
        assert win.btn_hk_autofix.winfo_manager() == "pack"

        # Click Home Auto-Fix button just like a real user
        win._show_page("home")
        root.update()
        win.btn_home_hk_fix.invoke()
        root.update()

        assert state["fixed"] is True
        assert sanitizer.hotkeys["sanitize"] == "ctrl+alt+s"
        assert win.btn_side_hk_fix.winfo_manager() == ""
        assert win.btn_home_hk_fix.winfo_manager() == ""

        win._toggle_language()
        root.update()
        side_txt = win.lbl_side_hk_status.cget("text")
        assert ("Ready" in side_txt) or ("就绪" in side_txt)
    finally:
        _close_tk(root)


# ---------------------------------------------------------------------------
# Feature 2: Custom Regex Rules, ReDoS Guard, Partial Group & GUI E2E
# ---------------------------------------------------------------------------

def test_custom_regex_partial_group_and_redos_protection(tmp_path: Path) -> None:
    sanitizer = _make_sanitizer(tmp_path)

    # Reject syntax errors, zero-width matches, and catastrophic nested quantifiers
    with pytest.raises(RegexSafetyError):
        validate_custom_regex("(unclosed[abc")
    with pytest.raises(RegexSafetyError):
        validate_custom_regex("(?=abc)")
    for evil in ("(a+)+$", "([a-zA-Z]+)*b", "(a|aa)+$"):
        t0 = time.monotonic()
        with pytest.raises((RegexSafetyError, RegexTimeoutError)):
            validate_custom_regex(evil)
        assert (time.monotonic() - t0) < 1.5

    # Safe partial capture group (?P<secret>...)
    sanitizer.add_custom_regex_rule(
        name="internal_order",
        pattern=r"ORDER-(?P<secret>\d{6,10})",
        category="ORDER_ID",
        placeholder_template="[{category}_{index}]",
        enabled=True,
    )
    src_text = "Track ORDER-8842109 and repeat ORDER-8842109 safely."
    san = sanitizer.sanitize(src_text)
    assert san.total_count == 2
    assert san.sanitized_text == "Track ORDER-[ORDER_ID_1] and repeat ORDER-[ORDER_ID_1] safely."
    res = sanitizer.restore(san.sanitized_text)
    assert res.restored_text == src_text

    # dictionary_only import merges custom_regex_rules safely
    export_path = tmp_path / "exported_cfg.json"
    sanitizer.export_config(export_path)
    sanitizer2 = _make_sanitizer(tmp_path / "s2")
    sanitizer2.import_config(export_path, dictionary_only=True)
    rules2 = sanitizer2.get_custom_regex_rules()
    assert any(r["name"] == "internal_order" for r in rules2)

    # Toggle off & back on
    assert sanitizer.set_custom_regex_rule_enabled("internal_order", False)
    assert sanitizer.sanitize("Track ORDER-8842109").total_count == 0
    assert sanitizer.set_custom_regex_rule_enabled("internal_order", True)
    assert sanitizer.sanitize("Track ORDER-8842109").total_count == 1
    assert sanitizer.remove_custom_regex_rule("internal_order")


def test_gui_e2e_custom_regex_crud_and_live_validation(tmp_path: Path, monkeypatch) -> None:
    sanitizer = _make_sanitizer(tmp_path)
    warnings = []
    monkeypatch.setattr("src.gui.messagebox.showwarning", lambda title, msg, **_kw: warnings.append((title, msg)))

    root, win = _new_tk_window(sanitizer)
    try:
        win._show_page("dict")
        win._show_dict_submode("regex")
        root.update()

        # Enter dangerous ReDoS pattern -> live test rejects and Add does not persist
        win.entry_regex_name.insert(0, "bad_redos")
        win.entry_regex_pattern.insert(0, "(a+)+$")
        win._on_regex_live_test_changed()
        root.update()
        assert "❌" in win.lbl_regex_test_result.cget("text")
        win.btn_add_regex.invoke()
        root.update()
        assert sanitizer.get_custom_regex_rules() == []
        assert len(warnings) == 1

        # Enter valid (?P<secret>...) pattern & live test text
        win.entry_regex_name.delete(0, "end")
        win.entry_regex_name.insert(0, "invoice_id")
        win.entry_regex_pattern.delete(0, "end")
        win.entry_regex_pattern.insert(0, r"INV-(?P<secret>\d{6})")
        win.entry_regex_cat.delete(0, "end")
        win.entry_regex_cat.insert(0, "INVOICE")
        win.entry_regex_test.delete(0, "end")
        win.entry_regex_test.insert(0, "Pay INV-774411 now")
        win._on_regex_live_test_changed()
        root.update()
        live_msg = win.lbl_regex_test_result.cget("text")
        assert "✅" in live_msg and "INV-[INVOICE_1]" in live_msg

        win.btn_add_regex.invoke()
        root.update()
        assert len(sanitizer.get_custom_regex_rules()) == 1
        assert win.custom_regex_scroll.winfo_children()

        # Toggle & delete via GUI handlers
        win._toggle_custom_regex_from_gui("invoice_id", False)
        assert sanitizer.get_custom_regex_rules()[0]["enabled"] is False
        win._remove_custom_regex_from_gui("invoice_id")
        assert sanitizer.get_custom_regex_rules() == []
    finally:
        _close_tk(root)


# ---------------------------------------------------------------------------
# Feature 3: Batch Multi-File / Folder Sanitize & Restore + Win32 Drop Target
# ---------------------------------------------------------------------------

def test_batch_folder_sanitize_shared_vault_and_restore(tmp_path: Path) -> None:
    sanitizer = _make_sanitizer(tmp_path)
    src_dir = tmp_path / "logs_bundle"
    (src_dir / "nested").mkdir(parents=True)
    shared_ip = "192.168.42.99"
    shared_key = "ghp_0123456789abcdef0123456789abcdef0123"
    (src_dir / ".env").write_text(f"API_KEY={shared_key}\nDB_HOST={shared_ip}\n", encoding="utf-8")
    (src_dir / "nested" / "app.log").write_text(
        f"GET {shared_ip}/health auth={shared_key}\n", encoding="utf-8"
    )
    (src_dir / "ignored.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

    san_res = process_batch_paths(sanitizer, [src_dir], mode="sanitize")
    assert len(san_res.processed_files) == 2
    assert san_res.total_hits >= 4
    out_dir = Path(san_res.output_root)
    assert out_dir != src_dir
    # Originals untouched
    assert shared_key in (src_dir / ".env").read_text(encoding="utf-8")

    # Cross-file shared SessionVault produces identical placeholders without double-nesting single dir
    env_san = (out_dir / ".env").read_text(encoding="utf-8")
    log_san = (out_dir / "nested" / "app.log").read_text(encoding="utf-8")
    assert not (out_dir / "logs_bundle").exists()
    assert shared_key not in env_san and shared_ip not in log_san
    env_key_tag = env_san.splitlines()[0].split("=", 1)[1]
    assert env_key_tag in log_san

    # Folder restore produces restored copies matching original content directly inside output_root
    res_out = process_batch_paths(sanitizer, [out_dir], mode="restore")
    assert len(res_out.processed_files) == 2
    rest_dir = Path(res_out.output_root)
    assert (rest_dir / ".env").read_text(encoding="utf-8") == (src_dir / ".env").read_text(encoding="utf-8")
    assert (rest_dir / "nested" / "app.log").read_text(encoding="utf-8") == (src_dir / "nested" / "app.log").read_text(encoding="utf-8")


def test_win32_drop_target_mock_and_gui_e2e_drop_flow(tmp_path: Path) -> None:
    class FakeDropAPI:
        def __init__(self, paths):
            self.paths = [Path(p) for p in paths]
            self.accepted = []
            self.extracted = []
            self.prev_proc = 0x1234

        def get_top_hwnd(self, widget_id: int) -> int:
            return widget_id + 100

        def drag_accept_files(self, hwnd: int, accept: bool) -> None:
            self.accepted.append((hwnd, accept))

        def set_wndproc(self, hwnd: int, _proc_ptr) -> int:
            old = self.prev_proc
            self.prev_proc = 0x5678
            return old

        def call_wndproc(self, _prev: int, _hwnd: int, _msg: int, _wp: int, _lp: int) -> int:
            return 0

        def extract_drop_paths(self, hdrop: int):
            self.extracted.append(hdrop)
            return list(self.paths)

    class DummyRoot:
        def winfo_id(self):
            return 4242

        def after(self, _ms, fn):
            fn()

    delivered = []
    api = FakeDropAPI(["C:\\work\\隐私文件.env", "D:\\logs\\app.log"])
    target = WindowsFileDropTarget(DummyRoot(), lambda p: delivered.append(p), api=api)
    assert target.attach() is True
    assert (4342, True) in api.accepted
    target.handle_drop_message(999)
    assert delivered == [[Path("C:\\work\\隐私文件.env"), Path("D:\\logs\\app.log")]]
    assert api.extracted == [999]
    target.detach()
    assert (4342, False) in api.accepted

    # GUI E2E handle_dropped_paths sanitize & lbl_batch_result update
    sanitizer = _make_sanitizer(tmp_path)
    sample = tmp_path / "sample.json"
    sample.write_text('{"token": "ghp_0123456789abcdef0123456789abcdef0123"}', encoding="utf-8")
    root, win = _new_tk_window(sanitizer)
    try:
        win.handle_dropped_paths([str(sample)], mode="sanitize")
        root.update()
        msg_text = win.lbl_batch_result.cget("text")
        assert msg_text != "" and ("1" in msg_text)
    finally:
        _close_tk(root)


# ---------------------------------------------------------------------------
# Feature 4: Home Recent Clipboard Diff Card + Allowlist & Rerun
# ---------------------------------------------------------------------------

def test_recent_clipboard_record_and_allowlist_rerun(tmp_path: Path, monkeypatch) -> None:
    sanitizer = _make_sanitizer(tmp_path)
    app = SanitizerTrayApp(sanitizer)

    clip_state = {"text": "ping Acme Global Sdn Bhd with 10.20.30.40"}
    monkeypatch.setattr("src.main._safe_clipboard_paste", lambda: clip_state["text"])

    def fake_write(val, **_kw):
        clip_state["text"] = val
        return True

    def fake_replace_if_unchanged(expected, new_val):
        if clip_state["text"] != expected:
            return False
        clip_state["text"] = new_val
        return True

    monkeypatch.setattr("src.main._safe_clipboard_copy", fake_write)
    monkeypatch.setattr("src.main._replace_clipboard_if_unchanged", fake_replace_if_unchanged)

    app.sanitize_clipboard()
    rec = app.get_last_clipboard_record()
    assert rec is not None
    assert rec.total_count == 2
    assert "Acme Global Sdn Bhd" not in clip_state["text"]

    # Clicking Allowlist & Rerun silently updates clipboard when unchanged
    ok, _msg = app.allowlist_and_rerun_last_clipboard("Acme Global Sdn Bhd")
    assert ok is True
    assert "Acme Global Sdn Bhd" in clip_state["text"]
    assert "10.20.30.40" not in clip_state["text"]

    # If user copied something else meanwhile, allowlist saves safely without overwriting clipboard
    clip_state["text"] = "user copied unrelated text"
    ok2, _msg2 = app.allowlist_and_rerun_last_clipboard("10.20.30.40")
    assert ok2 is False
    assert clip_state["text"] == "user copied unrelated text"
    assert "10.20.30.40" in sanitizer.get_allowlist()

    # GUI E2E render with reveal toggle + allowlist button click
    called = []
    stripe_dummy = "sk_live_" + "TEST000011112222333344445555"
    rec_gui = LastClipboardSanitizeRecord(
        raw_text=f"secret={stripe_dummy}",
        sanitized_text="secret=[STRIPE_KEY_1]",
        source="cruise",
        total_count=1,
        items=[("[STRIPE_KEY_1]", stripe_dummy, "STRIPE_KEY")],
    )
    root, win = _new_tk_window(
        sanitizer,
        get_last_clipboard_record=lambda: rec_gui,
        on_allowlist_and_rerun=lambda v: (called.append(v), (True, "ok"))[1],
    )
    try:
        def row_texts():
            out = []
            pending = [win.home_recent_items]
            while pending:
                w = pending.pop()
                if isinstance(w, ctk.CTkLabel):
                    out.append(w.cget("text"))
                pending.extend(w.winfo_children())
            return out

        masked = "\n".join(row_texts())
        assert stripe_dummy not in masked
        assert "•" in masked

        win.var_recent_reveal.set(True)
        win._on_toggle_recent_reveal()
        root.update()
        revealed = "\n".join(row_texts())
        assert "sk_live_" in revealed

        win._allowlist_and_rerun_from_recent(stripe_dummy)
        assert called == [stripe_dummy]
    finally:
        _close_tk(root)


# ---------------------------------------------------------------------------
# Feature 5: Structured Config, High Entropy Fallback & Cloud Rules
# ---------------------------------------------------------------------------

def test_cloud_rules_structured_configs_and_entropy_fallback(tmp_path: Path) -> None:
    sanitizer = _make_sanitizer(tmp_path)
    linear_dummy = "lin_api" + "_abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    dbx_dummy = "dapi" + "0123456789abcdef0123456789abcdef"
    payload = "\n".join([
        'SUPA_TOKEN="sbp_0123456789abcdef0123456789abcdef01234567"',
        "STRIPE_WH=whsec_abcdefghijklmnopqrstuvwxyz012345",
        f"LINEAR_KEY={linear_dummy}",
        f"DBX={dbx_dummy}",
        "TG=123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
        "AZURE_CONN=DefaultEndpointsProtocol=https;AccountName=demo;AccountKey=abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH1234567890+ABCDEFGH=;EndpointSuffix=core.windows.net",
        'CF_API_TOKEN="cf_v1_XyZ9876543210abcdef1234567890abcdef1234"',
        "url=https://api.example.com/v1?sig=AbCdEfGhIjKlMnOpQrStUvWxYz0123456789%2B%2F%3D",
        "db_password: myUltraSecretDbPassword_99",
    ])
    san = sanitizer.sanitize(payload)
    for sensitive in (
        "sbp_0123456789abcdef0123456789abcdef01234567",
        "whsec_abcdefghijklmnopqrstuvwxyz012345",
        linear_dummy,
        dbx_dummy,
        "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
        "myUltraSecretDbPassword_99",
    ):
        assert sensitive not in san.sanitized_text
    assert sanitizer.restore(san.sanitized_text).restored_text == payload

    # High-entropy fallback: catches random RHS secrets, spares ordinary English prose
    assert shannon_entropy("k9QmPx7Zt3Lw8Bv2Nc6Yr4Jf") > 3.6
    assert is_high_entropy_secret("k9QmPx7Zt3Lw8Bv2Nc6Yr4Jf") is True
    assert is_high_entropy_secret("Malaysia_Developer_Preview") is False

    prose_and_secret = (
        "Please keep this normal English documentation sentence intact. "
        'APP_BUILD_FINGERPRINT="k9QmPx7Zt3Lw8Bv2Nc6Yr4Jf9Zp2"'
    )
    san_off = sanitizer.sanitize(prose_and_secret, entropy_enabled=False)
    assert "k9QmPx7Zt3Lw8Bv2Nc6Yr4Jf9Zp2" in san_off.sanitized_text

    san_on = sanitizer.sanitize(prose_and_secret, entropy_enabled=True)
    assert "k9QmPx7Zt3Lw8Bv2Nc6Yr4Jf9Zp2" not in san_on.sanitized_text
    assert "normal English documentation sentence" in san_on.sanitized_text
    assert sanitizer.restore(san_on.sanitized_text).restored_text == prose_and_secret

    sanitizer.set_entropy_detection_enabled(True)
    assert sanitizer.entropy_detection_enabled is True


# ---------------------------------------------------------------------------
# Feature 6: Windows Native Clipboard Event Watcher
# ---------------------------------------------------------------------------

def test_windows_clipboard_watcher_lifecycle_and_dispatch() -> None:
    class FakeClipAPI:
        def __init__(self):
            self.seq = 10
            self.added = []
            self.removed = []
            self.destroyed = []
            self.closed = []

        def create_message_window(self, _class_name, _wndproc_cb) -> int:
            return 7777

        def def_window_proc(self, _hwnd, _msg, _wp, _lp) -> int:
            return 0

        def add_listener(self, hwnd: int) -> bool:
            self.added.append(hwnd)
            return True

        def remove_listener(self, hwnd: int) -> bool:
            self.removed.append(hwnd)
            return True

        def get_sequence_number(self) -> int:
            return self.seq

        def get_message(self, _message) -> int:
            return 0

        def translate_and_dispatch(self, _message) -> None:
            pass

        def post_close(self, hwnd: int) -> bool:
            self.closed.append(hwnd)
            return True

        def destroy_window(self, hwnd: int) -> bool:
            self.destroyed.append(hwnd)
            return True

        def post_quit(self) -> None:
            pass

    events = []
    api = FakeClipAPI()
    watcher = WindowsClipboardWatcher(lambda: events.append(api.seq), api=api)
    watcher.start()
    assert api.added == [7777]
    if watcher._thread is not None:
        watcher._thread.join(2)
    assert api.removed == [7777]

    # Duplicate sequence number ignored; new sequence number triggers callback
    watcher._dispatch_update()
    assert events == [10]
    watcher._dispatch_update()
    assert events == [10]
    api.seq = 11
    watcher._dispatch_update()
    assert events == [10, 11]

    watcher.stop()
    assert watcher.active is False


# ---------------------------------------------------------------------------
# Feature 7: Browser Extension Manifest, ProseMirror/Lexical & Shadow Restore Pill
# ---------------------------------------------------------------------------

def test_browser_extension_v060_manifest_and_dom_runtime() -> None:
    manifest = json.loads((REPO_ROOT / "browser-extension" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == __version__
    assert manifest["permissions"] == []
    matches = " ".join(manifest["content_scripts"][0]["matches"])
    for host in (
        "perplexity.ai",
        "grok.com",
        "x.com",
        "copilot.microsoft.com",
        "github.com",
        "aistudio.google.com",
        "chat.mistral.ai",
    ):
        assert host in matches

    node_script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function makeEl(tag) {
  return {
    tagName: String(tag || 'DIV').toUpperCase(),
    style: {},
    children: [],
    listeners: {},
    attributes: {},
    dataset: {},
    isContentEditable: false,
    textContent: '',
    innerText: '',
    value: '',
    attachShadow() {
      const root = { children: [], appendChild(c) { this.children.push(c); return c; } };
      this.shadowRoot = root;
      return root;
    },
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; },
    remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter(x => x !== this); },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    dispatchEvent(ev) {
      const list = this.listeners[ev.type] || [];
      for (const fn of list) fn(ev);
      if (ev.type === 'paste' && ev.clipboardData && this.isContentEditable) {
        this.textContent += ev.clipboardData.getData('text/plain');
      }
      return true;
    },
    focus() {},
    closest(sel) {
      if (sel.includes('pre') && (this.tagName === 'PRE' || this.tagName === 'CODE')) return this._pre || this;
      return null;
    },
    getBoundingClientRect() { return { top: 40, left: 40, right: 340, bottom: 140, width: 300, height: 100 }; },
  };
}

let copiedClipboard = '';
let msgHandler = null;
const docBody = makeEl('body');
const doc = {
  body: docBody,
  documentElement: docBody,
  listeners: {},
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
  createElement(tag) { return makeEl(tag); },
  queryCommandSupported() { return false; },
  execCommand() { throw new Error('execCommand must not be relied on solely'); },
  getElementById(id) {
    if (!this._ids) this._ids = {};
    if (!this._ids[id]) this._ids[id] = makeEl('div');
    return this._ids[id];
  }
};

function FakeClipboardEvent(type, opts) {
  this.type = type;
  this.clipboardData = opts && opts.clipboardData;
}
function FakeDataTransfer() {
  this._data = {};
  this.setData = (k, v) => { this._data[k] = v; };
  this.getData = (k) => this._data[k] || '';
}
function FakeInputEvent(type, opts) {
  this.type = type;
  Object.assign(this, opts || {});
}

const ctx = vm.createContext({
  window: null,
  document: doc,
  navigator: {
    language: 'en-US',
    clipboard: { writeText: async (t) => { copiedClipboard = t; } }
  },
  ClipboardEvent: FakeClipboardEvent,
  DataTransfer: FakeDataTransfer,
  InputEvent: FakeInputEvent,
  Event: function(type, opts) { this.type = type; Object.assign(this, opts || {}); },
  chrome: {
    runtime: {
      onMessage: { addListener(fn) { msgHandler = fn; } },
      lastError: null
    },
    tabs: {
      query(_q, cb) { cb([{ id: 1 }]); },
      sendMessage(_id, payload, cb) {
        if (msgHandler) msgHandler(payload, {}, cb);
      }
    }
  },
  setTimeout, clearTimeout,
});
ctx.window = ctx;

vm.runInContext(fs.readFileSync('browser-extension/sanitizer_core.js', 'utf8'), ctx);
vm.runInContext(fs.readFileSync('browser-extension/content.js', 'utf8'), ctx);

// 1. Intercept paste with Linear secret into a contentEditable Lexical/ProseMirror box
const editor = makeEl('div');
editor.isContentEditable = true;
docBody.appendChild(editor);

const sampleSecret = 'lin_api' + '_abcdefghijklmnopqrstuvwxyz0123456789ABCD';
const probeEngine = ctx.SanitizerExtCore.createSessionEngine();
const expectedSanitized = probeEngine.sanitize(sampleSecret).text;
assert.notStrictEqual(expectedSanitized, sampleSecret, 'Core engine must sanitize Linear secret');

let defaultPrevented = false;
const pasteEv = {
  type: 'paste',
  target: editor,
  clipboardData: { getData: () => sampleSecret },
  preventDefault() { defaultPrevented = true; },
  stopPropagation() {}
};
for (const fn of (doc.listeners['paste'] || [])) fn(pasteEv);
assert.strictEqual(defaultPrevented, true, 'Paste with secret must be intercepted synchronously');

const bannerHost = docBody.children.find(c => c.shadowRoot);
assert.ok(bannerHost, 'Shadow DOM paste warning banner should mount');
function findButtons(node, acc = []) {
  if (!node) return acc;
  if (node.tagName === 'BUTTON') acc.push(node);
  for (const ch of (node.children || [])) findButtons(ch, acc);
  return acc;
}
const btns = findButtons(bannerHost.shadowRoot);
assert.ok(btns.length >= 2);
btns[0].listeners['click'][0]();
assert.strictEqual(editor.textContent, expectedSanitized, 'Synthetic paste must insert sanitized tag without execCommand');
assert.ok(!editor.textContent.includes('lin_api_'), 'Plaintext secret must not enter editor');

// 2. Shadow DOM In-Page Restore Pill over <pre> block containing placeholder
const pre = makeEl('pre');
pre.textContent = 'export LINEAR_KEY=' + expectedSanitized;
docBody.appendChild(pre);
for (const fn of (doc.listeners['mouseover'] || [])) fn({ target: pre });
const restoreHost = docBody.children.find(c => c !== bannerHost && c.shadowRoot);
assert.ok(restoreHost, 'In-page Shadow DOM restore pill should appear on <pre> with placeholders');
const restoreBtn = findButtons(restoreHost.shadowRoot)[0];
Promise.resolve(restoreBtn.listeners['click'][0]()).then(() => {
  assert.strictEqual(copiedClipboard, 'export LINEAR_KEY=' + sampleSecret);
  // 3. Popup bilingual EN/ZH toggle via chrome.tabs messaging
  vm.runInContext(fs.readFileSync('browser-extension/popup.js', 'utf8'), ctx);
  assert.ok(doc.getElementById('btnRestore').textContent.includes('Restore'));
  doc.getElementById('btnLang').listeners['click'][0]();
  assert.ok(doc.getElementById('btnRestore').textContent.includes('还原'));
  console.log('EXT_OK');
});
"""
    proc = subprocess.run(
        ["node", "-e", node_script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "EXT_OK" in proc.stdout


# ---------------------------------------------------------------------------
# Feature 8: CLI Read-Only Secret Scanner (--scan / --git-staged)
# ---------------------------------------------------------------------------

def test_cli_readonly_scanner_and_git_staged_never_prints_plaintext(tmp_path: Path) -> None:
    sanitizer = _make_sanitizer(tmp_path)
    secret_a = "ghp_0123456789abcdef0123456789abcdef0123"
    secret_b = "whsec_secret9876543210abcdefghijklmnop"

    repo = tmp_path / "demo_repo"
    repo.mkdir()
    clean_file = repo / "README.txt"
    clean_file.write_text("Nothing confidential here.\n", encoding="utf-8")

    clean_findings, clean_files = scan_path(sanitizer, clean_file)
    assert clean_findings == [] and clean_files == 1

    env_file = repo / ".env"
    env_file.write_text(f"GH_TOKEN={secret_a}\n", encoding="utf-8")
    findings_dir, files_dir = scan_path(sanitizer, repo)
    assert len(findings_dir) == 1
    assert findings_dir[0].line_number == 1
    txt_rep = format_scan_report(findings_dir, files_dir, as_json=False, lang="en")
    json_rep = format_scan_report(findings_dir, files_dir, as_json=True, lang="en")
    assert secret_a not in txt_rep and secret_a not in json_rep
    assert mask_secret_for_terminal(secret_a) != secret_a

    proc_hit = subprocess.run(
        [sys.executable, "-m", "src.main", "--scan", str(repo)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc_hit.returncode == 1
    assert secret_a not in proc_hit.stdout and secret_a not in proc_hit.stderr

    proc_clean = subprocess.run(
        [sys.executable, "-m", "src.main", "--scan", str(clean_file)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc_clean.returncode == 0

    proc_missing = subprocess.run(
        [sys.executable, "-m", "src.main", "--scan", str(repo / "does_not_exist.env")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc_missing.returncode == 2

    # Real temp Git repo --git-staged check (flags staged secret, ignores unstaged file)
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=str(repo), capture_output=True, check=True)
    unstaged = repo / "unstaged.env"
    unstaged.write_text(f"STRIPE_WEBHOOK={secret_b}\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.txt", ".env"], cwd=str(repo), capture_output=True, check=True)

    staged_findings, staged_files = scan_git_staged(sanitizer, repo_dir=repo)
    assert len(staged_findings) == 1
    assert staged_findings[0].file_path == ".env"
    assert secret_a not in format_scan_report(staged_findings, staged_files, as_json=True)


# ---------------------------------------------------------------------------
# Feature 9: Smart App Control Friendly Launchers, Packaging & Optional Signing
# ---------------------------------------------------------------------------

def test_portable_launchers_packaging_manifests_and_ci_optional_signing() -> None:
    vbs = (REPO_ROOT / "run-sanitizer.vbs").read_text(encoding="utf-8")
    bat = (REPO_ROOT / "run-sanitizer.bat").read_text(encoding="utf-8")
    assert "pythonw" in vbs and "-m src.main" in vbs
    assert "-m src.main" in bat

    scoop = json.loads((REPO_ROOT / "packaging" / "scoop" / "ai-privacy-sanitizer.json").read_text(encoding="utf-8"))
    assert scoop["version"] == __version__

    winget = (REPO_ROOT / "packaging" / "winget" / "HsooiDev.AIPrivacySanitizer.yaml").read_text(encoding="utf-8")
    assert f"PackageVersion: {__version__}" in winget

    ci_yml = (REPO_ROOT / ".github" / "workflows" / "ci-build.yml").read_text(encoding="utf-8")
    assert "sync_web_rules.py --check" in ci_yml
    assert "WINDOWS_CODESIGN_PFX_BASE64" in ci_yml
    assert "skipping Authenticode signing" in ci_yml


# ---------------------------------------------------------------------------
# Real-User Edge Cases & Regression Verification
# ---------------------------------------------------------------------------

def test_real_user_regressions_drop_hotkey_cruise_readonly_and_extension(tmp_path: Path, monkeypatch) -> None:
    # 1. Read-only sanitizer NEVER creates missing config.json on disk
    missing_cfg = tmp_path / "never_created" / "config.json"
    ro_san = PrivacySanitizer(missing_cfg, REPO_ROOT / "config.example.json", read_only=True)
    assert ro_san.language in ("zh", "en")
    assert not missing_cfg.exists()

    # 2. Failed hotkey edit rollback keeps get_hotkey_status()['state'] == 'ready'
    if sys.platform == "win32":
        san_hk = _make_sanitizer(tmp_path / "hk")
        app_hk = SanitizerTrayApp(san_hk)

        class FakeWinHotkeys:
            def __init__(self, bindings):
                self._bindings = list(bindings)
                self.failed_binding = None

            def start(self):
                for hk, _cb in self._bindings:
                    if hk == "alt+x":
                        self.failed_binding = "alt+x"
                        raise RuntimeError("busy")

            def stop(self):
                pass

        monkeypatch.setattr("src.windows_hotkeys.WindowsHotkeys", FakeWinHotkeys)
        assert app_hk.register_hotkeys() is True
        assert app_hk.get_hotkey_status()["state"] == "ready"
        assert app_hk.reload_hotkeys({"sanitize": "alt+x", "restore": "ctrl+shift+r"}) is False
        assert app_hk._last_hotkey_conflict == "alt+x"
        assert app_hk.get_hotkey_status()["state"] == "ready"

    # 3. restore_clipboard prevents native WM_CLIPBOARDUPDATE cruise from re-sanitizing restored secret
    san_cr = _make_sanitizer(tmp_path / "cruise", {"auto_sanitize_clipboard": True})
    app_cr = SanitizerTrayApp(san_cr)
    secret_tok = "ghp_AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEf1234"
    clip = {"text": f"push {secret_tok}"}
    monkeypatch.setattr("src.main._safe_clipboard_paste", lambda: clip["text"])
    monkeypatch.setattr("src.main._safe_clipboard_copy", lambda v, **_kw: (clip.__setitem__("text", v), True)[1])
    monkeypatch.setattr(
        "src.main._replace_clipboard_if_unchanged",
        lambda exp, new_v, **_kw: (clip.__setitem__("text", new_v), True)[1] if clip["text"] == exp else False,
    )
    app_cr.sanitize_clipboard()
    sanitized_clip = clip["text"]
    assert secret_tok not in sanitized_clip

    app_cr.restore_clipboard()
    assert clip["text"] == f"push {secret_tok}"
    # Simulated WM_CLIPBOARDUPDATE fires right after restore_clipboard
    app_cr._on_windows_clipboard_update()
    assert clip["text"] == f"push {secret_tok}", "Cruise must not immediately re-sanitize user's restored clipboard"

    # 4. allowlist_and_rerun_last_clipboard updates in-memory Home card even if external clipboard changed
    clip["text"] = "external clipboard text"
    ok_ext, _ = app_cr.allowlist_and_rerun_last_clipboard(secret_tok)
    assert ok_ext is False
    assert clip["text"] == "external clipboard text"
    assert app_cr.get_last_clipboard_record().total_count == 0

    # 5. GUI: entry_regex_cat <KeyRelease> updates live preview & _discard_layout preserves _drop_target + Open Output visible
    san_gui = _make_sanitizer(tmp_path / "gui_edge")
    root, win = _new_tk_window(san_gui)
    try:
        win._ensure_drop_target_attached()
        existing_drop = win._drop_target
        if sys.platform == "win32":
            assert existing_drop is not None and existing_drop.attached is True
        win._toggle_language()
        root.update()
        assert win._drop_target is existing_drop

        win._show_page("dict")
        win._show_dict_submode("regex")
        root.update()
        win.entry_regex_pattern.insert(0, r"TICKET-(?P<secret>\d{4})")
        win.entry_regex_test.insert(0, "TICKET-1234")
        win.entry_regex_cat.delete(0, "end")
        win.entry_regex_cat.insert(0, "CASE_NUM")
        assert win.entry_regex_cat._entry.bind("<KeyRelease>")
        win.entry_regex_cat._entry.focus_force()
        root.update()
        win.entry_regex_cat._entry.event_generate("<KeyRelease>", keysym="a")
        root.update()
        assert "TICKET-[CASE_NUM_1]" in win.lbl_regex_test_result.cget("text")

        win._show_page("home")
        sample = tmp_path / "out_check.txt"
        sample.write_text("email dev@example.com", encoding="utf-8")
        win.handle_dropped_paths([str(sample)], mode="sanitize")
        root.update()
        assert "out_check.sanitized.txt" in win.lbl_batch_result.cget("text")
        assert win.btn_open_batch_out.winfo_manager() == "pack"
    finally:
        _close_tk(root)

    # 6. Extension content.js: savedRange survives blur/selection-loss before btnSafe click,
    #    unrelated [UNKNOWN_99] does not show Restore Pill, and Escape dismisses Restore Pill
    node_edge = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function makeEl(tag) {
  return {
    tagName: String(tag || 'DIV').toUpperCase(),
    style: {},
    children: [],
    listeners: {},
    isContentEditable: false,
    textContent: '',
    attachShadow() {
      const root = { children: [], appendChild(c) { this.children.push(c); return c; } };
      this.shadowRoot = root;
      return root;
    },
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    dispatchEvent(ev) {
      if (ev.type === 'paste' && this.isContentEditable) return false; // Simulate Lexical NOT handling synthetic paste -> falls back to Strategy 2 Range!
      return true;
    },
    focus() {},
    closest(sel) { return sel.includes('pre') && this.tagName === 'PRE' ? this : null; },
    getBoundingClientRect() { return { top: 60, left: 40, right: 340, bottom: 160, width: 300, height: 100 }; },
  };
}

const docBody = makeEl('body');
let activeSelRanges = [];
let rangeDeleted = false;
let rangeInserted = '';
const initialRange = {
  cloneRange() { return this; },
  deleteContents() { rangeDeleted = true; },
  insertNode(node) { rangeInserted = node.data; },
  setStartAfter() {},
  collapse() {},
};
activeSelRanges = [initialRange];

const doc = {
  body: docBody,
  documentElement: docBody,
  listeners: {},
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
  createElement(tag) { return makeEl(tag); },
  createTextNode(txt) { return { data: txt }; },
};

const ctx = vm.createContext({
  window: null,
  document: doc,
  navigator: { language: 'en-US', clipboard: { writeText: async () => {} } },
  Event: function(t, o) { this.type = t; Object.assign(this, o || {}); },
  InputEvent: function(t, o) { this.type = t; Object.assign(this, o || {}); },
  getSelection: () => ({
    rangeCount: activeSelRanges.length,
    getRangeAt: (i) => activeSelRanges[i],
    removeAllRanges: () => { activeSelRanges = []; },
    addRange: (r) => { activeSelRanges.push(r); },
    toString: () => '',
  }),
  chrome: { runtime: { onMessage: { addListener() {} } } },
  setTimeout, clearTimeout,
});
ctx.window = ctx;

vm.runInContext(fs.readFileSync('browser-extension/sanitizer_core.js', 'utf8'), ctx);
vm.runInContext(fs.readFileSync('browser-extension/content.js', 'utf8'), ctx);

const editor = makeEl('div');
editor.isContentEditable = true;
docBody.appendChild(editor);

const sampleSecret = 'ghp_0123456789abcdef0123456789abcdef0123';
for (const fn of (doc.listeners['paste'] || [])) {
  fn({
    type: 'paste',
    target: editor,
    clipboardData: { getData: () => sampleSecret },
    preventDefault() {},
    stopPropagation() {},
  });
}
// Simulate focus moving away & selection clearing BEFORE user clicks Sanitize & Paste
activeSelRanges = [];
function findButtons(n, a = []) {
  if (!n) return a;
  if (n.tagName === 'BUTTON') a.push(n);
  for (const c of (n.children || [])) findButtons(c, a);
  return a;
}
const bannerHost = docBody.children.find(c => c.shadowRoot);
const btns = findButtons(bannerHost.shadowRoot);
btns[0].listeners['click'][0]();
assert.strictEqual(rangeDeleted, true, 'Saved range must be restored into Selection before Strategy 2');
const expectedTag = ctx.SanitizerExtCore.createSessionEngine().sanitize(sampleSecret).text;
assert.strictEqual(rangeInserted, expectedTag, 'Sanitized placeholder inserted at saved caret');

// Unrelated [UNKNOWN_99] in <pre> must NOT show Restore Pill
const preBad = makeEl('pre');
preBad.textContent = '[UNKNOWN_99]';
for (const fn of (doc.listeners['mouseover'] || [])) fn({ target: preBad });
assert.strictEqual(docBody.children.filter(c => c.shadowRoot).length, 0, 'Must not show restore pill for unknown tags');

// Valid mapped placeholder shows Restore Pill and Escape dismisses it
const preGood = makeEl('pre');
preGood.textContent = 'token=' + rangeInserted;
for (const fn of (doc.listeners['mouseover'] || [])) fn({ target: preGood });
assert.strictEqual(docBody.children.filter(c => c.shadowRoot).length, 1);
for (const fn of (doc.listeners['keydown'] || [])) fn({ key: 'Escape' });
assert.strictEqual(docBody.children.filter(c => c.shadowRoot).length, 0, 'Escape must dismiss restore pill');
console.log('EDGE_OK');
"""
    proc = subprocess.run(["node", "-e", node_edge], cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "EDGE_OK" in proc.stdout


def test_rapid_language_toggle_reuses_rule_rows_and_guide_faq_collapsible(tmp_path: Path) -> None:
    san = _make_sanitizer(tmp_path / "perf")
    root, win = _new_tk_window(san)
    try:
        # 1. Rapid 10x language toggling on Dict -> Rules must reuse existing rule checkboxes in-place
        win._show_page("dict")
        win._show_dict_submode("rules")
        root.update()
        first_chk_ids = {k: id(v[0]) for k, v in win._rule_row_cache.items()}
        assert len(first_chk_ids) > 10

        t0 = time.perf_counter()
        for _ in range(10):
            win._toggle_language()
            root.update()
        elapsed = time.perf_counter() - t0
        after_chk_ids = {k: id(v[0]) for k, v in win._rule_row_cache.items()}
        assert after_chk_ids == first_chk_ids
        assert elapsed < 3.0

        # 2. Quick Guide starts with FAQ collapsed, toggles open/closed, and updates language cleanly
        win._show_page("guide")
        root.update()
        assert win._guide_faq_open is False
        assert win.guide_faq_card._parent_frame.winfo_manager() == ""
        assert len(win.guide_step_descs) == 3
        win.btn_guide_faq.invoke()
        root.update()
        assert win._guide_faq_open is True
        assert win.guide_faq_card._parent_frame.winfo_manager() == "pack"
        win._toggle_language()
        root.update()
        assert win.guide_faq_card._parent_frame.winfo_manager() == "pack"
        win.btn_guide_faq.invoke()
        root.update()
        assert win._guide_faq_open is False
        assert win.guide_faq_card._parent_frame.winfo_manager() == ""

        # 3. Clicking Home KPI stat cards jumps straight to Rules list / Live Vault
        win._navigate_to_page("home")
        root.update()
        win._open_rules_list_page()
        root.update()
        assert win._active_page_key == "dict"
        assert win._dict_submode == "rules"
        win._navigate_to_page("vault")
        root.update()
        assert win._active_page_key == "vault"
    finally:
        _close_tk(root)
