"""Synthetic Tk transition regressions; no screenshots, private config or clipboard."""
import ctypes
import json
from pathlib import Path
import sys
import tkinter as tk

import customtkinter as ctk
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.gui import _ModernControlCenter, _StableCTk
from src.sanitizer import PrivacySanitizer


@pytest.fixture
def window(tmp_path):
    example = tmp_path / "example.json"
    example.write_text(json.dumps({"language": "zh", "theme": "dark", "hotkeys": {
        "sanitize": "alt+s", "restore": "ctrl+shift+r"}, "custom_dictionary": {}}), encoding="utf-8")
    sanitizer = PrivacySanitizer(tmp_path / "config.json", example)
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
        yield root, win
    finally:
        # Tk timers outlive destroyed widget commands; don't leave prior test
        # interpreters' scheduled work in the shared native Tk event queue.
        for timer in root.tk.splitlist(root.tk.call("after", "info")):
            root.tk.call("after", "cancel", timer)
        root.destroy()


@pytest.mark.parametrize("operation", ["theme", "language"])
def test_switch_keeps_normal_idle_processing_and_completed_controls(window, operation):
    root, win = window
    old = win._main_container
    observations = []
    root.after_idle(lambda: observations.append({
        "theme": ctk.get_appearance_mode().lower(),
        "button_theme": win.btn_theme._get_appearance_mode().lower(),
        "button_text": win.btn_theme.cget("text"),
        "old_exists": bool(old.winfo_exists()),
    }))
    getattr(win, "_toggle_" + operation)()
    root.update_idletasks()
    assert observations
    assert ctk.get_appearance_mode().lower() == win.btn_theme._get_appearance_mode().lower() == win.theme_mode
    assert win.btn_theme.cget("text") == win._t(
        "btn_theme_light" if win.theme_mode == "dark" else "btn_theme_dark")
    assert old.winfo_exists() and win._main_container is old
    assert not root.tk.call("info", "commands", "::aps_update_*")
    assert win.sanitizer.hotkeys == {"sanitize": "alt+s", "restore": "ctrl+shift+r"}
    assert root.state() == "withdrawn"


@pytest.mark.parametrize("fail_save", [False, True])
def test_language_replacement_is_ready_behind_mapped_old_layout(window, fail_save):
    root, win = window
    root.geometry("940x660+20000+20000")
    root.deiconify()
    root.update()
    old = win._main_container
    staged = []

    def ready():
        new = win._main_container
        staged.append(new)
        assert old.winfo_viewable() and new.winfo_viewable()
        assert old.winfo_manager() == new.winfo_manager() == "grid"
        assert old.winfo_width() == new.winfo_width() == root.winfo_width()
        assert root.tk.splitlist(root.tk.call("winfo", "children", root._w))[-1] == old._w
        if fail_save:
            raise RuntimeError("synthetic settings failure")

    if fail_save:
        with pytest.raises(RuntimeError, match="synthetic"):
            win._build_layout(on_ready=ready)
        assert win._main_container is old and old.winfo_viewable()
        assert not staged[0].winfo_exists()
    else:
        win._build_layout(on_ready=ready)
        assert not old.winfo_exists() and win._main_container.winfo_viewable()


def test_switch_does_not_replace_tcl_update_commands(window):
    root, win = window
    other = tk.Tcl()
    other.eval("set observed 0; after idle {set observed 1}")
    win._toggle_theme()
    win._toggle_language()
    other.eval("update idletasks")
    assert other.eval("set observed") == "1"
    assert not root.tk.call("info", "commands", "::aps_update_*")
    with pytest.raises(tk.TclError):
        root.tk.call("update", "not-a-valid-option")


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows redraw boundary")
def test_mapped_window_remains_visible_during_failed_language_change(window, monkeypatch):
    root, win = window
    root.geometry("940x660+20000+20000")
    root.deiconify()
    root.update()
    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    hwnd = user32.GetParent(root.winfo_id())
    events = []
    root.bind("<Map>", lambda event: events.append("map") if event.widget is root else None)
    root.bind("<Unmap>", lambda event: events.append("unmap") if event.widget is root else None)
    assert user32.IsWindowVisible(hwnd)
    def fail():
        assert user32.IsWindowVisible(hwnd)
        raise RuntimeError("synthetic")
    monkeypatch.setattr(win, "_refresh_translations", lambda *_: fail())
    win._toggle_language()
    assert user32.IsWindowVisible(hwnd)
    root.update()
    assert root.state() == "normal" and events == []


def test_window_background_matches_page_in_both_themes(window):
    root, win = window
    for _ in range(2):
        assert root.cget("fg_color") == win._main_container.cget("fg_color")
        win._toggle_theme()


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows mapped button regression")
@pytest.mark.parametrize("operation", ["theme", "language"])
def test_repeated_real_buttons_leave_current_native_window_visible_and_usable(window, operation):
    root, win = window
    root.geometry("940x660+20000+20000")
    root.deiconify()
    root.update()
    native = ctypes.WinDLL("user32", use_last_error=True)
    native.GetParent.argtypes = [ctypes.c_void_p]
    native.GetParent.restype = ctypes.c_void_p
    native.IsWindowVisible.argtypes = [ctypes.c_void_p]
    native.IsWindowVisible.restype = ctypes.c_int
    errors = []
    visibility_during_idle = []
    root.report_callback_exception = lambda *args: errors.append(args)
    root.tk.createcommand("::aps_test_bgerror", lambda message: errors.append(message))
    root.tk.eval("proc bgerror {message} {::aps_test_bgerror $message}")

    def language_button():
        pending = [root]
        while pending:
            widget = pending.pop()
            if isinstance(widget, ctk.CTkButton) and widget.cget("command") == win._toggle_language:
                return widget
            pending.extend(widget.winfo_children())
        raise AssertionError("Language button missing")

    for _ in range(4):
        old_value = win.theme_mode if operation == "theme" else win.lang
        button = win.btn_theme if operation == "theme" else language_button()
        root.after_idle(lambda: visibility_during_idle.append(
            bool(native.IsWindowVisible(native.GetParent(root.winfo_id())))))
        button._canvas.event_generate("<Enter>", x=10, y=10)
        button._canvas.event_generate("<ButtonPress-1>", x=10, y=10)
        button._canvas.event_generate("<ButtonRelease-1>", x=10, y=10)
        root.update()
        root.after(130, root.quit)
        root.mainloop()
        actual = win.theme_mode if operation == "theme" else win.lang
        assert actual != old_value
        assert not errors
        current_hwnd = native.GetParent(root.winfo_id())
        assert native.IsWindowVisible(current_hwnd), "Current Windows wrapper is invisible after toggle"
        assert root.winfo_viewable(), "Tk root is not viewable after toggle"
        assert win._main_container.winfo_viewable()
        assert win.btn_theme.winfo_viewable() and language_button().winfo_viewable()
        assert root.state() == "normal"
    assert visibility_during_idle and all(visibility_during_idle)


@pytest.mark.parametrize("page", ["home", "sandbox", "dict", "vault", "guide"])
def test_language_updates_every_page_without_replacing_inputs_or_scroll(window, page):
    root, win = window
    win._show_page(page)
    win.add_cat_combo.set(win._cat_label("CLIENT"))
    win.filter_cat_combo.set(win._cat_label("PROJECT"))
    win.entry_new_word.insert(0, "Synthetic draft")
    win.entry_allowlist.insert(0, "fictional.invalid")
    win.sandbox_input.delete("1.0", "end")
    win.sandbox_input.insert("1.0", "\n".join(f"synthetic line {i}" for i in range(100)))
    win.sandbox_input.yview_moveto(0.5)
    win.sandbox_input._textbox.tag_add("sel", "42.0", "42.8")
    win._on_sandbox_input_changed()
    pending = win._sandbox_debounce_id
    widgets = (win._main_container, win.sandbox_input, win.sandbox_output,
               win.entry_new_word, win.entry_allowlist, win.vault_search_var, win.guide_box)
    pages = dict(win.pages)
    view = win.sandbox_input.yview()
    selection = win.sandbox_input._textbox.tag_ranges("sel")
    for _ in range(2):
        win._toggle_language()
        assert win.sanitizer.language == win.lang
        assert widgets == (win._main_container, win.sandbox_input, win.sandbox_output,
                           win.entry_new_word, win.entry_allowlist, win.vault_search_var, win.guide_box)
        assert win.pages == pages and win._active_page_key == page
        assert win.entry_new_word.get() == "Synthetic draft"
        assert win.entry_allowlist.get() == "fictional.invalid"
        assert win.add_cat_combo.get() == win._cat_label("CLIENT")
        assert win.filter_cat_combo.get() == win._cat_label("PROJECT")
        assert win.sandbox_input.yview() == view
        assert win.sandbox_input._textbox.tag_ranges("sel") == selection
        assert win._sandbox_debounce_id == pending
        for widget, (key, option, prefix) in win._translation_bindings.items():
            if widget.winfo_exists() and key != "btn_hk_record":
                assert widget.cget(option) == prefix + win._t(key)
        assert win.guide_box.get("1.0", "end-1c") == win._guide_text()
        assert "CTRL+SHIFT+R" in win.guide_box.get("1.0", "end-1c")
        assert win.nav_bar.get() == win._nav_key_to_label[page]


def test_failed_language_save_restores_visible_text_without_destroying_inputs(window, monkeypatch):
    root, win = window
    old_lang = win.lang
    before = win.sanitizer.config_path.read_bytes()
    container = win._main_container
    win.entry_new_word.insert(0, "Unsaved synthetic draft")
    monkeypatch.setattr("src.sanitizer.atomic_write_private", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic")))
    win._toggle_language()
    assert win.lang == win.sanitizer.language == old_lang
    assert win.sanitizer.config_path.read_bytes() == before
    assert win._main_container is container and container.winfo_exists()
    assert win.entry_new_word.get() == "Unsaved synthetic draft"
    for widget, (key, option, prefix) in win._translation_bindings.items():
        if widget.winfo_exists():
            assert widget.cget(option) == prefix + win._t(key)


def test_sandbox_aggregate_status_changes_language_without_retaining_raw_result(window):
    root, win = window
    win.sandbox_input.delete("1.0", "end")
    win.sandbox_input.insert("1.0", "password=synthetic-only")
    win._run_sandbox_sanitize()
    original_input = win.sandbox_input.get("1.0", "end-1c")
    masked_output = win.sandbox_output.get("1.0", "end-1c")
    win._toggle_language()
    assert win.status_var.get() == win._sandbox_status_texts[win.lang]
    assert "Masked" in win.status_var.get() or "masked" in win.status_var.get()
    assert win.sandbox_input.get("1.0", "end-1c") == original_input
    assert win.sandbox_output.get("1.0", "end-1c") == masked_output
    assert all("synthetic-only" not in text for text in win._sandbox_status_texts.values())
    win._run_sandbox_restore()
    win._toggle_language()
    assert win.status_var.get() == win._sandbox_status_texts[win.lang]
    assert "已还原" in win.status_var.get()


def test_main_window_uses_short_brand_without_a_visible_version(window):
    from src import APP_NAME, __version__
    from src import main as app_module
    root, win = window
    assert APP_NAME == app_module.APP_NAME == "Sanitizer"
    for _ in range(2):
        assert root.title() == APP_NAME
        assert __version__ not in win.status_var.get()
        pending = [win._main_container]
        while pending:
            widget = pending.pop()
            if isinstance(widget, (ctk.CTkLabel, ctk.CTkButton, ctk.CTkSwitch)):
                text = widget.cget("text") or ""
                assert "AI Privacy Sanitizer" not in text
                assert __version__ not in text
            pending.extend(widget.winfo_children())
        win._toggle_language()


def test_about_owns_version_is_reused_and_translates_in_place(window):
    from src import __version__
    root, win = window
    win._show_about()
    modal = win._about_modal
    assert modal.title() == win._t("about_title")
    assert __version__ in win._about_version_label.cget("text")
    win._show_about()
    assert win._about_modal is modal
    win._toggle_language()
    assert win._about_modal is modal
    assert modal.title() == win._t("about_title")
    assert win._about_version_label.cget("text") == win._t("about_version").format(version=__version__)
    modal.destroy()
    win._toggle_language()
    win._show_about()
    assert win._about_modal is not modal


@pytest.mark.parametrize("operation", ["theme", "language"])
def test_second_click_without_reentering_button_at_200ms(window, operation):
    """Exercise the click-animation timer, without synthesizing another hover."""
    root, win = window
    root.geometry("940x660+20000+20000")
    root.deiconify()
    root.update()
    button = None
    pending = [win._main_container]
    while pending:
        widget = pending.pop()
        if isinstance(widget, ctk.CTkButton) and widget.cget("command") == getattr(win, "_toggle_" + operation):
            button = widget
            break
        pending.extend(widget.winfo_children())
    assert button is not None
    original = win.lang if operation == "language" else win.theme_mode
    button._canvas.event_generate("<Enter>", x=10, y=10)
    button._canvas.event_generate("<ButtonPress-1>", x=10, y=10)
    button._canvas.event_generate("<ButtonRelease-1>", x=10, y=10)
    assert (win.lang if operation == "language" else win.theme_mode) != original
    root.after(200, root.quit)
    root.mainloop()
    button._canvas.event_generate("<ButtonPress-1>", x=10, y=10)
    button._canvas.event_generate("<ButtonRelease-1>", x=10, y=10)
    assert (win.lang if operation == "language" else win.theme_mode) == original


@pytest.mark.parametrize("operation", ["theme", "language"])
@pytest.mark.parametrize("surface", ["_canvas", "_text_label"])
def test_preference_click_uses_release_position_after_child_leave(window, operation, surface):
    """A label relayout can leave the cached hover flag false under the pointer."""
    root, win = window
    root.geometry("940x660+20000+20000")
    root.deiconify()
    root.update()
    pending = [win._main_container]
    button = None
    while pending:
        widget = pending.pop()
        if isinstance(widget, ctk.CTkButton) and widget.cget("command") == getattr(win, "_toggle_" + operation):
            button = widget
            break
        pending.extend(widget.winfo_children())
    assert button is not None
    original = win.lang if operation == "language" else win.theme_mode
    for _ in range(2):
        target = getattr(button, surface)
        target.event_generate("<Enter>", x=2, y=2)
        target.event_generate("<ButtonPress-1>", x=2, y=2)
        # The text/canvas are child windows; changing text/layout can deliver
        # Leave without a new Enter even though the release is inside the button.
        target.event_generate("<Leave>", x=2, y=2)
        assert not button._mouse_inside
        before = win.lang if operation == "language" else win.theme_mode
        target.event_generate("<ButtonRelease-1>", x=2, y=2)
        assert (win.lang if operation == "language" else win.theme_mode) != before
        root.update_idletasks()
    assert (win.lang if operation == "language" else win.theme_mode) == original


def test_preference_release_respects_disabled_and_outside_bounds(window):
    root, win = window
    root.geometry("940x660+20000+20000")
    root.deiconify()
    root.update()
    button = win.btn_theme
    original = win.theme_mode
    button.configure(state="disabled")
    button._canvas.event_generate("<ButtonRelease-1>", x=2, y=2)
    assert win.theme_mode == original
    button.configure(state="normal")
    button._canvas.event_generate("<Enter>", x=2, y=2)
    button._canvas.event_generate("<ButtonRelease-1>", x=-10, y=2)
    assert win.theme_mode == original
    button._canvas.event_generate("<ButtonRelease-1>", x=button.winfo_width()+10, y=2)
    assert win.theme_mode == original
    # A second release during CTk's 100ms animation must still be accepted.
    for _ in range(2):
        before = win.theme_mode
        button._canvas.event_generate("<ButtonRelease-1>", x=2, y=2)
        assert win.theme_mode != before
    assert win.theme_mode == original


def test_language_keeps_segment_buttons_and_never_flushes_partial_translations(window, monkeypatch):
    root, win = window
    bars = (win.nav_bar, win.dict_mode_seg)
    buttons = [tuple(bar._buttons_dict.values()) for bar in bars]
    flushes = []
    original_idle = tk.Misc.update_idletasks
    def idle(widget):
        flushes.append(widget)
        return original_idle(widget)
    monkeypatch.setattr(tk.Misc, 'update_idletasks', idle)
    win._toggle_language()
    assert not flushes, 'Language callback exposed a partial update to Tk paint/layout'
    for bar, original_buttons in zip(bars, buttons):
        assert tuple(bar._buttons_dict.values()) == original_buttons
        assert all(button.winfo_exists() for button in original_buttons)
    for _ in range(2):
        for page in win._nav_keys:
            win.nav_bar._buttons_dict[win._nav_key_to_label[page]].invoke()
            assert win._active_page_key == page
        for mode in ('words', 'rules'):
            label = win._dict_mode_labels[mode == 'rules']
            win.dict_mode_seg._buttons_dict[label].invoke()
            assert win._dict_submode == mode
        win._toggle_language()


@pytest.mark.parametrize('mode', ['Light', 'Dark'])
def test_language_retains_native_text_colors_and_left_anchored_descriptions(window, mode):
    root, win = window
    ctk.set_appearance_mode(mode)
    root.update_idletasks()
    pending = [win._main_container]
    labels = {}
    while pending:
        widget = pending.pop()
        if isinstance(widget, tk.Label):
            labels[widget] = (widget.cget('foreground'), widget.cget('background'))
        pending.extend(widget.winfo_children())
    for _ in range(2):
        win._toggle_language()
        for label, colors in labels.items():
            assert label.winfo_exists()
            assert (label.cget('foreground'), label.cget('background')) == colors
        for widget, (key, option, prefix) in win._translation_bindings.items():
            if key.startswith('sw_') and isinstance(widget, ctk.CTkLabel):
                assert widget.cget('anchor') == 'w'


@pytest.mark.parametrize('mode', ['Light', 'Dark'])
def test_bilingual_home_text_dimensions_do_not_grow_when_english_is_selected(window, mode):
    root, win = window
    ctk.set_appearance_mode(mode)
    root.geometry('940x660+20000+20000')
    root.deiconify()
    root.update()
    labels = {}
    for widget, (key, option, prefix) in win._translation_bindings.items():
        label = getattr(widget, '_label', getattr(widget, '_text_label', None))
        if label is not None:
            labels[key] = (widget, label, (widget.winfo_width(), widget.winfo_height(),
                                         label.winfo_width(), label.winfo_height()))
    for _ in range(4):
        win._toggle_language()
        root.update_idletasks()
        for key, (widget, label, dimensions) in labels.items():
            assert (widget.winfo_width(), widget.winfo_height(),
                    label.winfo_width(), label.winfo_height()) == dimensions, key
        assert win.sanitizer.hotkeys == {'sanitize':'alt+s', 'restore':'ctrl+shift+r'}
