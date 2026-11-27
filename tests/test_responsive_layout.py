"""Automated responsive layout & anti-clipping verification across all GUI pages and window sizes."""

import json
from pathlib import Path
import tkinter as tk

import customtkinter as ctk
import pytest

from src.gui import _ModernControlCenter, _StableCTk
from src.main import LastClipboardSanitizeRecord
from src.sanitizer import PrivacySanitizer


def _iter_mapped_descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _iter_mapped_descendants(child)


def _assert_no_clipped_controls(root: tk.Misc, container: tk.Misc, context: str) -> None:
    root.update()
    for w in _iter_mapped_descendants(container):
        try:
            if not w.winfo_ismapped():
                continue
        except tk.TclError:
            continue
        parent = w.master
        if parent is None:
            continue
        pw = parent.winfo_width()
        if pw <= 20:
            continue
        if isinstance(w, (ctk.CTkButton, ctk.CTkSwitch)):
            wx = w.winfo_x()
            ww = w.winfo_width()
            assert wx >= -2, f"[{context}] {w} negative x={wx}"
            assert ww >= 20, f"[{context}] {w} crushed width={ww}"
            assert wx + ww <= pw + 4, (
                f"[{context}] {w} overflows parent width={pw} (x={wx}, w={ww}, text={getattr(w, 'cget', lambda _k: '')('text')!r})"
            )
        if isinstance(w, ctk.CTkButton):
            lbl = getattr(w, "_text_label", None)
            if lbl is not None and w.cget("text"):
                req_w = lbl.winfo_reqwidth()
                actual_w = w.winfo_width()
                assert actual_w + 2 >= req_w, (
                    f"[{context}] button text clipped: {w.cget('text')!r} actual_w={actual_w} < req_w={req_w}"
                )


@pytest.mark.parametrize("lang", ["en", "zh"])
@pytest.mark.parametrize("size", [(860, 620), (940, 680), (1320, 820)])
def test_all_pages_fit_without_clipping_across_sizes(tmp_path: Path, lang: str, size):
    example = tmp_path / "example.json"
    example.write_text(
        json.dumps(
            {
                "language": lang,
                "theme": "dark",
                "hotkeys": {"sanitize": "alt+s", "restore": "ctrl+shift+r"},
                "custom_dictionary": {"COMPANY": ["Acme Global Technologies Sdn Bhd"]},
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
    w_px, h_px = size
    root.geometry(f"{w_px}x{h_px}+20000+20000")
    root.deiconify()
    try:
        conflict_status = {
            "state": "conflict",
            "conflict_key": "alt+s",
            "bound": {},
            "configured": {"sanitize": "alt+s", "restore": "ctrl+shift+r"},
        }
        sample_recent = LastClipboardSanitizeRecord(
            raw_text="Cloudflare CF_TOKEN=cf_test_token_alpha_1234567890abcd",
            sanitized_text="Cloudflare CF_TOKEN=[CLOUDFLARE_TOKEN_1]",
            source="hotkey",
            total_count=1,
            items=[("[CLOUDFLARE_TOKEN_1]", "cf_test_token_alpha_1234567890abcd", "CLOUDFLARE_TOKEN")],
        )
        win = _ModernControlCenter(
            root,
            sanitizer,
            get_hotkey_status=lambda: conflict_status,
            get_last_clipboard_record=lambda: sample_recent,
        )
        root.update()
        for page_key in ("home", "sandbox", "dict", "vault", "settings", "guide"):
            win._show_page(page_key)
            if page_key == "dict":
                win._show_dict_submode("words")
                _assert_no_clipped_controls(root, win.page_container, f"{lang}-{w_px}x{h_px}-dict-words")
                win._show_dict_submode("rules")
                _assert_no_clipped_controls(root, win.page_container, f"{lang}-{w_px}x{h_px}-dict-rules")
                win._show_dict_submode("regex")
                _assert_no_clipped_controls(root, win.page_container, f"{lang}-{w_px}x{h_px}-dict-regex")
            else:
                _assert_no_clipped_controls(root, win.page_container, f"{lang}-{w_px}x{h_px}-{page_key}")
            # Also verify footer never clips
            _assert_no_clipped_controls(root, win._main_container, f"{lang}-{w_px}x{h_px}-{page_key}-shell")
    finally:
        for timer in root.tk.splitlist(root.tk.call("after", "info")):
            root.tk.call("after", "cancel", timer)
        root.destroy()
