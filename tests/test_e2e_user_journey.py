"""End-to-end real user-view GUI walkthrough across every page, button, modal, and hotkey flow."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace
import tkinter as tk

import customtkinter as ctk
import pytest

from src import __version__
from src.gui import _ModernControlCenter, _StableCTk
from src.main import SanitizerTrayApp
from src.rules import SAMPLE_TEST_PAYLOAD
from src.sanitizer import AI_PROMPT_HINTS, PrivacySanitizer
from src.vault_crypto import is_encrypted_vault_payload


def _find_widget(root, cls, *, text_contains: str):
    pending = [root]
    while pending:
        w = pending.pop(0)
        if isinstance(w, cls):
            try:
                txt = str(w.cget("text") or "")
            except Exception:
                txt = ""
            if text_contains in txt:
                return w
        pending.extend(w.winfo_children())
    raise AssertionError(f"Widget {cls.__name__} with text containing {text_contains!r} not found")


def _find_all(root, cls):
    out = []
    pending = [root]
    while pending:
        w = pending.pop(0)
        if isinstance(w, cls):
            out.append(w)
        pending.extend(w.winfo_children())
    return out


def _pump(root):
    root.update_idletasks()
    root.update()


def test_full_end_to_end_user_journey_across_all_pages(tmp_path: Path, monkeypatch):
    pytest.importorskip("cryptography")

    example = tmp_path / "example.json"
    example.write_text(
        json.dumps(
            {
                "language": "en",
                "theme": "dark",
                "hotkeys": {"sanitize": "alt+s", "restore": "alt+r"},
                "custom_dictionary": {"COMPANY": ["Acme Global"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sanitizer = PrivacySanitizer(tmp_path / "config.json", example)
    fake_clipboard = {"text": ""}

    monkeypatch.setattr("src.main._safe_clipboard_paste", lambda retries=3: fake_clipboard["text"])

    def _fake_copy(text, retries=3, *, conceal=False):
        fake_clipboard["text"] = text

    monkeypatch.setattr("src.main._safe_clipboard_copy", _fake_copy)
    monkeypatch.setattr("src.gui.is_startup_enabled", lambda: False)
    monkeypatch.setattr("src.gui.set_startup_enabled", lambda _v: True)
    monkeypatch.setattr(
        "src.gui.messagebox.showerror",
        lambda *a, **_kw: (_ for _ in ()).throw(AssertionError(f"Unexpected error dialog: {a}")),
    )

    from src.windows_hotkeys import parse_hotkey

    app = SanitizerTrayApp(sanitizer=sanitizer)
    monkeypatch.setattr(
        app,
        "_reload_hotkey_registration",
        lambda hk: bool(
            parse_hotkey(hk["sanitize"], lambda k: ord(k.upper()) if k.isalnum() else -1)
            and parse_hotkey(hk["restore"], lambda k: ord(k.upper()) if k.isalnum() else -1)
        ),
    )
    ctk.set_appearance_mode("Dark")
    try:
        root = _StableCTk()
    except tk.TclError as exc:
        if "display" in str(exc).lower():
            pytest.skip("Tk display unavailable")
        raise

    root.geometry("940x680+20000+20000")
    root.deiconify()

    win = _ModernControlCenter(
        root=root,
        sanitizer=sanitizer,
        on_sanitize_clipboard=app.sanitize_clipboard,
        on_restore_clipboard=app.restore_clipboard,
        on_undo_sanitize=app.undo_last_sanitize,
        on_reload_hotkeys=app.reload_hotkeys,
        on_language_changed=app.refresh_tray_i18n,
        on_clear_session=app.clear_session_map,
        on_copy_to_clipboard=app.copy_to_clipboard,
        on_state_changed=app._update_tray_icon_state,
        get_idle_seconds_left=app.get_idle_seconds_remaining,
    )
    _pump(root)

    try:
        # ==================== 1. DASHBOARD ====================
        raw_secret = "DB=postgres://ops:Secret@99@10.44.55.66:5432/prod vendor=Acme Global"
        fake_clipboard["text"] = raw_secret
        win.btn_hero_san.invoke()
        _pump(root)
        san_clip = fake_clipboard["text"]
        assert "Secret@99" not in san_clip
        assert "Acme Global" not in san_clip
        assert int(win.lbl_stat_hits.cget("text")) >= 2
        assert int(win.lbl_stat_vault.cget("text")) >= 2

        win.btn_hero_res.invoke()
        _pump(root)
        assert fake_clipboard["text"] == raw_secret

        fake_clipboard["text"] = raw_secret
        win.btn_hero_san.invoke()
        _pump(root)
        assert "Secret@99" not in fake_clipboard["text"]
        win.btn_hero_undo.invoke()
        _pump(root)
        assert fake_clipboard["text"] == raw_secret

        # Semantic Disguise + AI Hint switches on Dashboard
        sw_sem = _find_widget(win.home_sw_card, ctk.CTkSwitch, text_contains="")
        switches_home = _find_all(win.home_sw_card, ctk.CTkSwitch)
        assert len(switches_home) == 2
        switches_home[0].toggle()
        switches_home[1].toggle()
        _pump(root)
        assert sanitizer.semantic_ip_mode is True
        assert sanitizer.ai_prompt_hint is True
        disguised = sanitizer.sanitize("ip=10.88.99.10")
        assert disguised.sanitized_text.startswith(AI_PROMPT_HINTS["en"])
        assert "192.0.2." in disguised.sanitized_text
        # Turn semantic & AI hint back off cleanly
        switches_home[0].toggle()
        switches_home[1].toggle()
        _pump(root)
        assert sanitizer.semantic_ip_mode is False
        assert sanitizer.ai_prompt_hint is False

        # Local File Sanitize & Restore via Dashboard buttons
        src_file = tmp_path / "demo.env"
        san_out = tmp_path / "demo.sanitized.env"
        res_out = tmp_path / "demo.restored.env"
        src_file.write_text("TOKEN=sk-proj-TestSecretKey1234567890\n", encoding="utf-8")

        monkeypatch.setattr("src.gui.filedialog.askopenfilename", lambda **_kw: str(src_file))
        monkeypatch.setattr("src.gui.filedialog.asksaveasfilename", lambda **_kw: str(san_out))
        _find_widget(win.home_file_card, ctk.CTkButton, text_contains="Sanitize File").invoke()
        _pump(root)
        assert san_out.exists()
        assert "TestSecretKey" not in san_out.read_text(encoding="utf-8")

        monkeypatch.setattr("src.gui.filedialog.askopenfilename", lambda **_kw: str(san_out))
        monkeypatch.setattr("src.gui.filedialog.asksaveasfilename", lambda **_kw: str(res_out))
        _find_widget(win.home_file_card, ctk.CTkButton, text_contains="Restore File").invoke()
        _pump(root)
        assert res_out.read_text(encoding="utf-8") == "TOKEN=sk-proj-TestSecretKey1234567890\n"

        # ==================== 2. LIVE SANDBOX ====================
        win.nav_bar._buttons_dict[win._nav_key_to_label["sandbox"]].invoke()
        _pump(root)
        assert win._active_page_key == "sandbox"

        vault_before_sb = sanitizer.vault.size
        _find_widget(win.pages["sandbox"], ctk.CTkButton, text_contains="Load Sample").invoke()
        _pump(root)
        sb_out = win.sandbox_output.get("1.0", "end-1c")
        assert "R3disP@ssw0rd99" not in sb_out
        assert sanitizer.vault.size == vault_before_sb  # isolated sandbox did not pollute vault
        assert len(win._saved_sandbox_cat_counts) >= 4
        assert win.sandbox_output._textbox.tag_ranges("placeholder_tag")

        # Test Restore
        _find_widget(win.pages["sandbox"], ctk.CTkButton, text_contains="Test Restore").invoke()
        _pump(root)
        assert win.sandbox_output.get("1.0", "end-1c") == SAMPLE_TEST_PAYLOAD.strip()

        # Re-sanitize + right-click allowlist resolution + Copy Output + Sync to Vault
        _find_widget(win.pages["sandbox"], ctk.CTkButton, text_contains="Sanitize").invoke()
        _pump(root)
        ph_sample = next(ph for ph, orig, _c in win._sandbox_vault.snapshot_placeholders() if orig == "192.168.10.45")
        orig_sample = win._sandbox_vault.lookup_original(ph_sample)
        win._allowlist_from_sandbox_tag(orig_sample)
        _pump(root)
        assert "192.168.10.45" in sanitizer.get_allowlist()
        assert "192.168.10.45" in win.sandbox_output.get("1.0", "end-1c")

        _find_widget(win.pages["sandbox"], ctk.CTkButton, text_contains="Copy Output").invoke()
        _pump(root)
        assert fake_clipboard["text"] == win.sandbox_output.get("1.0", "end-1c")

        _find_widget(win.pages["sandbox"], ctk.CTkButton, text_contains="Sync to Global Vault").invoke()
        _pump(root)
        assert sanitizer.vault.size > vault_before_sb

        # Clear Sandbox
        _find_widget(win.pages["sandbox"], ctk.CTkButton, text_contains="Clear").invoke()
        _pump(root)
        assert win.sandbox_input.get("1.0", "end-1c") == ""
        assert win.sandbox_output.get("1.0", "end-1c") == ""

        # ==================== 3. WORDS & RULES ====================
        win.nav_bar._buttons_dict[win._nav_key_to_label["dict"]].invoke()
        _pump(root)
        assert win._active_page_key == "dict"

        win.entry_new_word.insert(0, "AcmeAlpha, BetaCore")
        _find_widget(win.dict_words_pane, ctk.CTkButton, text_contains="Add Word").invoke()
        _pump(root)
        custom_words = sanitizer.get_custom_dictionary()["COMPANY"]
        assert "AcmeAlpha" in custom_words and "BetaCore" in custom_words

        # Delete one custom word with ✕ button inside dict_scroll
        del_btns = [b for b in _find_all(win.dict_scroll, ctk.CTkButton) if b.cget("text") == "✕"]
        assert len(del_btns) >= 2
        del_btns[0].invoke()
        _pump(root)
        assert len(sanitizer.get_custom_dictionary()["COMPANY"]) == len(custom_words) - 1

        # Open In-App JSON Editor, change idle_wipe_minutes -> 15, Format + Save
        _find_widget(win.dict_words_pane, ctk.CTkButton, text_contains="JSON").invoke()
        _pump(root)
        modal = win._json_modal
        assert modal is not None and modal.winfo_exists()
        txt_widget = _find_all(modal, ctk.CTkTextbox)[0]
        cfg_obj = json.loads(txt_widget.get("1.0", "end-1c"))
        cfg_obj["idle_wipe_minutes"] = 15
        txt_widget.delete("1.0", "end")
        txt_widget.insert("1.0", json.dumps(cfg_obj))
        _find_widget(modal, ctk.CTkButton, text_contains="Format").invoke()
        _pump(root)
        monkeypatch.setattr("src.gui.messagebox.showinfo", lambda *a, **kw: None)
        _find_widget(modal, ctk.CTkButton, text_contains="Save").invoke()
        _pump(root)
        assert sanitizer.idle_wipe_minutes == 15
        assert not modal.winfo_exists()

        # Export & Clear All & Re-import custom dictionary
        dict_backup = tmp_path / "dict_backup.json"
        monkeypatch.setattr("src.gui.messagebox.askokcancel", lambda *a, **kw: True)
        monkeypatch.setattr("src.gui.filedialog.asksaveasfilename", lambda **_kw: str(dict_backup))
        _find_widget(win.dict_words_pane, ctk.CTkButton, text_contains="Export").invoke()
        _pump(root)
        assert dict_backup.exists()

        monkeypatch.setattr("src.gui.messagebox.askyesno", lambda *a, **kw: True)
        _find_widget(win.dict_words_pane, ctk.CTkButton, text_contains="Clear All").invoke()
        _pump(root)
        assert not any(sanitizer.get_custom_dictionary().values())

        monkeypatch.setattr("src.gui.filedialog.askopenfilename", lambda **_kw: str(dict_backup))
        _find_widget(win.dict_words_pane, ctk.CTkButton, text_contains="Import").invoke()
        _pump(root)
        assert sanitizer.get_custom_dictionary()["COMPANY"]

        # Switch to Allowlist & Rules submode
        win.dict_mode_seg._buttons_dict[win._dict_mode_labels[1]].invoke()
        _pump(root)
        assert win._dict_submode == "rules"

        long_host = "very-long-internal-gateway.prod.company.internal"
        win.entry_allowlist.insert(0, long_host)
        _find_widget(win.dict_allow_card, ctk.CTkButton, text_contains="Add Allowlist").invoke()
        _pump(root)
        assert long_host in sanitizer.get_allowlist()

        # Confirm the ✕ delete button is inside its parent row (never clipped by long hostname)
        allow_dels = [b for b in _find_all(win.allowlist_scroll, ctk.CTkButton) if b.cget("text") == "✕"]
        assert allow_dels
        last_del = allow_dels[-1]
        assert last_del.winfo_x() + last_del.winfo_width() <= last_del.master.winfo_width() + 2
        last_del.invoke()
        _pump(root)
        assert long_host not in sanitizer.get_allowlist()

        # Presets + Rule Search + Checkbox toggle
        _find_widget(win.dict_preset_row, ctk.CTkButton, text_contains="DevOps").invoke()
        _pump(root)
        dev_counts = sanitizer.active_rule_counts()
        assert dev_counts[0] < dev_counts[1]
        assert win.lbl_stat_rules.cget("text") == f"{dev_counts[0]}/{dev_counts[1]}"

        _find_widget(win.dict_preset_row, ctk.CTkButton, text_contains="Keys Only").invoke()
        _pump(root)
        assert sanitizer.active_rule_counts()[0] == sanitizer.active_rule_counts()[1]

        win.rule_search_var.set("stripe")
        win.refresh_allowlist_and_rules_list()
        _pump(root)
        stripe_boxes = _find_all(win.rules_toggle_scroll, ctk.CTkCheckBox)
        assert len(stripe_boxes) == 1
        stripe_boxes[0].toggle()
        _pump(root)
        assert "stripe_live_test_key" in sanitizer.get_disabled_rules()
        stripe_boxes[0].toggle()
        _pump(root)
        assert "stripe_live_test_key" not in sanitizer.get_disabled_rules()
        win.rule_search_var.set("")
        win.refresh_allowlist_and_rules_list()

        # ==================== 4. SESSION VAULT ====================
        win.nav_bar._buttons_dict[win._nav_key_to_label["vault"]].invoke()
        _pump(root)
        assert win._active_page_key == "vault"
        assert sanitizer.vault.size > 0

        # Masked by default; Reveal Originals exposes plaintext
        vault_labels_masked = [l.cget("text") for l in _find_all(win.vault_scroll, ctk.CTkLabel)]
        assert any("•" in str(t) for t in vault_labels_masked)
        reveal_sw = _find_all(win.pages["vault"], ctk.CTkSwitch)[0]
        reveal_sw.toggle()
        _pump(root)
        assert win._reveal_vault_originals is True
        reveal_sw.toggle()
        _pump(root)

        # Copy Tag copies placeholder to clipboard
        _find_widget(win.vault_scroll, ctk.CTkButton, text_contains="Copy Tag").invoke()
        _pump(root)
        assert fake_clipboard["text"]

        # Encrypted Export + Clear Vault + Encrypted Import (AES-256-GCM)
        enc_vault_file = tmp_path / "session.vault.json"
        monkeypatch.setattr("src.gui.simpledialog.askstring", lambda *a, **kw: "VaultPass#2026")
        monkeypatch.setattr("src.gui.filedialog.asksaveasfilename", lambda **_kw: str(enc_vault_file))
        _find_widget(win.vault_actions_row, ctk.CTkButton, text_contains="Encrypted Export").invoke()
        _pump(root)
        assert enc_vault_file.exists()
        assert is_encrypted_vault_payload(json.loads(enc_vault_file.read_text(encoding="utf-8")))

        saved_count = sanitizer.vault.size
        monkeypatch.setattr("src.gui.messagebox.askyesno", lambda *a, **kw: True)
        _find_widget(win.vault_actions_row, ctk.CTkButton, text_contains="Clear Vault").invoke()
        _pump(root)
        assert sanitizer.vault.size == 0

        monkeypatch.setattr("src.gui.filedialog.askopenfilename", lambda **_kw: str(enc_vault_file))
        _find_widget(win.vault_actions_row, ctk.CTkButton, text_contains="Encrypted Import").invoke()
        _pump(root)
        assert sanitizer.vault.size == saved_count

        # ==================== 5. HOTKEYS & SAFETY ====================
        win.nav_bar._buttons_dict[win._nav_key_to_label["settings"]].invoke()
        _pump(root)
        assert win._active_page_key == "settings"

        # Record sanitize key with Windows NumLock ON (0x0008): MUST NOT inject ALT!
        numlock_bit = 0x0008 if sys.platform == "win32" else 0
        win.btn_rec_san.invoke()
        _pump(root)
        assert win._recording_target == "sanitize"
        assert win.btn_edit_san.winfo_x() + win.btn_edit_san.winfo_width() <= win.btn_edit_san.master.winfo_width() + 2
        win._on_hotkey_keypress(SimpleNamespace(keysym="K", state=0x0005 | numlock_bit, keycode=0x4B))  # Ctrl+Shift+K + NumLock
        _pump(root)
        assert win._recording_target is None
        assert sanitizer.hotkeys["sanitize"] == "ctrl+shift+k"
        assert win.combo_hk_sanitize._pill_btn.cget("text") == "CTRL + SHIFT + K"

        # Record F9 on restore with NumLock ON (0x0008): MUST stay F9 without ALT!
        win.btn_rec_res.invoke()
        _pump(root)
        win._on_hotkey_keypress(SimpleNamespace(keysym="F9", state=numlock_bit, keycode=0x78))
        _pump(root)
        assert sanitizer.hotkeys["restore"] == "f9"
        assert win.combo_hk_restore._pill_btn.cget("text") == "F9"

        # Confirm redundant "Save & Apply" button is removed in favor of IDE-style instant save
        assert not any("Save & Apply" in str(b.cget("text") or "") for b in _find_all(win.pages["settings"], ctk.CTkButton))

        # Click Pencil (✏️ -> ✓) -> insert text -> click ✓ -> saves immediately & closes cleanly back to normal pill + ✏️!
        win.btn_edit_san.invoke()
        _pump(root)
        assert win.combo_hk_sanitize._editing is True
        assert win.btn_edit_san.cget("text") == "✓"
        assert win.combo_hk_sanitize._entry.winfo_ismapped()
        win.combo_hk_sanitize._entry.delete(0, "end")
        win.combo_hk_sanitize._entry.insert(0, "ctrl+shift+j")
        win.btn_edit_san.invoke()
        _pump(root)
        assert win.combo_hk_sanitize._editing is False
        assert win.btn_edit_san.cget("text") == "✏️"
        assert not win.combo_hk_sanitize._entry.winfo_ismapped()
        assert win.combo_hk_sanitize._pill_btn.winfo_ismapped()
        assert sanitizer.hotkeys["sanitize"] == "ctrl+shift+j"
        assert win.combo_hk_sanitize._pill_btn.cget("text") == "CTRL + SHIFT + J"

        # Pencil -> invalid text -> click ✓ -> shows warning, closes editing, restores ✏️ & rolls back pill
        monkeypatch.setattr("src.gui.messagebox.showwarning", lambda *a, **kw: None)
        win.btn_edit_res.invoke()
        _pump(root)
        assert win.btn_edit_res.cget("text") == "✓"
        win.combo_hk_restore._entry.delete(0, "end")
        win.combo_hk_restore._entry.insert(0, "bad")
        win.btn_edit_res.invoke()
        _pump(root)
        assert win.combo_hk_restore._editing is False
        assert win.btn_edit_res.cget("text") == "✏️"
        assert not win.combo_hk_restore._entry.winfo_ismapped()
        assert win.combo_hk_restore._pill_btn.cget("text") == "F9"

        # Pencil open -> Reset Default -> closes editing, restores ✏️ and resets to ALT+S / ALT+R
        win.btn_edit_san.invoke()
        _pump(root)
        assert win.combo_hk_sanitize._editing is True
        win.combo_hk_sanitize._entry.delete(0, "end")
        win.combo_hk_sanitize._entry.insert(0, "ctrl+1")
        _find_widget(win.pages["settings"], ctk.CTkButton, text_contains="Reset Default").invoke()
        _pump(root)
        assert win.combo_hk_sanitize._editing is False
        assert win.btn_edit_san.cget("text") == "✏️"
        assert sanitizer.hotkeys == {"sanitize": "alt+s", "restore": "alt+r"}
        assert win.combo_hk_sanitize._pill_btn.cget("text") == "ALT + S"
        assert win.combo_hk_restore._pill_btn.cget("text") == "ALT + R"

        # Set custom hotkeys via Pencil + ✓ / Enter for Quick Guide verification
        win.btn_edit_san.invoke()
        win.combo_hk_sanitize._entry.delete(0, "end")
        win.combo_hk_sanitize._entry.insert(0, "ctrl+shift+k")
        win.btn_edit_san.invoke()
        win.btn_edit_res.invoke()
        win.combo_hk_restore._entry.delete(0, "end")
        win.combo_hk_restore._entry.insert(0, "f10")
        win.combo_hk_restore._handle_entry_return()
        _pump(root)
        assert sanitizer.hotkeys == {"sanitize": "ctrl+shift+k", "restore": "f10"}

        # Privacy switches + Auto-Wipe dropdown synced with sidebar
        settings_switches = _find_all(win.pages["settings"], ctk.CTkSwitch)
        assert len(settings_switches) >= 3
        settings_switches[0].toggle()  # Cruise Mode ON
        _pump(root)
        assert sanitizer.auto_sanitize_clipboard is True
        assert "Cruise" in win.lbl_side_status.cget("text")
        settings_switches[0].toggle()
        _pump(root)

        win.combo_idle_wipe.set(win._idle_label(10))
        win._on_idle_wipe_selected(win._idle_label(10))
        _pump(root)
        assert sanitizer.idle_wipe_minutes == 10
        assert win.lbl_idle_readout.cget("text").startswith(("10:", "09:"))

        # ==================== 6. QUICK GUIDE & GLOBAL SIDEBAR CONTROLS ====================
        win.nav_bar._buttons_dict[win._nav_key_to_label["guide"]].invoke()
        _pump(root)
        assert win._active_page_key == "guide"
        assert str(win.guide_box.cget("state")) == "disabled"
        guide_en = win.guide_box.get("1.0", "end-1c")
        assert "CTRL+SHIFT+K" in guide_en
        assert "F10" in guide_en
        assert "Alt+S" not in guide_en and "Alt+R" not in guide_en

        # Switch Dashboard and verify updated hotkeys & zero clipping
        win.nav_bar._buttons_dict[win._nav_key_to_label["home"]].invoke()
        _pump(root)
        assert "CTRL+SHIFT+K" in win.btn_hero_san.cget("text")
        assert "F10" in win.btn_hero_res.cget("text")
        assert win.btn_hero_res.winfo_x() + win.btn_hero_res.winfo_width() <= win.btn_hero_res.master.winfo_width() + 2

        # Language toggle EN -> ZH translates Quick Guide & Vault Copy Tag in-place
        win.btn_lang.invoke()
        _pump(root)
        assert win.lang == "zh"
        guide_zh = win.guide_box.get("1.0", "end-1c")
        assert "CTRL+SHIFT+K" in guide_zh
        assert "F10" in guide_zh
        assert "使用指南" in win._nav_key_to_label["guide"]
        win.nav_bar._buttons_dict[win._nav_key_to_label["vault"]].invoke()
        _pump(root)
        _find_widget(win.vault_scroll, ctk.CTkButton, text_contains="复制标签")

        # Theme toggle Dark -> Light -> Dark
        win.btn_theme.invoke()
        _pump(root)
        assert win.theme_mode == "light"
        win.btn_theme.invoke()
        _pump(root)
        assert win.theme_mode == "dark"

        # About modal opens and closes cleanly
        _find_widget(win._main_container, ctk.CTkButton, text_contains="关于").invoke()
        _pump(root)
        assert win._about_modal is not None and win._about_modal.winfo_exists()
        assert __version__ in win._about_version_label.cget("text")
        _find_widget(win._about_modal, ctk.CTkButton, text_contains="关闭").invoke()
        _pump(root)
        assert not win._about_modal.winfo_exists()
    finally:
        app.exit_app()
        for timer in root.tk.splitlist(root.tk.call("after", "info")):
            root.tk.call("after", "cancel", timer)
        root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native RegisterHotKey")
def test_real_windows_reset_default_and_conflict_flow(tmp_path: Path, monkeypatch):
    from src.windows_hotkeys import WindowsHotkeys

    example = tmp_path / "example.json"
    example.write_text(
        json.dumps(
            {
                "language": "en",
                "theme": "dark",
                "hotkeys": {"sanitize": "ctrl+a", "restore": "ctrl+shift+b"},
                "custom_dictionary": {},
            }
        ),
        encoding="utf-8",
    )
    sanitizer = PrivacySanitizer(tmp_path / "config.json", example)
    app = SanitizerTrayApp(sanitizer=sanitizer)

    warnings = []
    monkeypatch.setattr("src.gui.messagebox.showwarning", lambda *a, **kw: warnings.append(a))
    monkeypatch.setattr(
        "src.gui.messagebox.showerror",
        lambda *a, **_kw: (_ for _ in ()).throw(AssertionError(f"Unexpected error dialog: {a}")),
    )

    ctk.set_appearance_mode("Dark")
    try:
        root = _StableCTk()
    except tk.TclError as exc:
        if "display" in str(exc).lower():
            pytest.skip("Tk display unavailable")
        raise

    root.geometry("940x680+20000+20000")
    root.deiconify()

    win = _ModernControlCenter(
        root=root,
        sanitizer=sanitizer,
        on_reload_hotkeys=app.reload_hotkeys,
        on_language_changed=app.refresh_tray_i18n,
        get_last_hotkey_conflict=lambda: app._last_hotkey_conflict,
    )
    _pump(root)

    blocker = WindowsHotkeys([("ctrl+shift+y", lambda: None)])
    try:
        blocker.start()
        win.nav_bar._buttons_dict[win._nav_key_to_label["settings"]].invoke()
        _pump(root)

        # 1. Real Win32 Reset Default from ctrl+a / ctrl+shift+b MUST succeed with zero error popups
        _find_widget(win.pages["settings"], ctk.CTkButton, text_contains="Reset Default").invoke()
        _pump(root)
        assert not warnings, f"Unexpected Reset Default warning: {warnings}"
        assert app._windows_hotkeys is not None and app._windows_hotkeys.active
        assert tuple(sanitizer.hotkeys.values()) in (
            ("alt+s", "alt+r"),
            ("alt+s", "ctrl+shift+r"),
            ("ctrl+shift+s", "ctrl+shift+r"),
            ("ctrl+alt+s", "ctrl+alt+r"),
        )
        san_expected, res_expected = sanitizer.hotkeys["sanitize"], sanitizer.hotkeys["restore"]
        assert win.combo_hk_sanitize._pill_btn.cget("text") == " + ".join(san_expected.upper().split("+"))
        assert win.combo_hk_restore._pill_btn.cget("text") == " + ".join(res_expected.upper().split("+"))
        assert san_expected.upper() in win.guide_box.get("1.0", "end-1c")
        assert res_expected.upper() in win.guide_box.get("1.0", "end-1c")

        # 2. Saving a genuinely occupied Windows chord reports the exact conflicting key
        win.btn_edit_san.invoke()
        _pump(root)
        assert win.btn_edit_san.cget("text") == "✓"
        win.combo_hk_sanitize._entry.delete(0, "end")
        win.combo_hk_sanitize._entry.insert(0, "ctrl+shift+y")
        win.btn_edit_san.invoke()
        _pump(root)
        assert warnings and "CTRL+SHIFT+Y" in warnings[-1][1]
        assert win.combo_hk_sanitize._editing is False
        assert win.btn_edit_san.cget("text") == "✏️"
        assert sanitizer.hotkeys == {"sanitize": san_expected, "restore": res_expected}
    finally:
        blocker.stop()
        app.exit_app()
        for timer in root.tk.splitlist(root.tk.call("after", "info")):
            root.tk.call("after", "cancel", timer)
        root.destroy()
