"""Modern Dark/Light Bilingual Sidebar GUI Control Center using CustomTkinter."""

import ctypes
import gc
import io
import json
import math
from pathlib import Path
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import weakref
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import customtkinter as ctk

from src import APP_NAME, __version__
from src.file_batch import process_batch_paths
from src.hud import FloatingMicroHud
from src.i18n import tr
from src.regex_safety import ALLOWED_PLACEHOLDER_TEMPLATES, RegexSafetyError, sanitize_category_name
from src.rules import BUILTIN_RULES, SAMPLE_TEST_PAYLOAD
from src.sanitizer import (
    HotkeyRollbackError,
    InputTooLargeError,
    MAX_SANITIZE_CHARS,
    PrivacySanitizer,
    SessionVault,
    VALID_IDLE_WIPE_MINUTES,
)
from src.secure_io import atomic_write_private
from src.startup import is_startup_enabled, set_startup_enabled
from src.win_drop import WindowsFileDropTarget


def enable_high_dpi_awareness() -> None:
    """Enable Windows Per-Monitor High-DPI awareness so fonts and widgets render razor-sharp."""
    if platform.system() != "Windows":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _platform_font_families() -> Tuple[str, str]:
    """Select crisp native UI and monospace font families per OS."""
    sys_name = platform.system()
    if sys_name == "Windows":
        return "Microsoft YaHei UI", "Consolas"
    if sys_name == "Darwin":
        return "PingFang SC", "Menlo"
    return "DejaVu Sans", "DejaVu Sans Mono"


def _is_transient_windows_tcl_init_error(exc: BaseException) -> bool:
    """Return True when Windows Tk/Tcl raises the transient init.tcl 'No error' race."""
    if sys.platform != "win32" or not isinstance(exc, tk.TclError):
        return False
    msg = str(exc).lower()
    return "init.tcl" in msg and "no error" in msg


class _StableCTk(ctk.CTk):
    """Apply the Windows titlebar color without CustomTkinter's withdraw/deiconify cycle."""

    def __init__(self, *args, **kwargs) -> None:
        if not hasattr(ctypes, "windll"):
            ctk.deactivate_automatic_dpi_awareness()
        kwargs.setdefault("fg_color", ("#f1f5f9", "#0b0f19"))
        for attempt in range(5):
            try:
                super().__init__(*args, **kwargs)
                return
            except tk.TclError as exc:
                if (
                    attempt == 4
                    or getattr(self, "tk", None) is not None
                    or not _is_transient_windows_tcl_init_error(exc)
                ):
                    raise
                gc.collect()
                time.sleep(0.05 * (attempt + 1))

    def _windows_set_titlebar_color(self, color_mode: str) -> None:
        if platform.system() != "Windows":
            return
        try:
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            hwnd = user32.GetParent(self.winfo_id())
            value = ctypes.c_int(color_mode.lower() == "dark")
            setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
            setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            setter.restype = ctypes.c_long
            if setter(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)) != 0:
                setter(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
        except (AttributeError, OSError, tk.TclError):
            pass


class _StableCTkToplevel(ctk.CTkToplevel):
    _windows_set_titlebar_color = _StableCTk._windows_set_titlebar_color


class _PreferenceButton(ctk.CTkButton):
    """Use release coordinates when child relayout leaves cached hover stale."""

    def _on_release(self, event=None):
        if event is not None:
            try:
                x = event.widget.winfo_rootx() + event.x - self.winfo_rootx()
                y = event.widget.winfo_rooty() + event.y - self.winfo_rooty()
                inside = 0 <= x < self.winfo_width() and 0 <= y < self.winfo_height()
            except (AttributeError, tk.TclError):
                return
            if not inside:
                self._on_leave()
                return
            self._mouse_inside = True
        return super()._on_release(event)


_TK_KEYSYM_TO_TOKEN: Dict[str, str] = {
    "return": "enter",
    "kp_enter": "enter",
    "space": "space",
    "tab": "tab",
    "backspace": "backspace",
    "insert": "insert",
    "delete": "delete",
    "home": "home",
    "end": "end",
    "prior": "pageup",
    "page_up": "pageup",
    "next": "pagedown",
    "page_down": "pagedown",
    "left": "left",
    "up": "up",
    "right": "right",
    "down": "down",
    "caps_lock": "capslock",
    "num_lock": "numlock",
    "scroll_lock": "scrolllock",
    "pause": "pause",
    "print": "printscreen",
    "grave": "`",
    "asciitilde": "`",
    "minus": "-",
    "underscore": "-",
    "equal": "=",
    "plus": "=",
    "bracketleft": "[",
    "braceleft": "[",
    "bracketright": "]",
    "braceright": "]",
    "backslash": "\\",
    "bar": "\\",
    "semicolon": ";",
    "colon": ";",
    "apostrophe": "'",
    "quotedbl": "'",
    "comma": ",",
    "less": ",",
    "period": ".",
    "greater": ".",
    "slash": "/",
    "question": "/",
    "exclam": "1",
    "at": "2",
    "numbersign": "3",
    "dollar": "4",
    "percent": "5",
    "asciicircum": "6",
    "ampersand": "7",
    "asterisk": "8",
    "parenleft": "9",
    "parenright": "0",
    "kp_add": "num_add",
    "kp_subtract": "num_sub",
    "kp_multiply": "num_mul",
    "kp_divide": "num_div",
    "kp_decimal": "num_dec",
    **{f"kp_{d}": f"num{d}" for d in range(10)},
}

_WIN_VK_TO_TOKEN: Dict[int, str] = {
    0x08: "backspace",
    0x09: "tab",
    0x0D: "enter",
    0x13: "pause",
    0x14: "capslock",
    0x20: "space",
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2C: "printscreen",
    0x2D: "insert",
    0x2E: "delete",
    0x6A: "num_mul",
    0x6B: "num_add",
    0x6D: "num_sub",
    0x6E: "num_dec",
    0x6F: "num_div",
    0x90: "numlock",
    0x91: "scrolllock",
    0xBA: ";",
    0xBB: "=",
    0xBC: ",",
    0xBD: "-",
    0xBE: ".",
    0xBF: "/",
    0xC0: "`",
    0xDB: "[",
    0xDC: "\\",
    0xDD: "]",
    0xDE: "'",
    **{0x30 + d: str(d) for d in range(10)},
    **{0x41 + i: chr(ord("a") + i) for i in range(26)},
    **{0x60 + d: f"num{d}" for d in range(10)},
    **{0x70 + i: f"f{i + 1}" for i in range(24)},
}

_PURE_MODIFIER_KEYSYMS: Dict[str, str] = {
    "Control_L": "ctrl",
    "Control_R": "ctrl",
    "Alt_L": "alt",
    "Alt_R": "alt",
    "Shift_L": "shift",
    "Shift_R": "shift",
    "Win_L": "win",
    "Win_R": "win",
    "Super_L": "win",
    "Super_R": "win",
    "Meta_L": "win",
    "Meta_R": "win",
}

_PURE_MODIFIER_VKS: Dict[int, str] = {
    0x10: "shift",
    0x11: "ctrl",
    0x12: "alt",
    0x5B: "win",
    0x5C: "win",
    0xA0: "shift",
    0xA1: "shift",
    0xA2: "ctrl",
    0xA3: "ctrl",
    0xA4: "alt",
    0xA5: "alt",
}


def format_hotkey_display(chord: str) -> str:
    """Format a normalized shortcut chord into spaced uppercase badges (e.g. CTRL + SHIFT + S)."""
    cleaned = re.sub(r"\s+", "", str(chord or "").strip().lower())
    if not cleaned:
        return ""
    return " + ".join(part.upper() for part in cleaned.split("+") if part)


def normalize_tk_key_event(
    event,
    *,
    is_windows: Optional[bool] = None,
) -> Tuple[List[str], Optional[str], bool]:
    """Extract (ordered_modifiers, trigger_key_or_none, is_pure_modifier) from a Tk key event."""
    keysym = str(getattr(event, "keysym", "") or "")
    keycode = int(getattr(event, "keycode", 0) or 0)
    state = int(getattr(event, "state", 0) or 0)
    win_platform = (platform.system() == "Windows") if is_windows is None else bool(is_windows)

    mods_set = set()
    if state & 0x0004:
        mods_set.add("ctrl")
    if state & 0x0001:
        mods_set.add("shift")
    if win_platform:
        # On Windows Tk, 0x0008 is NumLock (Mod1) and 0x20000 is the Alt modifier bit.
        if state & 0x20000:
            mods_set.add("alt")
    else:
        if state & 0x20000 or state & 0x0008:
            mods_set.add("alt")
        if state & 0x0040:
            mods_set.add("win")

    # On live Windows events, also poll async modifier state so Win / AltGr work reliably.
    if platform.system() == "Windows" and isinstance(event, tk.Event):
        try:
            user32 = ctypes.windll.user32
            if user32.GetAsyncKeyState(0x11) & 0x8000:
                mods_set.add("ctrl")
            if user32.GetAsyncKeyState(0x12) & 0x8000:
                mods_set.add("alt")
            if user32.GetAsyncKeyState(0x10) & 0x8000:
                mods_set.add("shift")
            if (user32.GetAsyncKeyState(0x5B) & 0x8000) or (user32.GetAsyncKeyState(0x5C) & 0x8000):
                mods_set.add("win")
        except Exception:
            pass

    pure_mod = _PURE_MODIFIER_KEYSYMS.get(keysym) or _PURE_MODIFIER_VKS.get(keycode)
    if pure_mod is not None:
        mods_set.add(pure_mod)
        ordered = [m for m in ("ctrl", "alt", "shift", "win") if m in mods_set]
        return ordered, None, True

    ordered = [m for m in ("ctrl", "alt", "shift", "win") if m in mods_set]
    key_lower = keysym.lower()

    token: Optional[str] = None
    if key_lower in _TK_KEYSYM_TO_TOKEN:
        token = _TK_KEYSYM_TO_TOKEN[key_lower]
    elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key_lower):
        token = key_lower
    elif len(key_lower) == 1 and (key_lower.isalnum() or key_lower in "`-=[]\\;',./"):
        token = key_lower
    elif keycode in _WIN_VK_TO_TOKEN:
        token = _WIN_VK_TO_TOKEN[keycode]
    elif key_lower and key_lower != "??":
        token = key_lower

    return ordered, token, False


class _HotkeyRecorderBox(ctk.CTkFrame):
    """IDE-style click-to-record shortcut pill with optional inline manual input."""

    def __init__(
        self,
        master,
        *,
        value: str,
        font: ctk.CTkFont,
        listening_text: str,
        on_start_record: Callable[[], None],
        on_manual_commit: Callable[[str], None],
        on_manual_cancel: Callable[[], None],
        on_edit_state_changed: Optional[Callable[[bool], None]] = None,
        width: int = 230,
        height: int = 34,
    ) -> None:
        super().__init__(master, width=width, height=height, fg_color="transparent")
        self.pack_propagate(False)
        self._value = str(value or "alt+s").strip().lower()
        self._listening_text = listening_text
        self._recording = False
        self._editing = False
        self._on_manual_commit = on_manual_commit
        self._on_manual_cancel = on_manual_cancel
        self._on_edit_state_changed = on_edit_state_changed

        self._normal_fg = ("#f8fafc", "#0f172a")
        self._normal_hover = ("#e2e8f0", "#1e293b")
        self._normal_border = ("#cbd5e1", "#475569")
        self._normal_text = ("#0f172a", "#f8fafc")

        self._rec_fg = ("#eff6ff", "#172554")
        self._rec_border = ("#2563eb", "#60a5fa")
        self._rec_text = ("#1d4ed8", "#93c5fd")

        self._pill_btn = ctk.CTkButton(
            self,
            text=format_hotkey_display(self._value),
            font=font,
            width=width,
            height=height,
            corner_radius=8,
            border_width=1,
            border_color=self._normal_border,
            fg_color=self._normal_fg,
            hover_color=self._normal_hover,
            text_color=self._normal_text,
            cursor="hand2",
            command=on_start_record,
        )
        self._pill_btn.pack(fill="both", expand=True)

        self._entry = ctk.CTkEntry(
            self,
            width=width,
            height=height,
            corner_radius=8,
            font=font,
        )
        self._entry.bind("<Return>", self._handle_entry_return)
        self._entry.bind("<Escape>", self._handle_entry_escape)

    def get(self) -> str:
        if self._editing:
            return self._entry.get().strip().lower()
        return self._value

    def _notify_edit_state(self, editing: bool) -> None:
        if self._on_edit_state_changed is not None:
            try:
                self._on_edit_state_changed(bool(editing))
            except Exception:
                pass

    def set(self, value: str) -> None:
        self._value = re.sub(r"\s+", "", str(value or "").strip().lower())
        if self._editing:
            self._editing = False
            self._entry.pack_forget()
            self._pill_btn.pack(fill="both", expand=True)
            self._move_focus_out_of_entry()
            self._notify_edit_state(False)
        if not self._recording:
            self._pill_btn.configure(text=format_hotkey_display(self._value))

    def set_listening_text(self, listening_text: str) -> None:
        self._listening_text = listening_text
        if self._recording:
            self._pill_btn.configure(text=self._listening_text)

    def set_recording(self, active: bool, preview: str = "") -> None:
        if self._editing and active:
            self.finish_manual_edit(commit=False)
        self._recording = bool(active)
        if self._recording:
            self._pill_btn.configure(
                fg_color=self._rec_fg,
                hover_color=self._rec_fg,
                border_width=2,
                border_color=self._rec_border,
                text_color=self._rec_text,
                text=preview or self._listening_text,
            )
        else:
            self._pill_btn.configure(
                fg_color=self._normal_fg,
                hover_color=self._normal_hover,
                border_width=1,
                border_color=self._normal_border,
                text_color=self._normal_text,
                text=format_hotkey_display(self._value),
            )

    def start_manual_edit(self) -> None:
        if self._editing:
            self.finish_manual_edit(commit=False)
            return
        self._editing = True
        self._pill_btn.pack_forget()
        self._entry.delete(0, "end")
        self._entry.insert(0, self._value)
        self._entry.pack(fill="both", expand=True)
        self._entry.focus_set()
        self._entry.select_range(0, "end")
        self._notify_edit_state(True)

    def _move_focus_out_of_entry(self) -> None:
        try:
            focus_w = self.focus_get()
            inner_entry = getattr(self._entry, "_entry", None)
            if focus_w is not None and (focus_w is self._entry or focus_w is inner_entry):
                self._pill_btn.focus_set()
        except Exception:
            pass

    def finish_manual_edit(self, *, commit: bool) -> None:
        if not self._editing:
            return
        typed = self._entry.get().strip().lower()
        self._editing = False
        self._entry.pack_forget()
        self._pill_btn.pack(fill="both", expand=True)
        self._move_focus_out_of_entry()
        if commit and typed:
            self._value = re.sub(r"\s+", "", typed)
        self._pill_btn.configure(text=format_hotkey_display(self._value))
        self._notify_edit_state(False)

    def _handle_entry_return(self, _event=None) -> str:
        typed = self._entry.get().strip().lower()
        self.finish_manual_edit(commit=True)
        self._on_manual_commit(typed)
        return "break"

    def _handle_entry_escape(self, _event=None) -> str:
        self.finish_manual_edit(commit=False)
        self._on_manual_cancel()
        return "break"


class _SidebarNav(ctk.CTkFrame):
    """Vertical sidebar navigation exposing the same in-place relabel contract as CTkSegmentedButton."""

    def __init__(
        self,
        master,
        values: List[str],
        font: ctk.CTkFont,
        command: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._value_list: List[str] = list(values)
        self._command = command
        self._current_value: str = values[0] if values else ""
        self._buttons_dict: Dict[str, ctk.CTkButton] = {}
        self._selected_fg = ("#2563eb", "#2563eb")
        self._selected_hover = ("#1d4ed8", "#1d4ed8")
        self._unselected_fg = "transparent"
        self._unselected_hover = ("#e2e8f0", "#1e293b")
        self._selected_text = ("#ffffff", "#ffffff")
        self._unselected_text = ("#334155", "#cbd5e1")

        for val in self._value_list:
            btn = _PreferenceButton(
                self,
                text=val,
                font=font,
                height=36,
                corner_radius=9,
                anchor="w",
                fg_color=self._unselected_fg,
                hover_color=self._unselected_hover,
                text_color=self._unselected_text,
                command=lambda v=val: self.set(v, from_button_callback=True),
            )
            btn.pack(fill="x", pady=2)
            self._buttons_dict[val] = btn

    def cget(self, attribute_name: str):
        if attribute_name == "values":
            return list(self._value_list)
        return super().cget(attribute_name)

    def get(self) -> str:
        return self._current_value

    def set(self, value: str, from_button_callback: bool = False) -> None:
        if value not in self._buttons_dict:
            return
        self._current_value = value
        for val, btn in self._buttons_dict.items():
            if val == value:
                btn.configure(
                    fg_color=self._selected_fg,
                    hover_color=self._selected_hover,
                    text_color=self._selected_text,
                )
            else:
                btn.configure(
                    fg_color=self._unselected_fg,
                    hover_color=self._unselected_hover,
                    text_color=self._unselected_text,
                )
        if from_button_callback and self._command is not None:
            self._command(value)


CATEGORY_KEYS = ["COMPANY", "CLIENT", "PROJECT", "CUSTOM_SECRET"]

CATEGORY_BADGE_COLORS: Dict[str, tuple] = {
    "COMPANY": ("#d1fae5", "#064e3b"),
    "CLIENT": ("#fce7f3", "#831843"),
    "PROJECT": ("#fef3c7", "#78350f"),
    "CUSTOM_SECRET": ("#ede9fe", "#4c1d95"),
}

# Risk-tiered semantic highlight palette for Sandbox & Category Pills
RISK_TIERS: Dict[str, str] = {
    "PRIVATE_KEY": "api",
    "API_KEY": "api",
    "HIGH_ENTROPY": "api",
    "DB_PASS": "pass",
    "ID_CARD": "pii",
    "BANK_CARD": "pii",
    "PASSPORT": "pii",
    "PHONE": "pii",
    "EMAIL": "pii",
    "USER_ID": "pii",
    "PRIVATE_IP": "net",
    "PUBLIC_IP": "net",
    "IPV6": "net",
    "MAC_ADDR": "net",
    "USER_PATH": "net",
}

RISK_TAG_STYLES = {
    "dark": {
        "api": ("#7f1d1d", "#fca5a5"),
        "pass": ("#78350f", "#fcd34d"),
        "pii": ("#581c87", "#d8b4fe"),
        "net": ("#1e3a8a", "#93c5fd"),
        "biz": ("#064e3b", "#6ee7b7"),
    },
    "light": {
        "api": ("#fee2e2", "#991b1b"),
        "pass": ("#fef3c7", "#92400e"),
        "pii": ("#f3e8ff", "#6b21a8"),
        "net": ("#dbeafe", "#1e40af"),
        "biz": ("#d1fae5", "#065f46"),
    },
}

_VAULT_PAGE_SIZE = 60

_DEFAULT_HOTKEY_CANDIDATES: Tuple[Tuple[str, str], ...] = (
    ("alt+s", "alt+r"),
    ("alt+s", "ctrl+shift+r"),
    ("ctrl+shift+s", "ctrl+shift+r"),
    ("ctrl+alt+s", "ctrl+alt+r"),
)


class GuiController:
    """Thread-safe CustomTkinter GUI manager that hides to tray on close and re-opens on demand."""

    def __init__(
        self,
        sanitizer: PrivacySanitizer,
        icon_factory: Optional[Callable[[int], object]] = None,
        on_sanitize_clipboard: Optional[Callable[[], None]] = None,
        on_restore_clipboard: Optional[Callable[[], None]] = None,
        on_undo_sanitize: Optional[Callable[[], None]] = None,
        on_open_raw_config: Optional[Callable[[], None]] = None,
        on_exit_app: Optional[Callable[[], None]] = None,
        on_reload_hotkeys: Optional[Callable[[Optional[Dict[str, str]]], bool]] = None,
        on_language_changed: Optional[Callable[[], None]] = None,
        on_clear_session: Optional[Callable[[], None]] = None,
        on_copy_to_clipboard: Optional[Callable[..., bool]] = None,
        on_state_changed: Optional[Callable[[], None]] = None,
        get_idle_seconds_left: Optional[Callable[[], Optional[int]]] = None,
        get_last_hotkey_conflict: Optional[Callable[[], Optional[str]]] = None,
        get_hotkey_status: Optional[Callable[[], Dict[str, Any]]] = None,
        on_auto_fix_hotkeys: Optional[Callable[[], Tuple[bool, Dict[str, str], Optional[str]]]] = None,
        get_last_clipboard_record: Optional[Callable[[], Any]] = None,
        on_allowlist_and_rerun: Optional[Callable[[str], Tuple[bool, str]]] = None,
    ) -> None:
        self.sanitizer = sanitizer
        self.icon_factory = icon_factory
        self.on_sanitize_clipboard = on_sanitize_clipboard
        self.on_restore_clipboard = on_restore_clipboard
        self.on_undo_sanitize = on_undo_sanitize
        self.on_open_raw_config = on_open_raw_config
        self.on_exit_app = on_exit_app
        self.on_reload_hotkeys = on_reload_hotkeys
        self.on_language_changed = on_language_changed
        self.on_clear_session = on_clear_session
        self.on_copy_to_clipboard = on_copy_to_clipboard
        self.on_state_changed = on_state_changed
        self.get_idle_seconds_left = get_idle_seconds_left
        self.get_last_hotkey_conflict = get_last_hotkey_conflict
        self.get_hotkey_status = get_hotkey_status
        self.on_auto_fix_hotkeys = on_auto_fix_hotkeys
        self.get_last_clipboard_record = get_last_clipboard_record
        self.on_allowlist_and_rerun = on_allowlist_and_rerun
        self.startup_status: Optional[str] = None
        self._cmd_queue: "queue.Queue[object]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()

    def ensure_started(self) -> None:
        pass

    def show_window(self) -> None:
        """Request the GUI window to appear on the Home Dashboard."""
        self._cmd_queue.put("SHOW")

    def show_json_editor(self) -> None:
        """Request the GUI window to appear and open the built-in JSON editor modal."""
        self._cmd_queue.put("SHOW_JSON")

    def request_refresh(self) -> None:
        """Request the GUI window to refresh all stats and vault lists on the main UI thread."""
        self._cmd_queue.put("REFRESH")

    def show_hud(self, title: str, message: str, *, tone: str = "info") -> None:
        """Queue a non-focus-stealing Micro-HUD toast on the main UI thread."""
        self._cmd_queue.put(("HUD", title, message, tone))

    def set_status(self, text: str) -> None:
        """Queue a footer status update on the main UI thread."""
        self._cmd_queue.put(("STATUS", text))

    def shutdown(self) -> None:
        """Request the CustomTkinter loop to terminate cleanly."""
        self._cmd_queue.put("QUIT")

    def run_main_loop(
        self, show_on_start: bool = True, before_mainloop: Optional[Callable[[], None]] = None
    ) -> None:
        """Run CustomTkinter on the main thread (recommended for Windows DWM & OLE dialogs)."""
        enable_high_dpi_awareness()
        ctk.set_default_color_theme("blue")
        initial_theme = "Light" if self.sanitizer.theme == "light" else "Dark"
        ctk.set_appearance_mode(initial_theme)

        root = _StableCTk()
        if not show_on_start:
            root.withdraw()

        hud = FloatingMicroHud(root)
        app_win = _ModernControlCenter(
            root=root,
            sanitizer=self.sanitizer,
            icon_factory=self.icon_factory,
            on_sanitize_clipboard=self.on_sanitize_clipboard,
            on_restore_clipboard=self.on_restore_clipboard,
            on_undo_sanitize=self.on_undo_sanitize,
            on_exit_app=self.on_exit_app,
            on_reload_hotkeys=self.on_reload_hotkeys,
            on_language_changed=self.on_language_changed,
            on_clear_session=self.on_clear_session,
            on_copy_to_clipboard=self.on_copy_to_clipboard,
            on_state_changed=self.on_state_changed,
            get_idle_seconds_left=self.get_idle_seconds_left,
            get_last_hotkey_conflict=self.get_last_hotkey_conflict,
            get_hotkey_status=self.get_hotkey_status,
            on_auto_fix_hotkeys=self.on_auto_fix_hotkeys,
            get_last_clipboard_record=self.get_last_clipboard_record,
            on_allowlist_and_rerun=self.on_allowlist_and_rerun,
        )
        if self.startup_status:
            app_win.status_var.set(self.startup_status)
        if show_on_start:
            root.after(80, app_win.present)

        self._started.set()
        tick_counter = [0]

        def _poll_commands() -> None:
            try:
                while True:
                    cmd = self._cmd_queue.get_nowait()
                    if cmd == "SHOW":
                        app_win.present()
                    elif cmd == "SHOW_JSON":
                        app_win.present()
                        app_win.open_in_app_json_modal()
                    elif cmd == "REFRESH":
                        app_win.refresh_all()
                    elif isinstance(cmd, tuple) and cmd and cmd[0] == "HUD":
                        _, h_title, h_msg, h_tone = cmd
                        hud.show(h_title, h_msg, tone=h_tone)
                    elif isinstance(cmd, tuple) and cmd and cmd[0] == "STATUS":
                        _, status_text = cmd
                        app_win.status_var.set(status_text)
                    elif cmd == "QUIT":
                        app_win.detach_drop_target()
                        hud.destroy()
                        root.quit()
                        root.destroy()
                        return
            except queue.Empty:
                pass
            tick_counter[0] += 1
            if tick_counter[0] % 8 == 0:
                app_win._update_idle_readout()
            root.after(120, _poll_commands)

        if before_mainloop is not None:
            before_mainloop()
        root.after(120, _poll_commands)
        root.mainloop()


class _ModernControlCenter:
    """Sleek modern Dark/Light bilingual Sidebar desktop UI built with CustomTkinter."""

    def __init__(
        self,
        root: ctk.CTk,
        sanitizer: PrivacySanitizer,
        icon_factory: Optional[Callable[[int], object]] = None,
        on_sanitize_clipboard: Optional[Callable[[], None]] = None,
        on_restore_clipboard: Optional[Callable[[], None]] = None,
        on_undo_sanitize: Optional[Callable[[], None]] = None,
        on_exit_app: Optional[Callable[[], None]] = None,
        on_reload_hotkeys: Optional[Callable[[Optional[Dict[str, str]]], bool]] = None,
        on_language_changed: Optional[Callable[[], None]] = None,
        on_clear_session: Optional[Callable[[], None]] = None,
        on_copy_to_clipboard: Optional[Callable[..., bool]] = None,
        on_state_changed: Optional[Callable[[], None]] = None,
        get_idle_seconds_left: Optional[Callable[[], Optional[int]]] = None,
        get_last_hotkey_conflict: Optional[Callable[[], Optional[str]]] = None,
        get_hotkey_status: Optional[Callable[[], Dict[str, Any]]] = None,
        on_auto_fix_hotkeys: Optional[Callable[[], Tuple[bool, Dict[str, str], Optional[str]]]] = None,
        get_last_clipboard_record: Optional[Callable[[], Any]] = None,
        on_allowlist_and_rerun: Optional[Callable[[str], Tuple[bool, str]]] = None,
    ) -> None:
        self.root = root
        self.sanitizer = sanitizer
        self.on_sanitize_clipboard = on_sanitize_clipboard
        self.on_restore_clipboard = on_restore_clipboard
        self.on_undo_sanitize = on_undo_sanitize
        self.on_exit_app = on_exit_app
        self.on_reload_hotkeys = on_reload_hotkeys
        self.on_language_changed = on_language_changed
        self.on_clear_session = on_clear_session
        self.on_copy_to_clipboard = on_copy_to_clipboard
        self.on_state_changed = on_state_changed
        self.get_idle_seconds_left = get_idle_seconds_left
        self.get_last_hotkey_conflict = get_last_hotkey_conflict
        self.get_hotkey_status = get_hotkey_status
        self.on_auto_fix_hotkeys = on_auto_fix_hotkeys
        self.get_last_clipboard_record = get_last_clipboard_record
        self.on_allowlist_and_rerun = on_allowlist_and_rerun
        self._tk_icon = None
        self._json_modal: Optional[ctk.CTkToplevel] = None
        self._about_modal: Optional[ctk.CTkToplevel] = None
        self._active_page_key: str = "home"
        self._dict_submode: str = "words"
        self._reveal_vault_originals: bool = False
        self._recent_reveal_originals: bool = False
        self._drop_mode: str = "sanitize"
        self._drop_target: Optional[WindowsFileDropTarget] = None
        self._last_batch_output_path: Optional[Path] = None
        self._recording_target: Optional[str] = None
        self._sandbox_debounce_id: Optional[str] = None
        self._vault_search_debounce_id: Optional[str] = None
        self._rule_search_debounce_id: Optional[str] = None
        self._vault_render_limit: int = _VAULT_PAGE_SIZE
        self._rule_row_cache: Dict[str, Tuple[ctk.CTkCheckBox, tk.BooleanVar]] = {}
        self._rendered_rule_names: List[str] = []
        self._rendered_allowlist_items: Optional[List[str]] = None
        self._guide_faq_open: bool = False

        # Isolated Sandbox vault (prevents live typing / samples from polluting global SessionVault)
        self._sandbox_vault: SessionVault = SessionVault()
        self._sandbox_isolate: bool = True

        # Persistent UI state across layout operations
        self._saved_sandbox_input: str = SAMPLE_TEST_PAYLOAD.strip()
        self._saved_sandbox_output: str = ""
        self._saved_sandbox_cat_counts: Dict[str, int] = {}
        self._saved_entry_new_word: str = ""
        self._saved_add_cat_key: str = "COMPANY"
        self._saved_filter_cat_key: str = "ALL"
        self._saved_entry_allowlist: str = ""
        self._saved_vault_search: str = ""
        self._saved_rule_search: str = ""
        self._saved_regex_name: str = ""
        self._saved_regex_cat: str = "CUSTOM_REGEX"
        self._saved_regex_tpl: str = ALLOWED_PLACEHOLDER_TEMPLATES[0]
        self._saved_regex_pattern: str = ""
        self._saved_regex_test: str = ""
        self._saved_batch_status: str = ""
        self._saved_hk_sanitize: Optional[str] = None
        self._saved_hk_restore: Optional[str] = None
        self._translation_bindings = weakref.WeakKeyDictionary()
        self._sandbox_status_texts: Dict[str, str] = {}
        self._responsive_wraps: List[tuple] = []
        self._responsive_mode: Dict[str, str] = {}
        self._last_layout_logical_w: int = 0
        self._in_language_toggle: bool = False

        self.lang = self.sanitizer.language
        self.theme_mode = self.sanitizer.theme

        self.root.title(self._t("window_title"))
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        if icon_factory is not None:
            try:
                pil_img = icon_factory(64)
                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                self._tk_icon = tk.PhotoImage(data=buf.getvalue())
                self.root.iconphoto(True, self._tk_icon)
            except Exception:
                pass

        try:
            win_scale = max(1.0, float(ctk.ScalingTracker.get_window_dpi_scaling(self.root)))
        except Exception:
            win_scale = 1.0
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        log_sw = int(screen_w / win_scale) if screen_w > 0 else 1280
        log_sh = int(screen_h / win_scale) if screen_h > 0 else 800
        width = min(1040, max(860, log_sw - 80))
        height = min(690, max(600, log_sh - 100))
        self._initial_logical_width = width
        pos_x = max(20, (log_sw - width) // 2)
        pos_y = max(20, (log_sh - height) // 2)
        self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.root.minsize(840, 580)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        ui_font, mono_font = _platform_font_families()
        self.font_title = ctk.CTkFont(family=ui_font, size=20, weight="bold")
        self.font_h2 = ctk.CTkFont(family=ui_font, size=15, weight="bold")
        self.font_h3 = ctk.CTkFont(family=ui_font, size=13, weight="bold")
        self.font_body = ctk.CTkFont(family=ui_font, size=12)
        self.font_small = ctk.CTkFont(family=ui_font, size=11)
        self.font_stat_num = ctk.CTkFont(family=ui_font, size=24, weight="bold")
        self.font_mono = ctk.CTkFont(family=mono_font, size=12)
        self.font_mono_sm = ctk.CTkFont(family=mono_font, size=11)

        self._main_container: Optional[ctk.CTkFrame] = None
        self.root.bind(
            "<Destroy>",
            lambda ev: self.detach_drop_target() if ev.widget is self.root else None,
            add="+",
        )
        self._build_layout()

    def _t(self, key: str) -> str:
        if platform.system() == "Darwin" and key in ("status_ready", "hotkey_section_desc"):
            key = "macos_preview_hotkeys"
        return tr(self.lang, key)

    def _localized_widget(
        self,
        widget_type,
        master,
        *,
        translation_key: str,
        translation_option: str = "text",
        translation_prefix: str = "",
        **kwargs,
    ):
        """Register the translation key, without replacing the widget when language changes."""
        if widget_type is ctk.CTkLabel:
            kwargs.setdefault("anchor", "w")
        kwargs[translation_option] = translation_prefix + self._t(translation_key)
        widget = widget_type(master, **kwargs)
        if translation_option == "text":
            self._reserve_bilingual_text(
                widget,
                [
                    translation_prefix + self._format_hotkey_text(tr(lang, translation_key))
                    for lang in ("zh", "en")
                ],
            )
        self._translation_bindings[widget] = (translation_key, translation_option, translation_prefix)
        return widget

    @staticmethod
    def _reserve_bilingual_text(widget, variants) -> None:
        """Give native labels constant text dimensions before they are mapped."""
        label = getattr(widget, "_label", getattr(widget, "_text_label", None))
        if label is None:
            return
        font = tkfont.Font(root=widget, font=label.cget("font"))
        probe = tk.Label(
            widget,
            font=label.cget("font"),
            wraplength=label.cget("wraplength"),
            padx=0,
            pady=0,
            borderwidth=0,
        )
        try:
            sizes = []
            for text in variants:
                probe.configure(text=text)
                sizes.append((probe.winfo_reqwidth(), probe.winfo_reqheight()))
            label.configure(
                width=math.ceil(max(w for w, _h in sizes) / max(1, font.measure("0"))),
                height=math.ceil(max(h for _w, h in sizes) / max(1, font.metrics("linespace"))),
            )
        finally:
            probe.destroy()

    def _register_wrap_label(
        self,
        widget: ctk.CTkLabel,
        width_fn: Callable[[int], int],
        variants_fn: Optional[Callable[[], List[str]]] = None,
    ) -> ctk.CTkLabel:
        """Track a label so its wraplength and bilingual bounds adapt to container width."""
        self._responsive_wraps.append((widget, width_fn, variants_fn))
        return widget

    def _on_page_container_configure(self, event: tk.Event) -> None:
        if getattr(self, "_in_language_toggle", False):
            return
        raw_w = int(getattr(event, "width", 0) or 0)
        if raw_w < 120:
            return
        try:
            scale = max(1.0, float(self.page_container._get_widget_scaling()))
        except Exception:
            scale = 1.0
        logical_w = max(280, int(raw_w / scale))
        if abs(logical_w - self._last_layout_logical_w) < 10:
            return
        self._last_layout_logical_w = logical_w
        self._apply_responsive_layout(logical_w)

    def _apply_responsive_layout(self, logical_w: int, *, force: bool = False) -> None:
        """Reflow multi-column cards/toolbars and update label wraplengths without clipping."""
        if logical_w <= 0:
            return
        self._last_layout_logical_w = logical_w

        # 1. Home Hero Buttons (3-up vs 2+1 vs 3-stack, also accounting for actual hotkey length)
        if hasattr(self, "home_btn_row"):
            try:
                scale = max(1.0, float(self.home_btn_row._get_widget_scaling()))
            except Exception:
                scale = 1.0
            def _btn_req(btn) -> int:
                lbl = getattr(btn, "_text_label", None)
                w_px = lbl.winfo_reqwidth() if lbl is not None else btn.winfo_reqwidth()
                return math.ceil(w_px / scale) + 38

            san_w = _btn_req(self.btn_hero_san)
            res_w = _btn_req(self.btn_hero_res)
            undo_w = max(135, _btn_req(self.btn_hero_undo))
            avail_hero = max(260, logical_w - 38)
            if logical_w >= 860 and (san_w + res_w + undo_w + 24) <= avail_hero:
                hero_mode = "wide"
            elif logical_w >= 520 and (max(san_w, res_w) * 2 + 16) <= avail_hero:
                hero_mode = "two_row"
            else:
                hero_mode = "stack"

            if force or self._responsive_mode.get("home_hero") != hero_mode:
                self._responsive_mode["home_hero"] = hero_mode
                for btn in (self.btn_hero_san, self.btn_hero_res, self.btn_hero_undo):
                    btn.grid_forget()
                if hero_mode == "wide":
                    self.home_btn_row.grid_columnconfigure(0, weight=1, uniform="hero2")
                    self.home_btn_row.grid_columnconfigure(1, weight=1, uniform="hero2")
                    self.home_btn_row.grid_columnconfigure(2, weight=0, uniform="")
                    self.btn_hero_san.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=0)
                    self.btn_hero_res.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=0)
                    self.btn_hero_undo.grid(row=0, column=2, sticky="ew", padx=0, pady=0)
                elif hero_mode == "two_row":
                    self.home_btn_row.grid_columnconfigure(0, weight=1, uniform="hero2")
                    self.home_btn_row.grid_columnconfigure(1, weight=1, uniform="hero2")
                    self.home_btn_row.grid_columnconfigure(2, weight=0, uniform="")
                    self.btn_hero_san.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=0)
                    self.btn_hero_res.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=0)
                    self.btn_hero_undo.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=(8, 0))
                else:
                    self.home_btn_row.grid_columnconfigure(0, weight=1, uniform="")
                    self.home_btn_row.grid_columnconfigure(1, weight=0, uniform="")
                    self.home_btn_row.grid_columnconfigure(2, weight=0, uniform="")
                    self.btn_hero_san.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 6))
                    self.btn_hero_res.grid(row=1, column=0, sticky="ew", padx=0, pady=(0, 6))
                    self.btn_hero_undo.grid(row=2, column=0, sticky="ew", padx=0, pady=0)

        # 2. Home Mid Row (Protection Modes + Local File: side-by-side vs stacked)
        if hasattr(self, "home_mid_row"):
            mid_mode = "side_by_side" if logical_w >= 860 else "stacked"
            if force or self._responsive_mode.get("home_mid") != mid_mode:
                self._responsive_mode["home_mid"] = mid_mode
                self.home_sw_card.grid_forget()
                self.home_file_card.grid_forget()
                if mid_mode == "side_by_side":
                    self.home_mid_row.grid_columnconfigure(0, weight=3)
                    self.home_mid_row.grid_columnconfigure(1, weight=2)
                    self.home_sw_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)
                    self.home_file_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)
                else:
                    self.home_mid_row.grid_columnconfigure(0, weight=1)
                    self.home_mid_row.grid_columnconfigure(1, weight=0)
                    self.home_sw_card.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 12))
                    self.home_file_card.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # 3. Sandbox Toolbar Row 1
        if hasattr(self, "sb_tb_row1"):
            sb_mode = "single" if logical_w >= 660 else "double"
            if force or self._responsive_mode.get("sb_tb") != sb_mode:
                self._responsive_mode["sb_tb"] = sb_mode
                for b in self._sb_toolbar_btns:
                    b.grid_forget()
                b_load, b_san, b_res, b_copy, b_clr = self._sb_toolbar_btns
                if sb_mode == "single":
                    self.sb_tb_row1.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="sbtb")
                    self.sb_tb_row1.grid_columnconfigure(4, weight=0, uniform="")
                    b_load.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=0)
                    b_san.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=0)
                    b_res.grid(row=0, column=2, sticky="ew", padx=(0, 6), pady=0)
                    b_copy.grid(row=0, column=3, sticky="ew", padx=(0, 6), pady=0)
                    b_clr.grid(row=0, column=4, sticky="ew", padx=0, pady=0)
                else:
                    self.sb_tb_row1.grid_columnconfigure((0, 1, 2), weight=1, uniform="sbtb")
                    self.sb_tb_row1.grid_columnconfigure((3, 4), weight=0, uniform="")
                    b_load.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
                    b_san.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(0, 6))
                    b_res.grid(row=0, column=2, sticky="ew", padx=0, pady=(0, 6))
                    b_copy.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 6), pady=0)
                    b_clr.grid(row=1, column=2, sticky="ew", padx=0, pady=0)

        # 4. Dictionary Words Tools Row + Rules Split + Presets
        if hasattr(self, "dict_tools_row"):
            dt_mode = "one_row" if logical_w >= 780 else "two_row"
            if force or self._responsive_mode.get("dict_tools") != dt_mode:
                self._responsive_mode["dict_tools"] = dt_mode
                for w in (
                    self._dict_lbl_filter, self.filter_cat_combo, self._dict_btn_clear,
                    self._dict_btn_json, self._dict_btn_imp, self._dict_btn_exp,
                ):
                    w.grid_forget()
                if dt_mode == "one_row":
                    self.dict_tools_row.grid_columnconfigure((0, 1), weight=0, uniform="")
                    self.dict_tools_row.grid_columnconfigure(2, weight=1, uniform="")
                    self.dict_tools_row.grid_columnconfigure((3, 4, 5), weight=0, uniform="")
                    self._dict_lbl_filter.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=0)
                    self.filter_cat_combo.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=0)
                    self._dict_btn_clear.grid(row=0, column=2, sticky="w", padx=(0, 8), pady=0)
                    self._dict_btn_json.grid(row=0, column=3, sticky="e", padx=(0, 6), pady=0)
                    self._dict_btn_imp.grid(row=0, column=4, sticky="e", padx=(0, 6), pady=0)
                    self._dict_btn_exp.grid(row=0, column=5, sticky="e", padx=0, pady=0)
                else:
                    self.dict_tools_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="")
                    self.dict_tools_row.grid_columnconfigure((3, 4, 5), weight=0, uniform="")
                    self._dict_lbl_filter.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=(0, 6))
                    self.filter_cat_combo.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(0, 6))
                    self._dict_btn_clear.grid(row=0, column=2, sticky="ew", padx=0, pady=(0, 6))
                    self._dict_btn_json.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=0)
                    self._dict_btn_imp.grid(row=1, column=1, sticky="ew", padx=(0, 6), pady=0)
                    self._dict_btn_exp.grid(row=1, column=2, sticky="ew", padx=0, pady=0)

        if hasattr(self, "dict_rules_pane"):
            dr_mode = "side_by_side" if logical_w >= 760 else "stacked"
            if force or self._responsive_mode.get("dict_rules") != dr_mode:
                self._responsive_mode["dict_rules"] = dr_mode
                self.dict_allow_card.grid_forget()
                self.dict_rules_card.grid_forget()
                if dr_mode == "side_by_side":
                    self.dict_rules_pane.grid_columnconfigure(0, weight=2)
                    self.dict_rules_pane.grid_columnconfigure(1, weight=3)
                    self.dict_rules_pane.grid_rowconfigure(0, weight=1)
                    self.dict_rules_pane.grid_rowconfigure(1, weight=0)
                    self.dict_allow_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=2)
                    self.dict_rules_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=2)
                else:
                    self.dict_rules_pane.grid_columnconfigure(0, weight=1)
                    self.dict_rules_pane.grid_columnconfigure(1, weight=0)
                    self.dict_rules_pane.grid_rowconfigure(0, weight=1)
                    self.dict_rules_pane.grid_rowconfigure(1, weight=2)
                    self.dict_allow_card.grid(row=0, column=0, sticky="nsew", padx=0, pady=(2, 6))
                    self.dict_rules_card.grid(row=1, column=0, sticky="nsew", padx=0, pady=(2, 2))

        if hasattr(self, "dict_preset_row"):
            rules_est_w = int(logical_w * 0.58) if logical_w >= 760 else logical_w
            pr_mode = "three" if rules_est_w >= 520 else "two_one"
            if force or self._responsive_mode.get("dict_preset") != pr_mode:
                self._responsive_mode["dict_preset"] = pr_mode
                for pb in self._preset_btns:
                    pb.grid_forget()
                p_dev, p_hr, p_str = self._preset_btns
                if pr_mode == "three":
                    self.dict_preset_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="preset")
                    p_dev.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=0)
                    p_hr.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=0)
                    p_str.grid(row=0, column=2, sticky="ew", padx=0, pady=0)
                else:
                    self.dict_preset_row.grid_columnconfigure((0, 1), weight=1, uniform="preset2")
                    self.dict_preset_row.grid_columnconfigure(2, weight=0, uniform="")
                    p_dev.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
                    p_hr.grid(row=0, column=1, sticky="ew", padx=0, pady=(0, 6))
                    p_str.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

        # 4b. Dict Regex Pane (narrow vs wide)
        if hasattr(self, "regex_form_grid"):
            rg_mode = "wide" if logical_w >= 760 else "compact"
            if force or self._responsive_mode.get("regex_form") != rg_mode:
                self._responsive_mode["regex_form"] = rg_mode
                for w in (
                    self._lbl_rg_name, self.entry_regex_name,
                    self._lbl_rg_cat, self.entry_regex_cat,
                    self._lbl_rg_tpl, self.combo_regex_tpl,
                ):
                    w.grid_forget()
                if rg_mode == "wide":
                    self.regex_form_grid.grid_columnconfigure((0, 2, 4), weight=0)
                    self.regex_form_grid.grid_columnconfigure((1, 3, 5), weight=1)
                    self._lbl_rg_name.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=2)
                    self.entry_regex_name.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=2)
                    self._lbl_rg_cat.grid(row=0, column=2, sticky="w", padx=(0, 6), pady=2)
                    self.entry_regex_cat.grid(row=0, column=3, sticky="ew", padx=(0, 10), pady=2)
                    self._lbl_rg_tpl.grid(row=0, column=4, sticky="w", padx=(0, 6), pady=2)
                    self.combo_regex_tpl.grid(row=0, column=5, sticky="ew", padx=0, pady=2)
                else:
                    self.regex_form_grid.grid_columnconfigure(0, weight=0)
                    self.regex_form_grid.grid_columnconfigure(1, weight=1)
                    self.regex_form_grid.grid_columnconfigure((2, 3, 4, 5), weight=0)
                    self._lbl_rg_name.grid(row=0, column=0, sticky="w", padx=(0, 6), pady=2)
                    self.entry_regex_name.grid(row=0, column=1, sticky="ew", padx=0, pady=2)
                    self._lbl_rg_cat.grid(row=1, column=0, sticky="w", padx=(0, 6), pady=2)
                    self.entry_regex_cat.grid(row=1, column=1, sticky="ew", padx=0, pady=2)
                    self._lbl_rg_tpl.grid(row=2, column=0, sticky="w", padx=(0, 6), pady=2)
                    self.combo_regex_tpl.grid(row=2, column=1, sticky="ew", padx=0, pady=2)

        # 4c. Home Drop Controls (2-col vs stacked inside narrow side-by-side home_file_card)
        if hasattr(self, "drop_ctrl_row"):
            dc_mode = "inline" if logical_w >= 960 or logical_w < 860 else "stacked"
            if force or self._responsive_mode.get("drop_ctrl") != dc_mode:
                self._responsive_mode["drop_ctrl"] = dc_mode
                self.drop_mode_seg.grid_forget()
                self.btn_batch_folder.grid_forget()
                if dc_mode == "inline":
                    self.drop_ctrl_row.grid_columnconfigure(0, weight=1)
                    self.drop_ctrl_row.grid_columnconfigure(1, weight=0)
                    self.drop_mode_seg.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=0)
                    self.btn_batch_folder.grid(row=0, column=1, sticky="ew", padx=0, pady=0)
                else:
                    self.drop_ctrl_row.grid_columnconfigure(0, weight=1)
                    self.drop_ctrl_row.grid_columnconfigure(1, weight=0)
                    self.drop_mode_seg.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 6))
                    self.btn_batch_folder.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        # 5. Vault Actions Row (4-col vs 2x2)
        if hasattr(self, "vault_actions_row"):
            va_mode = "four" if logical_w >= 540 else "two_by_two"
            if force or self._responsive_mode.get("vault_act") != va_mode:
                self._responsive_mode["vault_act"] = va_mode
                for vb in self._vault_action_btns:
                    vb.grid_forget()
                v_ref, v_exp, v_imp, v_clr = self._vault_action_btns
                if va_mode == "four":
                    self.vault_actions_row.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="vact")
                    v_ref.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=0)
                    v_exp.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=0)
                    v_imp.grid(row=0, column=2, sticky="ew", padx=(0, 6), pady=0)
                    v_clr.grid(row=0, column=3, sticky="ew", padx=0, pady=0)
                else:
                    self.vault_actions_row.grid_columnconfigure((0, 1), weight=1, uniform="vact2")
                    self.vault_actions_row.grid_columnconfigure((2, 3), weight=0, uniform="")
                    v_ref.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
                    v_exp.grid(row=0, column=1, sticky="ew", padx=0, pady=(0, 6))
                    v_imp.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=0)
                    v_clr.grid(row=1, column=1, sticky="ew", padx=0, pady=0)

        # 6. Dynamic Wraplengths + Bilingual Size Reservations
        self._update_responsive_wraps(logical_w)

    def _update_responsive_wraps(self, logical_w: int) -> None:
        alive: List[tuple] = []
        for widget, width_fn, variants_fn in self._responsive_wraps:
            try:
                if not widget.winfo_exists():
                    continue
            except Exception:
                continue
            alive.append((widget, width_fn, variants_fn))
            raw_wrap = max(140, int(width_fn(logical_w)))
            new_wrap = (raw_wrap // 8) * 8
            if getattr(widget, "_aps_last_wrap", None) == new_wrap:
                continue
            widget._aps_last_wrap = new_wrap
            widget.configure(wraplength=new_wrap)
            variants: Optional[List[str]] = None
            if variants_fn is not None:
                variants = variants_fn()
            elif widget in self._translation_bindings:
                t_key, t_opt, t_prefix = self._translation_bindings[widget]
                if t_opt == "text":
                    variants = [
                        t_prefix + self._format_hotkey_text(tr(lang, t_key))
                        for lang in ("zh", "en")
                    ]
            if variants:
                self._reserve_bilingual_text(widget, variants)
        self._responsive_wraps = alive

    def _ready_status_text(self) -> str:
        return self._format_hotkey_text(self._t("status_ready"))

    def _format_hotkey_text(self, text: str) -> str:
        hotkeys = self.sanitizer.hotkeys
        san_disp = hotkeys.get("sanitize", "alt+s").upper()
        res_disp = hotkeys.get("restore", "alt+r").upper()
        return re.sub(
            r"Alt\s*\+\s*([SR])\b",
            lambda match: san_disp if match.group(1).upper() == "S" else res_disp,
            text,
            flags=re.I,
        )

    def _guide_text(self) -> str:
        return self._format_hotkey_text(self._t("tutorial_body").strip())

    @staticmethod
    def _relabel_segments(bar, values, selected) -> None:
        """Translate fixed segments or sidebar buttons without creating unpainted native labels."""
        old_values = bar.cget("values")
        if len(old_values) != len(values) or len(set(values)) != len(values):
            raise ValueError("Translated segments must retain their unique positions")
        buttons = [bar._buttons_dict[value] for value in old_values]
        renamed = dict(zip(old_values, values))
        bar._value_list = list(values)
        bar._buttons_dict = dict(zip(values, buttons))
        bar._current_value = renamed.get(bar.get(), bar.get())
        for value, button in zip(values, buttons):
            button.configure(text=value, command=lambda value=value: bar.set(value, from_button_callback=True))
        bar.set(selected)

    def _refresh_translations(self, add_category: str, filter_category: str) -> None:
        for widget, (key, option, prefix) in list(self._translation_bindings.items()):
            if widget.winfo_exists():
                widget.configure(**{option: prefix + self._t(key)})
            else:
                del self._translation_bindings[widget]
        self.root.title(self._t("window_title"))
        self._nav_labels = [self._t("nav_" + key) for key in self._nav_keys]
        self._label_to_nav_key = dict(zip(self._nav_labels, self._nav_keys))
        self._nav_key_to_label = dict(zip(self._nav_keys, self._nav_labels))
        self._relabel_segments(self.nav_bar, self._nav_labels, self._nav_key_to_label[self._active_page_key])
        self._dict_mode_labels = [
            self._t("dict_mode_words"),
            self._t("dict_mode_rules"),
            self._t("dict_mode_regex"),
        ]
        dict_idx = {"words": 0, "rules": 1, "regex": 2}.get(self._dict_submode, 0)
        self._relabel_segments(
            self.dict_mode_seg,
            self._dict_mode_labels,
            self._dict_mode_labels[dict_idx],
        )
        if hasattr(self, "drop_mode_seg"):
            self._drop_mode_labels = [
                self._t("file_drop_mode_san"),
                self._t("file_drop_mode_res"),
            ]
            self._relabel_segments(
                self.drop_mode_seg,
                self._drop_mode_labels,
                self._drop_mode_labels[1 if self._drop_mode == "restore" else 0],
            )
        self.add_cat_combo.configure(values=[self._cat_label(key) for key in CATEGORY_KEYS])
        self.add_cat_combo.set(self._cat_label(add_category))
        self.filter_cat_combo.configure(values=[self._cat_label(key) for key in ["ALL"] + CATEGORY_KEYS])
        self.filter_cat_combo.set(self._cat_label(filter_category))
        if hasattr(self, "combo_idle_wipe"):
            self._refresh_idle_combo_labels()
        self.btn_theme.configure(
            text=self._t("btn_theme_light" if self.theme_mode == "dark" else "btn_theme_dark")
        )
        self._refresh_sidebar_status_label()
        self._refresh_hotkey_labels()
        if hasattr(self, "combo_hk_sanitize") and hasattr(self.combo_hk_sanitize, "set_listening_text"):
            self.combo_hk_sanitize.set_listening_text(self._t("hk_box_listening"))
        if hasattr(self, "combo_hk_restore") and hasattr(self.combo_hk_restore, "set_listening_text"):
            self.combo_hk_restore.set_listening_text(self._t("hk_box_listening"))
        if self._recording_target:
            target = self.btn_rec_san if self._recording_target == "sanitize" else self.btn_rec_res
            target.configure(text=self._t("btn_hk_recording"))
        if self._json_modal is not None and self._json_modal.winfo_exists():
            self._json_modal.title(self._t("json_modal_title"))
        if self._about_modal is not None and self._about_modal.winfo_exists():
            self._about_modal.title(self._t("about_title"))
            self._about_version_label.configure(text=self._t("about_version").format(version=__version__))
        self._refresh_hotkey_status_ui()
        self._refresh_recent_clipboard_card()
        if hasattr(self, "lbl_regex_test_result") and self.lbl_regex_test_result.winfo_exists():
            if self._active_page_key == "dict" and self._dict_submode == "regex":
                self._on_regex_live_test_changed()
        if self._active_page_key == "dict":
            if self._dict_submode == "rules":
                self.refresh_allowlist_and_rules_list()
            elif self._dict_submode == "regex":
                self.refresh_custom_regex_list()

    def _cat_label(self, cat_key: str) -> str:
        mapping = {
            "ALL": self._t("cat_all"),
            "COMPANY": self._t("cat_company"),
            "CLIENT": self._t("cat_client"),
            "PROJECT": self._t("cat_project"),
            "CUSTOM_SECRET": self._t("cat_secret"),
        }
        return mapping.get(cat_key, cat_key)

    def _label_to_cat(self, label: str) -> str:
        for k in ["ALL"] + CATEGORY_KEYS:
            if self._cat_label(k) == label:
                return k
        return "COMPANY"

    def _idle_label(self, minutes: int) -> str:
        if minutes <= 0:
            return self._t("idle_wipe_off")
        return self._t("idle_wipe_min").format(m=minutes)

    def _label_to_idle_minutes(self, label: str) -> int:
        for m in VALID_IDLE_WIPE_MINUTES:
            if self._idle_label(m) == label:
                return m
        match = re.search(r"(\d+)", str(label or ""))
        return int(match.group(1)) if match else 0

    def _refresh_idle_combo_labels(self) -> None:
        current_min = self.sanitizer.idle_wipe_minutes
        vals = [self._idle_label(m) for m in VALID_IDLE_WIPE_MINUTES]
        self.combo_idle_wipe.configure(values=vals)
        self.combo_idle_wipe.set(self._idle_label(current_min))

    def _snapshot_ui_state(self) -> None:
        """Preserve all user-typed textboxes, entries, and dropdown selections before rebuilding layout."""
        for attr in ("_sandbox_debounce_id", "_vault_search_debounce_id", "_rule_search_debounce_id"):
            timer = getattr(self, attr, None)
            if timer is not None:
                try:
                    self.root.after_cancel(timer)
                except Exception:
                    pass
                setattr(self, attr, None)

        if self._recording_target is not None:
            self._recording_target = None
            for seq in ("<KeyPress>", "<KeyRelease>"):
                try:
                    self.root.unbind(seq)
                except Exception:
                    pass

        for attr, widget_attr, is_text in (
            ("_saved_sandbox_input", "sandbox_input", True),
            ("_saved_sandbox_output", "sandbox_output", True),
            ("_saved_entry_new_word", "entry_new_word", False),
            ("_saved_entry_allowlist", "entry_allowlist", False),
            ("_saved_hk_sanitize", "combo_hk_sanitize", False),
            ("_saved_hk_restore", "combo_hk_restore", False),
        ):
            if hasattr(self, widget_attr):
                try:
                    w = getattr(self, widget_attr)
                    setattr(self, attr, w.get("1.0", "end-1c") if is_text else w.get())
                except Exception:
                    pass
        if hasattr(self, "add_cat_combo"):
            try:
                self._saved_add_cat_key = self._label_to_cat(self.add_cat_combo.get())
            except Exception:
                pass
        if hasattr(self, "filter_cat_combo"):
            try:
                self._saved_filter_cat_key = self._label_to_cat(self.filter_cat_combo.get())
            except Exception:
                pass
        if hasattr(self, "vault_search_var"):
            try:
                self._saved_vault_search = self.vault_search_var.get()
            except Exception:
                pass
        if hasattr(self, "rule_search_var"):
            try:
                self._saved_rule_search = self.rule_search_var.get()
            except Exception:
                pass
        for s_attr, w_attr in (
            ("_saved_regex_name", "entry_regex_name"),
            ("_saved_regex_cat", "entry_regex_cat"),
            ("_saved_regex_tpl", "combo_regex_tpl"),
            ("_saved_regex_pattern", "entry_regex_pattern"),
            ("_saved_regex_test", "entry_regex_test"),
        ):
            if hasattr(self, w_attr):
                try:
                    setattr(self, s_attr, getattr(self, w_attr).get())
                except Exception:
                    pass

    def _attach_text_context_menu(
        self,
        widget: object,
        is_textbox: bool = True,
        *,
        allow_placeholder_allowlist: bool = False,
    ) -> None:
        """Attach cross-platform right-click Cut/Copy/Paste/Select All (+ Allowlist on sandbox output)."""
        inner = getattr(widget, "_textbox", None) if is_textbox else getattr(widget, "_entry", None)
        if inner is None:
            return
        menu = tk.Menu(inner, tearoff=0)
        menu.add_command(label="Cut", command=lambda: inner.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: inner.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: inner.event_generate("<<Paste>>"))
        menu.add_separator()
        if is_textbox:
            menu.add_command(label="Select All", command=lambda: inner.tag_add("sel", "1.0", "end"))
        else:
            menu.add_command(label="Select All", command=lambda: inner.select_range(0, "end"))

        allow_state: Dict[str, Optional[str]] = {"original": None}
        if allow_placeholder_allowlist:
            menu.add_separator()
            menu.add_command(
                label=self._t("ctx_allowlist_placeholder"),
                command=lambda: self._allowlist_from_sandbox_tag(allow_state["original"]),
            )

        def _popup(event) -> None:
            try:
                labels = (
                    ["✂️ 剪切 (Cut)", "📋 复制 (Copy)", "📥 粘贴 (Paste)", "🔠 全选 (Select All)"]
                    if self.lang == "zh"
                    else ["✂️ Cut", "📋 Copy", "📥 Paste", "🔠 Select All"]
                )
                for index, label in zip((0, 1, 2, 4), labels):
                    menu.entryconfigure(index, label=label)
                if allow_placeholder_allowlist:
                    clicked_orig = self._find_placeholder_original_at_event(inner, event)
                    allow_state["original"] = clicked_orig
                    menu.entryconfigure(
                        6,
                        label=self._t("ctx_allowlist_placeholder"),
                        state="normal" if clicked_orig else "disabled",
                    )
                inner.focus_set()
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        inner.bind("<Button-3>", _popup)
        if platform.system() == "Darwin":
            inner.bind("<Button-2>", _popup)
            inner.bind("<Control-Button-1>", _popup)

    def _active_sandbox_vault(self) -> SessionVault:
        if getattr(self, "_sandbox_isolate", False) and getattr(self, "_sandbox_vault", None) is not None:
            return self._sandbox_vault
        return self.sanitizer.vault

    def _find_placeholder_original_at_event(self, inner_text: tk.Text, event) -> Optional[str]:
        """Resolve original value if user right-clicked on a highlighted placeholder in sandbox output."""
        try:
            click_idx = inner_text.index(f"@{event.x},{event.y}")
            line_no, col_no = map(int, click_idx.split("."))
            line_text = inner_text.get(f"{line_no}.0", f"{line_no}.end")
        except Exception:
            return None
        vault = self._active_sandbox_vault()
        for ph, orig, _cat in vault.snapshot_placeholders():
            start = 0
            while True:
                pos = line_text.find(ph, start)
                if pos == -1:
                    break
                if pos <= col_no <= pos + len(ph):
                    return orig
                start = pos + len(ph)
        return None

    def _allowlist_from_sandbox_tag(self, original_value: Optional[str]) -> None:
        if not original_value:
            return
        if self.sanitizer.add_allowlist_item(original_value):
            self._run_sandbox_sanitize()
            self.status_var.set(self._t("msg_allowlist_added"))

    def _cancel_layout_timers(self, container) -> None:
        """Cancel only callbacks owned by this widget subtree."""
        if isinstance(container, tk.Misc):
            commands = set()
            pending = [container]
            while pending:
                widget = pending.pop()
                commands.update(getattr(widget, "_tclCommands", None) or ())
                pending.extend(widget.winfo_children())
            for timer in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                script, _kind = self.root.tk.call("after", "info", timer)
                parts = self.root.tk.splitlist(script)
                if parts and str(parts[0]) in commands:
                    self.root.tk.call("after", "cancel", timer)

    def _discard_layout(self, container) -> None:
        self._cancel_layout_timers(container)
        container.destroy()

    def _ensure_drop_target_attached(self) -> None:
        """Attach native Win32 Explorer file/folder drag-and-drop once the top HWND exists."""
        if platform.system() != "Windows" or self._drop_target is not None:
            return
        try:
            self.root.update_idletasks()
            drop_target = WindowsFileDropTarget(self.root, self.handle_dropped_paths)
            if drop_target.attach():
                self._drop_target = drop_target
        except Exception:
            pass

    def detach_drop_target(self) -> None:
        """Detach native Win32 drag-and-drop hook if attached."""
        target = getattr(self, "_drop_target", None)
        if target is not None:
            try:
                target.detach()
            except Exception:
                pass
            self._drop_target = None

    def _build_layout(self, on_ready: Optional[Callable[[], None]] = None) -> None:
        """Lay out the replacement behind the mapped old page, then raise it."""
        previous = self.__dict__.copy()
        old_container = self._main_container
        try:
            self._construct_layout()
            self._main_container.grid(row=0, column=0, sticky="nsew")
            if old_container is not None:
                self._main_container.lower(old_container)
            self.root.update_idletasks()
            if on_ready is not None:
                on_ready()
            self._main_container.lift()
        except Exception:
            if self._main_container is not None and self._main_container is not old_container:
                self._discard_layout(self._main_container)
            self.__dict__.clear()
            self.__dict__.update(previous)
            raise
        if old_container is not None:
            self._discard_layout(old_container)

    def _construct_layout(self) -> None:
        self._responsive_wraps = []
        self._responsive_mode = {}
        self._last_layout_logical_w = 0
        if getattr(self, "_sandbox_debounce_id", None) is not None:
            try:
                self.root.after_cancel(self._sandbox_debounce_id)
            except Exception:
                pass
            self._sandbox_debounce_id = None
        if self._recording_target is not None:
            self._recording_target = None
            for seq in ("<KeyPress>", "<KeyRelease>"):
                try:
                    self.root.unbind(seq)
                except Exception:
                    pass

        self.root.title(self._t("window_title"))
        self.status_var = tk.StringVar(value=self._ready_status_text())
        self._main_container = ctk.CTkFrame(
            self.root,
            fg_color=("#f1f5f9", "#0b0f19"),
            corner_radius=0,
        )

        # Shared BooleanVars (kept synchronized across sidebar, home, and settings)
        self.var_auto_sanitize = tk.BooleanVar(value=self.sanitizer.auto_sanitize_clipboard)
        self.var_semantic_ip = tk.BooleanVar(value=self.sanitizer.semantic_ip_mode)
        self.var_ai_hint = tk.BooleanVar(value=self.sanitizer.ai_prompt_hint)
        self.var_whole_word = tk.BooleanVar(value=self.sanitizer.custom_word_whole_word)
        self.var_hud_enabled = tk.BooleanVar(value=self.sanitizer.hud_enabled)
        self.var_clip_guard = tk.BooleanVar(value=self.sanitizer.clipboard_privacy_guard)
        self.var_entropy = tk.BooleanVar(value=self.sanitizer.entropy_detection_enabled)
        self.var_startup = tk.BooleanVar(value=is_startup_enabled())

        # --- Body Shell: Left Sidebar + Right Workspace ---
        body = ctk.CTkFrame(self._main_container, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # --- 1. Left Fixed Sidebar (224px) ---
        sidebar = ctk.CTkFrame(
            body,
            width=224,
            fg_color=("#ffffff", "#111827"),
            corner_radius=0,
            border_width=0,
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        side_inner = ctk.CTkFrame(sidebar, fg_color="transparent")
        side_inner.pack(fill="both", expand=True, padx=12, pady=14)

        # Brand Header (strictly short APP_NAME without version)
        brand_row = ctk.CTkFrame(side_inner, fg_color="transparent")
        brand_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            brand_row,
            text=self._t("brand_title"),
            font=self.font_title,
            text_color=("#0f172a", "#f8fafc"),
            anchor="w",
        ).pack(side="left")

        self._localized_widget(
            ctk.CTkButton,
            brand_row,
            translation_key="btn_about",
            font=self.font_small,
            width=54,
            height=26,
            corner_radius=7,
            fg_color=("#e2e8f0", "#1e293b"),
            hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._show_about,
        ).pack(side="right")

        # Live Protection Status Mini-Card in Sidebar
        status_card = ctk.CTkFrame(
            side_inner,
            fg_color=("#f8fafc", "#1e293b"),
            corner_radius=10,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        status_card.pack(fill="x", pady=(0, 12))

        self.lbl_side_status = ctk.CTkLabel(
            status_card,
            text="",
            font=self.font_small,
            text_color=("#059669", "#34d399"),
            anchor="w",
        )
        self._reserve_bilingual_text(
            self.lbl_side_status,
            [
                tr(lang, key)
                for lang in ("zh", "en")
                for key in ("sidebar_status_ready", "sidebar_status_cruise")
            ],
        )
        self.lbl_side_status.pack(fill="x", padx=10, pady=(8, 4))

        side_cruise_row = ctk.CTkFrame(status_card, fg_color="transparent")
        side_cruise_row.pack(fill="x", padx=10, pady=(0, 8))
        self._localized_widget(
            ctk.CTkLabel,
            side_cruise_row,
            translation_key="sidebar_cruise_short",
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(side="left")
        ctk.CTkSwitch(
            side_cruise_row,
            text="",
            variable=self.var_auto_sanitize,
            onvalue=True,
            offvalue=False,
            progress_color=("#059669", "#10b981"),
            command=self._on_toggle_auto_sanitize,
            width=40,
        ).pack(side="right")

        self.side_hk_row = ctk.CTkFrame(status_card, fg_color="transparent")
        self.side_hk_row.pack(fill="x", padx=10, pady=(0, 8))
        self.lbl_side_hk_status = ctk.CTkLabel(
            self.side_hk_row,
            text="",
            font=self.font_small,
            text_color=("#059669", "#34d399"),
            anchor="w",
        )
        self._reserve_bilingual_text(
            self.lbl_side_hk_status,
            [
                tr("zh", "hk_status_side_ready"),
                tr("en", "hk_status_side_ready"),
                tr("zh", "hk_status_side_conflict").format(key="ALT+R"),
                tr("en", "hk_status_side_conflict").format(key="ALT+R"),
            ],
        )
        self.lbl_side_hk_status.pack(side="left", fill="x", expand=True)

        self.btn_side_hk_fix = self._localized_widget(
            ctk.CTkButton,
            self.side_hk_row,
            translation_key="btn_hk_autofix_short",
            font=self.font_small,
            width=66,
            height=22,
            corner_radius=6,
            fg_color=("#d97706", "#b45309"),
            hover_color=("#b45309", "#92400e"),
            text_color="#ffffff",
            command=self._auto_fix_hotkeys_from_gui,
        )

        # Sidebar Navigation Buttons
        self._nav_keys = ["home", "sandbox", "dict", "vault", "settings", "guide"]
        self._nav_labels = [self._t("nav_" + k) for k in self._nav_keys]
        self._label_to_nav_key = dict(zip(self._nav_labels, self._nav_keys))
        self._nav_key_to_label = dict(zip(self._nav_keys, self._nav_labels))

        self.nav_bar = _SidebarNav(
            side_inner,
            values=self._nav_labels,
            font=self.font_h3,
            command=self._on_nav_selected,
        )
        for key, label in zip(self._nav_keys, self._nav_labels):
            self._reserve_bilingual_text(
                self.nav_bar._buttons_dict[label],
                [tr(lang, "nav_" + key) for lang in ("zh", "en")],
            )
        self.nav_bar.pack(fill="x", pady=(0, 8))

        # Sidebar Footer Controls (Idle Readout, Theme, Lang)
        side_footer = ctk.CTkFrame(side_inner, fg_color="transparent")
        side_footer.pack(side="bottom", fill="x")

        idle_box = ctk.CTkFrame(
            side_footer,
            fg_color=("#f8fafc", "#1e293b"),
            corner_radius=8,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        idle_box.pack(fill="x", pady=(0, 8))
        self._localized_widget(
            ctk.CTkLabel,
            idle_box,
            translation_key="sidebar_idle_label",
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(side="left", padx=(8, 4), pady=5)
        self.lbl_idle_readout = ctk.CTkLabel(
            idle_box,
            text="--:--",
            font=self.font_mono_sm,
            text_color=("#059669", "#34d399"),
            anchor="e",
        )
        self.lbl_idle_readout.pack(side="right", padx=(4, 8), pady=5)

        pref_row = ctk.CTkFrame(side_footer, fg_color="transparent")
        pref_row.pack(fill="x", pady=(0, 6))
        pref_row.grid_columnconfigure((0, 1), weight=1)

        theme_btn_text = (
            self._t("btn_theme_light") if self.theme_mode == "dark" else self._t("btn_theme_dark")
        )
        self.btn_theme = _PreferenceButton(
            pref_row,
            text=theme_btn_text,
            font=self.font_small,
            height=32,
            corner_radius=8,
            fg_color=("#e2e8f0", "#1e293b"),
            hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._toggle_theme,
        )
        self._reserve_bilingual_text(
            self.btn_theme,
            [
                tr(lang, key)
                for lang in ("zh", "en")
                for key in ("btn_theme_light", "btn_theme_dark")
            ],
        )
        self.btn_theme.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self.btn_lang = self._localized_widget(
            _PreferenceButton,
            pref_row,
            translation_key="btn_lang",
            font=self.font_small,
            height=32,
            corner_radius=8,
            fg_color=("#e2e8f0", "#1e293b"),
            hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._toggle_language,
        )
        self.btn_lang.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        # --- 2. Right Content Area ---
        right_shell = ctk.CTkFrame(body, fg_color="transparent")
        right_shell.grid(row=0, column=1, sticky="nsew")

        self.page_container = ctk.CTkFrame(right_shell, fg_color="transparent")
        self.page_container.pack(fill="both", expand=True, padx=18, pady=(14, 6))
        self.page_container.bind("<Configure>", self._on_page_container_configure)

        self.pages: Dict[str, ctk.CTkFrame] = {}
        self._build_page_home()
        self._build_page_sandbox()
        self._build_page_dict()
        self._build_page_vault()
        self._build_page_settings()
        self._build_page_guide()

        # --- 3. Bottom Compact Status Bar (pack right buttons first so status text never crowds them) ---
        footer = ctk.CTkFrame(
            self._main_container,
            fg_color=("#ffffff", "#111827"),
            corner_radius=0,
            height=42,
        )
        footer.pack(fill="x", side="bottom")

        self._localized_widget(
            ctk.CTkButton,
            footer,
            translation_key="btn_exit_app",
            font=self.font_small,
            width=102,
            height=28,
            corner_radius=7,
            fg_color=("#dc2626", "#991b1b"),
            hover_color=("#b91c1c", "#7f1d1d"),
            text_color="#ffffff",
            command=self._trigger_exit_app,
        ).pack(side="right", padx=(6, 16), pady=6)

        self._localized_widget(
            ctk.CTkButton,
            footer,
            translation_key="btn_hide_tray",
            font=self.font_small,
            width=102,
            height=28,
            corner_radius=7,
            fg_color=("#e2e8f0", "#1e293b"),
            hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self.hide,
        ).pack(side="right", padx=(0, 4), pady=6)

        ctk.CTkLabel(
            footer,
            textvariable=self.status_var,
            font=self.font_small,
            text_color=("#0284c7", "#38bdf8"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=16, pady=6)

        self._refresh_sidebar_status_label()
        self._refresh_hotkey_status_ui()
        self._refresh_recent_clipboard_card()
        self._update_idle_readout()
        init_page_w = max(580, getattr(self, "_initial_logical_width", 980) - 224 - 36)
        self._apply_responsive_layout(init_page_w, force=True)
        target_label = self._nav_key_to_label.get(self._active_page_key, self._nav_labels[0])
        self.nav_bar.set(target_label)
        self._show_page(self._active_page_key)
        if platform.system() == "Windows" and self._drop_target is None:
            self.root.after(150, self._ensure_drop_target_attached)

    def _refresh_sidebar_status_label(self) -> None:
        if not hasattr(self, "lbl_side_status"):
            return
        if self.sanitizer.auto_sanitize_clipboard:
            self.lbl_side_status.configure(
                text=self._t("sidebar_status_cruise"),
                text_color=("#059669", "#34d399"),
            )
        else:
            self.lbl_side_status.configure(
                text=self._t("sidebar_status_ready"),
                text_color=("#2563eb", "#60a5fa"),
            )

    def _update_idle_readout(self) -> None:
        if not hasattr(self, "lbl_idle_readout"):
            return
        try:
            if not self.lbl_idle_readout.winfo_exists():
                return
            if self.get_idle_seconds_left is not None:
                rem = self.get_idle_seconds_left()
            else:
                mins = self.sanitizer.idle_wipe_minutes
                rem = mins * 60 if mins > 0 and self.sanitizer.vault.size > 0 else None
            if rem is None:
                txt = self._t("sidebar_idle_off") if self.sanitizer.idle_wipe_minutes == 0 else "--:--"
            else:
                txt = f"{rem // 60:02d}:{rem % 60:02d}"
            self.lbl_idle_readout.configure(text=txt)
        except Exception:
            pass

    # ---------------- Page 1: Home Dashboard (Clean, Uncrowded) ----------------

    def _build_page_home(self) -> None:
        page = ctk.CTkScrollableFrame(self.page_container, fg_color="transparent")
        self.pages["home"] = page

        # Hero Card
        hero = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#131c31"),
            corner_radius=14,
            border_width=1,
            border_color=("#10b981", "#059669"),
        )
        hero.pack(fill="x", pady=(0, 12))

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                hero,
                translation_key="hero_badge",
                font=self.font_h2,
                text_color=("#059669", "#34d399"),
                justify="left",
            ),
            lambda w: w - 56,
        ).pack(anchor="w", fill="x", padx=18, pady=(14, 4))

        self.home_hk_status_row = ctk.CTkFrame(hero, fg_color="transparent")
        self.home_hk_status_row.pack(fill="x", padx=18, pady=(0, 6))
        self.lbl_home_hk_status = ctk.CTkLabel(
            self.home_hk_status_row,
            text="",
            font=self.font_small,
            text_color=("#059669", "#34d399"),
            anchor="w",
            justify="left",
        )
        self._register_wrap_label(
            self.lbl_home_hk_status,
            lambda w: w - 210,
        )
        self.lbl_home_hk_status.pack(side="left", fill="x", expand=True)
        self.btn_home_hk_fix = self._localized_widget(
            ctk.CTkButton,
            self.home_hk_status_row,
            translation_key="btn_hk_autofix",
            font=self.font_small,
            width=142,
            height=26,
            corner_radius=7,
            fg_color=("#d97706", "#b45309"),
            hover_color=("#b45309", "#92400e"),
            text_color="#ffffff",
            command=self._auto_fix_hotkeys_from_gui,
        )

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                hero,
                translation_key="hero_desc",
                font=self.font_body,
                text_color=("#334155", "#cbd5e1"),
                justify="left",
            ),
            lambda w: w - 56,
        ).pack(anchor="w", fill="x", padx=18, pady=(0, 12))

        self.home_btn_row = ctk.CTkFrame(hero, fg_color="transparent")
        self.home_btn_row.pack(fill="x", padx=18, pady=(0, 14))

        self.btn_hero_san = ctk.CTkButton(
            self.home_btn_row,
            text=self._format_hotkey_text(self._t("btn_hero_sanitize")),
            font=self.font_h3,
            width=10,
            height=42,
            corner_radius=10,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            text_color="#ffffff",
            command=self._trigger_sanitize_clipboard,
        )

        self.btn_hero_res = ctk.CTkButton(
            self.home_btn_row,
            text=self._format_hotkey_text(self._t("btn_hero_restore")),
            font=self.font_h3,
            width=10,
            height=42,
            corner_radius=10,
            fg_color=("#2563eb", "#2563eb"),
            hover_color=("#1d4ed8", "#1d4ed8"),
            text_color="#ffffff",
            command=self._trigger_restore_clipboard,
        )

        self.btn_hero_undo = self._localized_widget(
            ctk.CTkButton,
            self.home_btn_row,
            translation_key="btn_hero_undo",
            font=self.font_h3,
            width=10,
            height=42,
            corner_radius=10,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            text_color="#ffffff",
            command=self._trigger_undo_sanitize,
        )

        # 3 Dynamic KPI Cards (self-explanatory & clickable)
        stats_row = ctk.CTkFrame(page, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 12))
        stats_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="kpi")

        self._stat_cards: Dict[str, ctk.CTkFrame] = {}
        self.lbl_stat_hits = self._create_stat_card(
            stats_row,
            col=0,
            title="stat_intercepted_title",
            value=str(self.sanitizer.vault.total_intercepted_hits),
            unit="stat_intercepted_unit",
            accent=("#059669", "#34d399"),
            hint="stat_intercepted_hint",
            on_click=lambda: self._navigate_to_page("vault"),
            card_key="hits",
        )
        self.lbl_stat_vault = self._create_stat_card(
            stats_row,
            col=1,
            title="stat_vault_title",
            value=str(self.sanitizer.vault.size),
            unit="stat_vault_unit",
            accent=("#2563eb", "#60a5fa"),
            hint="stat_vault_hint",
            on_click=lambda: self._navigate_to_page("vault"),
            card_key="vault",
        )
        active_r, total_r = self.sanitizer.active_rule_counts()
        self.lbl_stat_rules = self._create_stat_card(
            stats_row,
            col=2,
            title="stat_rules_title",
            value=f"{active_r}/{total_r}",
            unit="stat_rules_unit",
            accent=("#7c3aed", "#a78bfa"),
            hint="stat_rules_hint",
            on_click=self._open_rules_list_page,
            card_key="rules",
        )

        # Dual Row: Quick Modes Card + Local File Sanitize/Restore Card
        self.home_mid_row = ctk.CTkFrame(page, fg_color="transparent")
        self.home_mid_row.pack(fill="x", pady=(0, 12))

        self.home_sw_card = ctk.CTkFrame(
            self.home_mid_row,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=14,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )

        self._localized_widget(
            ctk.CTkLabel,
            self.home_sw_card,
            translation_key="switches_section_title",
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w", padx=16, pady=(12, 4))

        home_sw_wrap = lambda w: (int(w * 0.56) - 108) if w >= 860 else (w - 108)
        self._create_switch_row(
            self.home_sw_card,
            title="sw_semantic_title",
            desc="sw_semantic_desc",
            variable=self.var_semantic_ip,
            command=self._on_toggle_semantic_ip,
            wrap_fn=home_sw_wrap,
        )
        self._create_switch_row(
            self.home_sw_card,
            title="sw_ai_hint_title",
            desc="sw_ai_hint_desc",
            variable=self.var_ai_hint,
            command=self._on_toggle_ai_hint,
            wrap_fn=home_sw_wrap,
        )

        # File Sanitize / Restore Card (v0.5.0)
        self.home_file_card = ctk.CTkFrame(
            self.home_mid_row,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=14,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )

        file_wrap = lambda w: (int(w * 0.38) - 48) if w >= 860 else (w - 52)
        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                self.home_file_card,
                translation_key="file_drop_title",
                font=self.font_h3,
                text_color=("#0f172a", "#f8fafc"),
                justify="left",
            ),
            file_wrap,
        ).pack(anchor="w", fill="x", padx=16, pady=(12, 4))

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                self.home_file_card,
                translation_key="file_drop_desc",
                font=self.font_small,
                text_color=("#64748b", "#94a3b8"),
                wraplength=260,
                justify="left",
            ),
            file_wrap,
        ).pack(anchor="w", fill="x", padx=16, pady=(0, 12))

        file_btns = ctk.CTkFrame(self.home_file_card, fg_color="transparent")
        file_btns.pack(fill="x", padx=16, pady=(0, 8))
        file_btns.grid_columnconfigure((0, 1), weight=1, uniform="fbtn")

        self._localized_widget(
            ctk.CTkButton,
            file_btns,
            translation_key="btn_sanitize_file",
            font=self.font_small,
            width=10,
            height=34,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            text_color="#ffffff",
            command=self._sanitize_local_file_dialog,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._localized_widget(
            ctk.CTkButton,
            file_btns,
            translation_key="btn_restore_file",
            font=self.font_small,
            width=10,
            height=34,
            corner_radius=8,
            fg_color=("#2563eb", "#2563eb"),
            hover_color=("#1d4ed8", "#1d4ed8"),
            text_color="#ffffff",
            command=self._restore_local_file_dialog,
        ).grid(row=0, column=1, sticky="ew", padx=0)

        self.home_drop_zone = ctk.CTkFrame(
            self.home_file_card,
            fg_color=("#f8fafc", "#0f172a"),
            corner_radius=10,
            border_width=1,
            border_color=("#cbd5e1", "#334155"),
        )
        self.home_drop_zone.pack(fill="x", padx=16, pady=(0, 12))

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                self.home_drop_zone,
                translation_key="file_drop_zone_hint",
                font=self.font_small,
                text_color=("#475569", "#94a3b8"),
                justify="left",
            ),
            lambda w: (int(w * 0.38) - 64) if w >= 860 else (w - 72),
        ).pack(anchor="w", fill="x", padx=10, pady=(8, 6))

        self.drop_ctrl_row = ctk.CTkFrame(self.home_drop_zone, fg_color="transparent")
        self.drop_ctrl_row.pack(fill="x", padx=10, pady=(0, 8))

        self._drop_mode_labels = [
            self._t("file_drop_mode_san"),
            self._t("file_drop_mode_res"),
        ]
        self.drop_mode_seg = ctk.CTkSegmentedButton(
            self.drop_ctrl_row,
            values=self._drop_mode_labels,
            font=self.font_small,
            height=28,
            corner_radius=7,
            selected_color=("#059669", "#059669"),
            selected_hover_color=("#047857", "#047857"),
            command=self._on_drop_mode_selected,
        )
        self.drop_mode_seg.set(
            self._drop_mode_labels[1 if self._drop_mode == "restore" else 0]
        )

        self.btn_batch_folder = self._localized_widget(
            ctk.CTkButton,
            self.drop_ctrl_row,
            translation_key="btn_batch_folder",
            font=self.font_small,
            width=108,
            height=28,
            corner_radius=7,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            text_color="#ffffff",
            command=self._batch_folder_dialog,
        )

        self.lbl_batch_result = ctk.CTkLabel(
            self.home_drop_zone,
            text=self._saved_batch_status,
            font=self.font_small,
            text_color=("#059669", "#34d399"),
            anchor="w",
            justify="left",
        )
        self._register_wrap_label(
            self.lbl_batch_result,
            lambda w: (int(w * 0.38) - 64) if w >= 860 else (w - 72),
        )
        self.btn_open_batch_out = self._localized_widget(
            ctk.CTkButton,
            self.home_drop_zone,
            translation_key="btn_open_batch_out",
            font=self.font_small,
            width=136,
            height=24,
            corner_radius=6,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._open_batch_output_dir,
        )
        if self._saved_batch_status:
            self.lbl_batch_result.pack(anchor="w", fill="x", padx=10, pady=(0, 4))
            if self._last_batch_output_path is not None:
                self.btn_open_batch_out.pack(anchor="w", padx=10, pady=(0, 6))

        # Recent Clipboard Sanitize Diff Quick-View Card (v0.6.0)
        self.home_recent_card = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=14,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        self.home_recent_card.pack(fill="x", pady=(0, 12))

        recent_hdr = ctk.CTkFrame(self.home_recent_card, fg_color="transparent")
        recent_hdr.pack(fill="x", padx=16, pady=(12, 4))

        self.var_recent_reveal = tk.BooleanVar(value=self._recent_reveal_originals)
        self._localized_widget(
            ctk.CTkSwitch,
            recent_hdr,
            translation_key="recent_clip_reveal",
            font=self.font_small,
            variable=self.var_recent_reveal,
            onvalue=True,
            offvalue=False,
            progress_color=("#059669", "#10b981"),
            command=self._on_toggle_recent_reveal,
        ).pack(side="right", padx=(8, 0))

        self._localized_widget(
            ctk.CTkLabel,
            recent_hdr,
            translation_key="recent_clip_title",
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(side="left")

        self.lbl_recent_meta = ctk.CTkLabel(
            recent_hdr,
            text="",
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
            anchor="w",
        )
        self.lbl_recent_meta.pack(side="left", padx=(10, 0))

        self.home_recent_body = ctk.CTkFrame(self.home_recent_card, fg_color="transparent")
        self.home_recent_body.pack(fill="x", padx=16, pady=(2, 12))

        self.lbl_recent_empty = self._register_wrap_label(
            ctk.CTkLabel(
                self.home_recent_body,
                text=self._format_hotkey_text(self._t("recent_clip_empty")),
                font=self.font_small,
                text_color=("#64748b", "#94a3b8"),
                anchor="w",
                justify="left",
            ),
            lambda w: w - 60,
        )
        self.lbl_recent_empty.pack(anchor="w", fill="x")

        self.home_recent_items = ctk.CTkFrame(self.home_recent_body, fg_color="transparent")

        # Workflow Banner
        wf_card = ctk.CTkFrame(
            page,
            fg_color=("#e0f2fe", "#0f172a"),
            corner_radius=12,
            border_width=1,
            border_color=("#bae6fd", "#1e3a8a"),
        )
        wf_card.pack(fill="x", pady=(0, 6))

        wf_text = self._format_hotkey_text(
            f"{self._t('workflow_title')}：{self._t('workflow_steps')}"
        )
        self.lbl_workflow = ctk.CTkLabel(
            wf_card,
            text=wf_text,
            font=self.font_body,
            text_color=("#0369a1", "#7dd3fc"),
            anchor="w",
            justify="left",
        )
        self._register_wrap_label(
            self.lbl_workflow,
            lambda w: w - 56,
            variants_fn=lambda: [
                self._format_hotkey_text(f"{tr(lang, 'workflow_title')}：{tr(lang, 'workflow_steps')}")
                for lang in ("zh", "en")
            ],
        )
        self.lbl_workflow.pack(fill="x", padx=16, pady=10)

    def _create_stat_card(
        self,
        parent: ctk.CTkFrame,
        col: int,
        title: str,
        value: str,
        unit: str,
        accent: tuple,
        *,
        hint: Optional[str] = None,
        on_click: Optional[Callable[[], None]] = None,
        card_key: Optional[str] = None,
    ) -> ctk.CTkLabel:
        padx = (0, 6) if col == 0 else ((6, 6) if col == 1 else (6, 0))
        card = ctk.CTkFrame(
            parent,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        card.grid(row=0, column=col, sticky="ew", padx=padx)
        if card_key and hasattr(self, "_stat_cards"):
            self._stat_cards[card_key] = card

        lbl_title = self._localized_widget(
            ctk.CTkLabel,
            card,
            translation_key=title,
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        )
        lbl_title.pack(anchor="w", padx=14, pady=(10, 2))

        val_row = ctk.CTkFrame(card, fg_color="transparent")
        val_row.pack(anchor="w", padx=14, pady=(0, 2 if hint else 10))

        num_lbl = ctk.CTkLabel(val_row, text=value, font=self.font_stat_num, text_color=accent)
        num_lbl.pack(side="left")

        lbl_unit = self._localized_widget(
            ctk.CTkLabel,
            val_row,
            translation_key=unit,
            translation_prefix="  ",
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        )
        lbl_unit.pack(side="left", pady=(6, 0))

        hint_lbl = None
        if hint:
            hint_lbl = self._localized_widget(
                ctk.CTkLabel,
                card,
                translation_key=hint,
                font=self.font_small,
                text_color=("#64748b", "#94a3b8"),
            )
            hint_lbl.pack(anchor="w", padx=14, pady=(0, 8))

        if on_click is not None:
            def _bind_click(widget) -> None:
                try:
                    widget.configure(cursor="hand2")
                except Exception:
                    pass
                widget.bind("<Button-1>", lambda _e: on_click())
                inner = getattr(widget, "_label", None)
                if inner is not None:
                    try:
                        inner.configure(cursor="hand2")
                    except Exception:
                        pass
                    inner.bind("<Button-1>", lambda _e: on_click())

            for target_w in (card, lbl_title, val_row, num_lbl, lbl_unit, hint_lbl):
                if target_w is not None:
                    _bind_click(target_w)

        return num_lbl

    def _create_switch_row(
        self,
        parent: ctk.CTkFrame,
        title: str,
        desc: str,
        variable: tk.BooleanVar,
        command: Callable[[], None],
        *,
        wrap_fn: Optional[Callable[[int], int]] = None,
    ) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=6)

        # Pack switch on the right FIRST so long descriptions can never push it off-screen.
        ctk.CTkSwitch(
            row,
            text="",
            variable=variable,
            onvalue=True,
            offvalue=False,
            progress_color=("#059669", "#10b981"),
            command=command,
            width=46,
        ).pack(side="right", padx=(10, 0))

        txt_box = ctk.CTkFrame(row, fg_color="transparent")
        txt_box.pack(side="left", fill="x", expand=True)

        eff_wrap = wrap_fn or (lambda w: w - 110)

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                txt_box,
                translation_key=title,
                font=self.font_body,
                anchor="w",
                justify="left",
                text_color=("#0f172a", "#f8fafc"),
            ),
            eff_wrap,
        ).pack(anchor="w", fill="x")

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                txt_box,
                translation_key=desc,
                font=self.font_small,
                anchor="w",
                justify="left",
                text_color=("#64748b", "#94a3b8"),
            ),
            eff_wrap,
        ).pack(anchor="w", fill="x")
        return row

    # ---------------- Page 2: Live Sandbox (Isolated + Risk-Colored + Allowlist Menu) ----------------

    def _build_page_sandbox(self) -> None:
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["sandbox"] = page

        toolbar = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        toolbar.pack(fill="x", pady=(0, 8))

        self.sb_tb_row1 = ctk.CTkFrame(toolbar, fg_color="transparent")
        self.sb_tb_row1.pack(fill="x", padx=12, pady=(8, 4))

        self._sb_toolbar_btns = [
            self._localized_widget(
                ctk.CTkButton,
                self.sb_tb_row1,
                translation_key="btn_load_sample",
                font=self.font_small,
                width=10,
                height=32,
                corner_radius=8,
                fg_color=("#475569", "#334155"),
                hover_color=("#334155", "#475569"),
                command=self._load_sample_into_sandbox,
            ),
            self._localized_widget(
                ctk.CTkButton,
                self.sb_tb_row1,
                translation_key="btn_run_sanitize",
                font=self.font_h3,
                width=10,
                height=32,
                corner_radius=8,
                fg_color=("#059669", "#059669"),
                hover_color=("#047857", "#047857"),
                command=self._run_sandbox_sanitize,
            ),
            self._localized_widget(
                ctk.CTkButton,
                self.sb_tb_row1,
                translation_key="btn_run_restore",
                font=self.font_small,
                width=10,
                height=32,
                corner_radius=8,
                fg_color=("#2563eb", "#2563eb"),
                hover_color=("#1d4ed8", "#1d4ed8"),
                command=self._run_sandbox_restore,
            ),
            self._localized_widget(
                ctk.CTkButton,
                self.sb_tb_row1,
                translation_key="btn_copy_output",
                font=self.font_small,
                width=10,
                height=32,
                corner_radius=8,
                fg_color=("#475569", "#334155"),
                hover_color=("#334155", "#475569"),
                command=self._copy_sandbox_output,
            ),
            self._localized_widget(
                ctk.CTkButton,
                self.sb_tb_row1,
                translation_key="btn_clear_sandbox",
                font=self.font_small,
                width=72,
                height=32,
                corner_radius=8,
                fg_color=("#dc2626", "#991b1b"),
                hover_color=("#b91c1c", "#7f1d1d"),
                command=self._clear_sandbox,
            ),
        ]

        tb_row2 = ctk.CTkFrame(toolbar, fg_color="transparent")
        tb_row2.pack(fill="x", padx=12, pady=(2, 8))

        self._localized_widget(
            ctk.CTkButton,
            tb_row2,
            translation_key="btn_sync_sandbox_vault",
            font=self.font_small,
            width=10,
            height=26,
            corner_radius=7,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._sync_sandbox_to_global_vault,
        ).pack(side="right", padx=(8, 0))

        self.var_sandbox_isolate = tk.BooleanVar(value=self._sandbox_isolate)
        self._localized_widget(
            ctk.CTkCheckBox,
            tb_row2,
            translation_key="sw_sandbox_isolate",
            font=self.font_small,
            variable=self.var_sandbox_isolate,
            onvalue=True,
            offvalue=False,
            checkbox_width=16,
            checkbox_height=16,
            command=self._on_toggle_sandbox_isolate,
        ).pack(side="left")

        # Multi-Row Wrapping Category Breakdown Bar
        self.sandbox_cat_bar = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=10,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        self.sandbox_cat_bar.pack(fill="x", pady=(0, 8))

        self.sandbox_cat_inner = ctk.CTkFrame(self.sandbox_cat_bar, fg_color="transparent")
        self.sandbox_cat_inner.pack(fill="x", padx=10, pady=5)

        self._localized_widget(
            ctk.CTkLabel,
            self.sandbox_cat_inner,
            translation_key="sandbox_cat_empty",
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(side="left")

        panes = ctk.CTkFrame(page, fg_color="transparent")
        panes.pack(fill="both", expand=True)
        panes.grid_columnconfigure((0, 1), weight=1, uniform="sbpane")
        panes.grid_rowconfigure(0, weight=1)

        left_card = ctk.CTkFrame(
            panes,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                left_card,
                translation_key="sandbox_left_title",
                font=self.font_h3,
                text_color=("#0f172a", "#f8fafc"),
                justify="left",
            ),
            lambda w: max(180, w // 2 - 44),
        ).pack(anchor="w", fill="x", padx=12, pady=(8, 4))

        self.sandbox_input = ctk.CTkTextbox(
            left_card,
            font=self.font_mono,
            fg_color=("#f8fafc", "#0f172a"),
            text_color=("#0f172a", "#e2e8f0"),
            corner_radius=8,
            wrap="word",
        )
        self.sandbox_input.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._sandbox_debounce_id = None
        self.sandbox_input.bind("<KeyRelease>", self._on_sandbox_input_changed)
        self.sandbox_input.bind("<<Paste>>", self._on_sandbox_input_changed)
        self.sandbox_input.bind("<<Cut>>", self._on_sandbox_input_changed)
        self._attach_text_context_menu(self.sandbox_input, is_textbox=True)

        right_card = ctk.CTkFrame(
            panes,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        right_card.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                right_card,
                translation_key="sandbox_right_title",
                font=self.font_h3,
                text_color=("#059669", "#34d399"),
                justify="left",
            ),
            lambda w: max(180, w // 2 - 44),
        ).pack(anchor="w", fill="x", padx=12, pady=(8, 4))

        self.sandbox_output = ctk.CTkTextbox(
            right_card,
            font=self.font_mono,
            fg_color=("#f8fafc", "#0f172a"),
            text_color=("#0f172a", "#e2e8f0"),
            corner_radius=8,
            wrap="word",
        )
        self.sandbox_output.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._attach_text_context_menu(
            self.sandbox_output, is_textbox=True, allow_placeholder_allowlist=True
        )
        self._configure_sandbox_highlight_tag()
        if self._saved_sandbox_input:
            self.sandbox_input.insert("1.0", self._saved_sandbox_input)
        if self._saved_sandbox_output:
            self.sandbox_output.insert("1.0", self._saved_sandbox_output)
            self._highlight_placeholders_in_output()
        if self._saved_sandbox_cat_counts:
            self._render_sandbox_category_pills(self._saved_sandbox_cat_counts)

    def _configure_sandbox_highlight_tag(self) -> None:
        inner_text = getattr(self.sandbox_output, "_textbox", None)
        if inner_text is None:
            return
        palette = RISK_TAG_STYLES["dark" if self.theme_mode == "dark" else "light"]
        for tier, (bg, fg) in palette.items():
            inner_text.tag_configure(f"tier_{tier}", background=bg, foreground=fg)
        biz_bg, biz_fg = palette["biz"]
        inner_text.tag_configure("placeholder_tag", background=biz_bg, foreground=biz_fg)

    # ---------------- Page 3: Custom Words & Friendly Rules / Allowlist ----------------

    def _build_page_dict(self) -> None:
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["dict"] = page

        mode_bar = ctk.CTkFrame(page, fg_color="transparent")
        mode_bar.pack(fill="x", pady=(0, 6))

        self._dict_mode_labels = [
            self._t("dict_mode_words"),
            self._t("dict_mode_rules"),
            self._t("dict_mode_regex"),
        ]
        self.dict_mode_seg = ctk.CTkSegmentedButton(
            mode_bar,
            values=self._dict_mode_labels,
            font=self.font_h3,
            height=34,
            corner_radius=8,
            selected_color=("#059669", "#059669"),
            selected_hover_color=("#047857", "#047857"),
            command=self._on_dict_submode_selected,
        )
        self.dict_mode_seg.pack(fill="x")

        # Sub-container 1: Custom Words
        self.dict_words_pane = ctk.CTkFrame(page, fg_color="transparent")

        banner = ctk.CTkFrame(
            self.dict_words_pane,
            fg_color=("#eff6ff", "#172554"),
            corner_radius=12,
            border_width=1,
            border_color=("#bfdbfe", "#1e40af"),
        )
        banner.pack(fill="x", pady=(2, 8))

        self._localized_widget(
            ctk.CTkLabel,
            banner,
            translation_key="dict_banner_title",
            font=self.font_h3,
            text_color=("#1d4ed8", "#93c5fd"),
        ).pack(anchor="w", padx=14, pady=(8, 2))

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                banner,
                translation_key="dict_banner_desc",
                font=self.font_small,
                text_color=("#1e40af", "#bfdbfe"),
                justify="left",
            ),
            lambda w: w - 52,
        ).pack(anchor="w", fill="x", padx=14, pady=(0, 8))

        add_card = ctk.CTkFrame(
            self.dict_words_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        add_card.pack(fill="x", pady=(0, 8))

        add_row = ctk.CTkFrame(add_card, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=(10, 4))

        self._localized_widget(
            ctk.CTkLabel,
            add_row,
            translation_key="lbl_add_cat",
            font=self.font_body,
        ).pack(side="left")

        cat_values = [self._cat_label(k) for k in CATEGORY_KEYS]
        self.add_cat_combo = ctk.CTkComboBox(
            add_row,
            values=cat_values,
            font=self.font_small,
            width=190,
            state="readonly",
        )
        self.add_cat_combo.set(
            self._cat_label(self._saved_add_cat_key)
            if self._saved_add_cat_key in CATEGORY_KEYS
            else cat_values[0]
        )
        self.add_cat_combo.pack(side="left", padx=(6, 8))

        self.entry_new_word = self._localized_widget(
            ctk.CTkEntry,
            add_row,
            translation_key="placeholder_add_word",
            translation_option="placeholder_text",
            font=self.font_body,
            height=34,
        )
        self.entry_new_word.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_new_word.bind("<Return>", lambda _e: self._add_word())
        if self._saved_entry_new_word:
            self.entry_new_word.insert(0, self._saved_entry_new_word)
        self._attach_text_context_menu(self.entry_new_word, is_textbox=False)

        self._localized_widget(
            ctk.CTkButton,
            add_row,
            translation_key="btn_add_word",
            font=self.font_h3,
            width=102,
            height=34,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            command=self._add_word,
        ).pack(side="left")

        ww_row = ctk.CTkFrame(add_card, fg_color="transparent")
        ww_row.pack(fill="x", padx=12, pady=(2, 8))
        self._localized_widget(
            ctk.CTkCheckBox,
            ww_row,
            translation_key="sw_whole_word_title",
            font=self.font_small,
            variable=self.var_whole_word,
            onvalue=True,
            offvalue=False,
            checkbox_width=16,
            checkbox_height=16,
            command=self._on_toggle_whole_word,
        ).pack(side="left")

        self.dict_tools_row = ctk.CTkFrame(self.dict_words_pane, fg_color="transparent")
        self.dict_tools_row.pack(fill="x", pady=(0, 6))

        self._dict_lbl_filter = self._localized_widget(
            ctk.CTkLabel,
            self.dict_tools_row,
            translation_key="lbl_filter_cat",
            font=self.font_small,
        )

        filter_values = [self._cat_label("ALL")] + cat_values
        self.filter_cat_combo = ctk.CTkComboBox(
            self.dict_tools_row,
            values=filter_values,
            font=self.font_small,
            width=165,
            state="readonly",
            command=lambda _v: self.refresh_dictionary_list(),
        )
        self.filter_cat_combo.set(
            self._cat_label(self._saved_filter_cat_key)
            if self._saved_filter_cat_key in (["ALL"] + CATEGORY_KEYS)
            else filter_values[0]
        )

        self._dict_btn_clear = self._localized_widget(
            ctk.CTkButton,
            self.dict_tools_row,
            translation_key="btn_clear_all_dict",
            font=self.font_small,
            width=10,
            height=30,
            corner_radius=8,
            fg_color=("#dc2626", "#991b1b"),
            hover_color=("#b91c1c", "#7f1d1d"),
            command=self._confirm_clear_all_custom_words,
        )

        self._dict_btn_exp = self._localized_widget(
            ctk.CTkButton,
            self.dict_tools_row,
            translation_key="btn_export",
            font=self.font_small,
            width=10,
            height=30,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=self._export_dictionary,
        )

        self._dict_btn_imp = self._localized_widget(
            ctk.CTkButton,
            self.dict_tools_row,
            translation_key="btn_import",
            font=self.font_small,
            width=10,
            height=30,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=self._import_dictionary,
        )

        self._dict_btn_json = self._localized_widget(
            ctk.CTkButton,
            self.dict_tools_row,
            translation_key="btn_json_editor",
            font=self.font_small,
            width=10,
            height=30,
            corner_radius=8,
            fg_color=("#2563eb", "#2563eb"),
            hover_color=("#1d4ed8", "#1d4ed8"),
            command=self.open_in_app_json_modal,
        )

        self.dict_scroll = ctk.CTkScrollableFrame(
            self.dict_words_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        self.dict_scroll.pack(fill="both", expand=True)

        # Sub-container 2: Allowlist & Human-Friendly Rules + Scenario Presets
        self.dict_rules_pane = ctk.CTkFrame(page, fg_color="transparent")

        self.dict_allow_card = ctk.CTkFrame(
            self.dict_rules_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )

        allow_wrap = lambda w: (int(w * 0.38) - 40) if w >= 760 else (w - 48)
        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                self.dict_allow_card,
                translation_key="allowlist_title",
                font=self.font_h3,
                text_color=("#0f172a", "#f8fafc"),
                justify="left",
            ),
            allow_wrap,
        ).pack(anchor="w", fill="x", padx=12, pady=(10, 6))

        allow_in_row = ctk.CTkFrame(self.dict_allow_card, fg_color="transparent")
        allow_in_row.pack(fill="x", padx=12, pady=(0, 8))

        self.entry_allowlist = self._localized_widget(
            ctk.CTkEntry,
            allow_in_row,
            translation_key="placeholder_allowlist",
            translation_option="placeholder_text",
            font=self.font_small,
            height=32,
        )
        self.entry_allowlist.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_allowlist.bind("<Return>", lambda _e: self._add_allowlist_from_gui())
        if self._saved_entry_allowlist:
            self.entry_allowlist.insert(0, self._saved_entry_allowlist)
        self._attach_text_context_menu(self.entry_allowlist, is_textbox=False)

        self._localized_widget(
            ctk.CTkButton,
            allow_in_row,
            translation_key="btn_add_allowlist",
            font=self.font_small,
            width=95,
            height=32,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            command=self._add_allowlist_from_gui,
        ).pack(side="left")

        self.allowlist_scroll = ctk.CTkScrollableFrame(
            self.dict_allow_card,
            fg_color=("#f8fafc", "#0f172a"),
            corner_radius=8,
        )
        self.allowlist_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._rendered_allowlist_items = None

        self.dict_rules_card = ctk.CTkFrame(
            self.dict_rules_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )

        rules_wrap = lambda w: (int(w * 0.58) - 40) if w >= 760 else (w - 48)
        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                self.dict_rules_card,
                translation_key="rules_toggle_title",
                font=self.font_h3,
                text_color=("#0f172a", "#f8fafc"),
                justify="left",
            ),
            rules_wrap,
        ).pack(anchor="w", fill="x", padx=12, pady=(10, 6))

        # Preset Buttons Row (responsive 3-up or 2+1)
        self.dict_preset_row = ctk.CTkFrame(self.dict_rules_card, fg_color="transparent")
        self.dict_preset_row.pack(fill="x", padx=12, pady=(0, 6))
        self._preset_btns = [
            self._localized_widget(
                ctk.CTkButton,
                self.dict_preset_row,
                translation_key=t_key,
                font=self.font_small,
                width=10,
                height=28,
                corner_radius=7,
                fg_color=("#e2e8f0", "#334155"),
                hover_color=("#cbd5e1", "#475569"),
                text_color=("#0f172a", "#f8fafc"),
                command=lambda p=p_key: self._apply_preset_from_gui(p),
            )
            for p_key, t_key in (
                ("dev", "preset_dev"),
                ("hr", "preset_hr"),
                ("strict", "preset_strict"),
            )
        ]

        # Rule Search Input
        self.rule_search_var = tk.StringVar(value=self._saved_rule_search)
        self.rule_search_var.trace_add("write", lambda *_a: self._schedule_rule_search_refresh())
        self.entry_rule_search = self._localized_widget(
            ctk.CTkEntry,
            self.dict_rules_card,
            textvariable=self.rule_search_var,
            translation_key="placeholder_rule_search",
            translation_option="placeholder_text",
            font=self.font_small,
            height=30,
        )
        self.entry_rule_search.pack(fill="x", padx=12, pady=(0, 6))
        self._attach_text_context_menu(self.entry_rule_search, is_textbox=False)

        self.rules_toggle_scroll = ctk.CTkScrollableFrame(
            self.dict_rules_card,
            fg_color=("#f8fafc", "#0f172a"),
            corner_radius=8,
        )
        self.rules_toggle_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._rule_row_cache.clear()
        self._rendered_rule_names = []

        # Sub-container 3: User-Defined Custom Regex Rules + Live ReDoS Safety Tester
        self.dict_regex_pane = ctk.CTkFrame(page, fg_color="transparent")

        regex_card = ctk.CTkFrame(
            self.dict_regex_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        regex_card.pack(fill="x", pady=(2, 8))

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                regex_card,
                translation_key="regex_banner_title",
                font=self.font_h3,
                text_color=("#0f172a", "#f8fafc"),
                justify="left",
            ),
            lambda w: w - 52,
        ).pack(anchor="w", fill="x", padx=12, pady=(10, 6))

        self.regex_form_grid = ctk.CTkFrame(regex_card, fg_color="transparent")
        self.regex_form_grid.pack(fill="x", padx=12, pady=(0, 6))

        self._lbl_rg_name = self._localized_widget(
            ctk.CTkLabel, self.regex_form_grid, translation_key="regex_lbl_name", font=self.font_small
        )
        self.entry_regex_name = self._localized_widget(
            ctk.CTkEntry,
            self.regex_form_grid,
            translation_key="regex_ph_name",
            translation_option="placeholder_text",
            font=self.font_small,
            height=30,
        )
        if self._saved_regex_name:
            self.entry_regex_name.insert(0, self._saved_regex_name)
        self._attach_text_context_menu(self.entry_regex_name, is_textbox=False)

        self._lbl_rg_cat = self._localized_widget(
            ctk.CTkLabel, self.regex_form_grid, translation_key="regex_lbl_cat", font=self.font_small
        )
        self.entry_regex_cat = self._localized_widget(
            ctk.CTkEntry,
            self.regex_form_grid,
            translation_key="regex_ph_cat",
            translation_option="placeholder_text",
            font=self.font_small,
            height=30,
        )
        self.entry_regex_cat.insert(0, self._saved_regex_cat or "CUSTOM_REGEX")
        self.entry_regex_cat.bind("<KeyRelease>", lambda _e: self._on_regex_live_test_changed())
        self._attach_text_context_menu(self.entry_regex_cat, is_textbox=False)

        self._lbl_rg_tpl = self._localized_widget(
            ctk.CTkLabel, self.regex_form_grid, translation_key="regex_lbl_tpl", font=self.font_small
        )
        self.combo_regex_tpl = ctk.CTkComboBox(
            self.regex_form_grid,
            values=list(ALLOWED_PLACEHOLDER_TEMPLATES),
            font=self.font_mono_sm,
            height=30,
            state="readonly",
            command=lambda _v: self._on_regex_live_test_changed(),
        )
        self.combo_regex_tpl.set(
            self._saved_regex_tpl
            if self._saved_regex_tpl in ALLOWED_PLACEHOLDER_TEMPLATES
            else ALLOWED_PLACEHOLDER_TEMPLATES[0]
        )

        pat_row = ctk.CTkFrame(regex_card, fg_color="transparent")
        pat_row.pack(fill="x", padx=12, pady=(0, 6))
        self._localized_widget(
            ctk.CTkLabel, pat_row, translation_key="regex_lbl_pattern", font=self.font_small
        ).pack(side="left", padx=(0, 6))
        self.btn_add_regex = self._localized_widget(
            ctk.CTkButton,
            pat_row,
            translation_key="regex_btn_add",
            font=self.font_small,
            width=112,
            height=32,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            command=self._add_custom_regex_from_gui,
        )
        self.btn_add_regex.pack(side="right", padx=(8, 0))
        self.entry_regex_pattern = self._localized_widget(
            ctk.CTkEntry,
            pat_row,
            translation_key="regex_ph_pattern",
            translation_option="placeholder_text",
            font=self.font_mono_sm,
            height=32,
        )
        self.entry_regex_pattern.pack(side="left", fill="x", expand=True)
        if self._saved_regex_pattern:
            self.entry_regex_pattern.insert(0, self._saved_regex_pattern)
        self.entry_regex_pattern.bind("<KeyRelease>", lambda _e: self._on_regex_live_test_changed())
        self.entry_regex_pattern.bind("<Return>", lambda _e: self._add_custom_regex_from_gui())
        self._attach_text_context_menu(self.entry_regex_pattern, is_textbox=False)

        test_row = ctk.CTkFrame(regex_card, fg_color="transparent")
        test_row.pack(fill="x", padx=12, pady=(0, 4))
        self._localized_widget(
            ctk.CTkLabel, test_row, translation_key="regex_lbl_test", font=self.font_small
        ).pack(side="left", padx=(0, 6))
        self.entry_regex_test = self._localized_widget(
            ctk.CTkEntry,
            test_row,
            translation_key="regex_ph_test",
            translation_option="placeholder_text",
            font=self.font_mono_sm,
            height=30,
        )
        self.entry_regex_test.pack(side="left", fill="x", expand=True)
        if self._saved_regex_test:
            self.entry_regex_test.insert(0, self._saved_regex_test)
        self.entry_regex_test.bind("<KeyRelease>", lambda _e: self._on_regex_live_test_changed())
        self._attach_text_context_menu(self.entry_regex_test, is_textbox=False)

        self.lbl_regex_test_result = ctk.CTkLabel(
            regex_card,
            text=self._t("regex_test_idle"),
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
            anchor="w",
            justify="left",
        )
        self._register_wrap_label(self.lbl_regex_test_result, lambda w: w - 52)
        self.lbl_regex_test_result.pack(anchor="w", fill="x", padx=12, pady=(0, 10))

        self.custom_regex_scroll = ctk.CTkScrollableFrame(
            self.dict_regex_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        self.custom_regex_scroll.pack(fill="both", expand=True)

        dict_idx = {"words": 0, "rules": 1, "regex": 2}.get(self._dict_submode, 0)
        self.dict_mode_seg.set(self._dict_mode_labels[dict_idx])
        self._show_dict_submode(self._dict_submode)

    # ---------------- Page 4: Session Vault ----------------

    def _build_page_vault(self) -> None:
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["vault"] = page

        top_bar = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        top_bar.pack(fill="x", pady=(0, 8))

        bar_row1 = ctk.CTkFrame(top_bar, fg_color="transparent")
        bar_row1.pack(fill="x", padx=12, pady=(8, 4))

        self.var_reveal_vault = tk.BooleanVar(value=self._reveal_vault_originals)
        self._localized_widget(
            ctk.CTkSwitch,
            bar_row1,
            translation_key="sw_reveal_vault",
            font=self.font_small,
            variable=self.var_reveal_vault,
            onvalue=True,
            offvalue=False,
            progress_color=("#059669", "#10b981"),
            command=self._on_toggle_reveal_vault,
        ).pack(side="right", padx=(10, 0))

        self.vault_search_var = tk.StringVar(value=self._saved_vault_search)
        self.vault_search_var.trace_add("write", lambda *_a: self._schedule_vault_search_refresh())
        self.entry_vault_search = self._localized_widget(
            ctk.CTkEntry,
            bar_row1,
            textvariable=self.vault_search_var,
            translation_key="placeholder_search_vault",
            translation_option="placeholder_text",
            font=self.font_small,
            height=30,
        )
        self.entry_vault_search.pack(side="left", fill="x", expand=True)
        self._attach_text_context_menu(self.entry_vault_search, is_textbox=False)

        self.vault_actions_row = ctk.CTkFrame(top_bar, fg_color="transparent")
        self.vault_actions_row.pack(fill="x", padx=12, pady=(2, 8))

        self._vault_action_btns = [
            self._localized_widget(
                ctk.CTkButton,
                self.vault_actions_row,
                translation_key="btn_refresh_vault",
                font=self.font_small,
                width=10,
                height=30,
                corner_radius=8,
                fg_color=("#475569", "#334155"),
                hover_color=("#334155", "#475569"),
                command=self.refresh_vault_list,
            ),
            self._localized_widget(
                ctk.CTkButton,
                self.vault_actions_row,
                translation_key="btn_export_enc_vault",
                font=self.font_small,
                width=10,
                height=30,
                corner_radius=8,
                fg_color=("#2563eb", "#2563eb"),
                hover_color=("#1d4ed8", "#1d4ed8"),
                command=self._export_encrypted_vault_from_gui,
            ),
            self._localized_widget(
                ctk.CTkButton,
                self.vault_actions_row,
                translation_key="btn_import_enc_vault",
                font=self.font_small,
                width=10,
                height=30,
                corner_radius=8,
                fg_color=("#475569", "#334155"),
                hover_color=("#334155", "#475569"),
                command=self._import_encrypted_vault_from_gui,
            ),
            self._localized_widget(
                ctk.CTkButton,
                self.vault_actions_row,
                translation_key="btn_clear_vault",
                font=self.font_small,
                width=10,
                height=30,
                corner_radius=8,
                fg_color=("#dc2626", "#991b1b"),
                hover_color=("#b91c1c", "#7f1d1d"),
                command=self._confirm_clear_vault_from_gui,
            ),
        ]

        self.vault_scroll = ctk.CTkScrollableFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        self.vault_scroll.pack(fill="both", expand=True)

    # ---------------- Page 5: Hotkeys & Privacy Settings (Zero Overflow 2-Row Layout) ----------------

    def _build_page_settings(self) -> None:
        page = ctk.CTkScrollableFrame(self.page_container, fg_color="transparent")
        self.pages["settings"] = page

        hk = self.sanitizer.hotkeys

        # Hotkeys Card (Spacious 2-row grid, never clips at 860px)
        hk_card = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=14,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        hk_card.pack(fill="x", pady=(0, 12))

        self._localized_widget(
            ctk.CTkLabel,
            hk_card,
            translation_key="hotkey_section_title",
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w", padx=16, pady=(14, 2))

        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                hk_card,
                translation_key="hotkey_section_desc",
                font=self.font_small,
                text_color=("#64748b", "#94a3b8"),
                wraplength=680,
                justify="left",
            ),
            lambda w: w - 56,
        ).pack(anchor="w", fill="x", padx=16, pady=(0, 10))

        row_san = ctk.CTkFrame(hk_card, fg_color="transparent")
        row_san.pack(fill="x", padx=16, pady=(0, 8))

        self._localized_widget(
            ctk.CTkLabel,
            row_san,
            translation_key="lbl_hk_sanitize",
            font=self.font_body,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(side="left")

        self.combo_hk_sanitize = _HotkeyRecorderBox(
            row_san,
            value=self._saved_hk_sanitize or hk.get("sanitize", "alt+s"),
            font=self.font_mono,
            listening_text=self._t("hk_box_listening"),
            on_start_record=lambda: self._start_hotkey_recording("sanitize"),
            on_manual_commit=lambda _val: self._save_and_apply_hotkeys(),
            on_manual_cancel=lambda: self.status_var.set(self._t("msg_hk_cancelled")),
            on_edit_state_changed=lambda editing: self._update_edit_button_visual("sanitize", editing),
            width=210,
        )
        self.combo_hk_sanitize.pack(side="left", padx=(8, 8))

        self.btn_rec_san = self._localized_widget(
            ctk.CTkButton,
            row_san,
            translation_key="btn_hk_record",
            font=self.font_small,
            width=126,
            height=34,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=lambda: self._start_hotkey_recording("sanitize"),
        )
        self.btn_rec_san.pack(side="left", padx=(0, 6))

        self.btn_edit_san = ctk.CTkButton(
            row_san,
            text="✏️",
            font=self.font_small,
            width=36,
            height=34,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=lambda: self._toggle_manual_hotkey_edit("sanitize"),
        )
        self.btn_edit_san.pack(side="left")

        row_res = ctk.CTkFrame(hk_card, fg_color="transparent")
        row_res.pack(fill="x", padx=16, pady=(0, 10))

        self._localized_widget(
            ctk.CTkLabel,
            row_res,
            translation_key="lbl_hk_restore",
            font=self.font_body,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(side="left")

        self.combo_hk_restore = _HotkeyRecorderBox(
            row_res,
            value=self._saved_hk_restore or hk.get("restore", "alt+r"),
            font=self.font_mono,
            listening_text=self._t("hk_box_listening"),
            on_start_record=lambda: self._start_hotkey_recording("restore"),
            on_manual_commit=lambda _val: self._save_and_apply_hotkeys(),
            on_manual_cancel=lambda: self.status_var.set(self._t("msg_hk_cancelled")),
            on_edit_state_changed=lambda editing: self._update_edit_button_visual("restore", editing),
            width=210,
        )
        self.combo_hk_restore.pack(side="left", padx=(8, 8))

        self.btn_rec_res = self._localized_widget(
            ctk.CTkButton,
            row_res,
            translation_key="btn_hk_record",
            font=self.font_small,
            width=126,
            height=34,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=lambda: self._start_hotkey_recording("restore"),
        )
        self.btn_rec_res.pack(side="left", padx=(0, 6))

        self.btn_edit_res = ctk.CTkButton(
            row_res,
            text="✏️",
            font=self.font_small,
            width=36,
            height=34,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=lambda: self._toggle_manual_hotkey_edit("restore"),
        )
        self.btn_edit_res.pack(side="left")

        row_act = ctk.CTkFrame(hk_card, fg_color="transparent")
        row_act.pack(fill="x", padx=16, pady=(0, 8))

        self._localized_widget(
            ctk.CTkButton,
            row_act,
            translation_key="btn_hk_reset",
            font=self.font_small,
            width=120,
            height=32,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._reset_default_hotkeys,
        ).pack(side="left")

        self.hk_status_bar = ctk.CTkFrame(
            hk_card,
            fg_color=("#f8fafc", "#0f172a"),
            corner_radius=9,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        self.hk_status_bar.pack(fill="x", padx=16, pady=(0, 14))

        self.btn_hk_autofix = self._localized_widget(
            ctk.CTkButton,
            self.hk_status_bar,
            translation_key="btn_hk_autofix",
            font=self.font_small,
            width=156,
            height=28,
            corner_radius=7,
            fg_color=("#d97706", "#b45309"),
            hover_color=("#b45309", "#92400e"),
            text_color="#ffffff",
            command=self._auto_fix_hotkeys_from_gui,
        )

        self.lbl_settings_hk_status = ctk.CTkLabel(
            self.hk_status_bar,
            text="",
            font=self.font_small,
            text_color=("#059669", "#34d399"),
            anchor="w",
            justify="left",
        )
        self._register_wrap_label(self.lbl_settings_hk_status, lambda w: w - 230)
        self.lbl_settings_hk_status.pack(side="left", fill="x", expand=True, padx=12, pady=8)

        # Privacy & Desktop Feedback Card
        priv_card = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=14,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        priv_card.pack(fill="x", pady=(0, 12))

        self._localized_widget(
            ctk.CTkLabel,
            priv_card,
            translation_key="privacy_section_title",
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        self._create_switch_row(
            priv_card,
            title="sw_cruise_title",
            desc="sw_cruise_desc",
            variable=self.var_auto_sanitize,
            command=self._on_toggle_auto_sanitize,
        )
        self._create_switch_row(
            priv_card,
            title="sw_clip_guard_title",
            desc="sw_clip_guard_desc",
            variable=self.var_clip_guard,
            command=self._on_toggle_clip_guard,
        )
        self._create_switch_row(
            priv_card,
            title="sw_hud_title",
            desc="sw_hud_desc",
            variable=self.var_hud_enabled,
            command=self._on_toggle_hud,
        )
        if platform.system() == "Windows":
            self._create_switch_row(
                priv_card,
                title="sw_startup_title",
                desc="sw_startup_desc",
                variable=self.var_startup,
                command=self._on_toggle_startup,
            )
        self._create_switch_row(
            priv_card,
            title="sw_entropy_title",
            desc="sw_entropy_desc",
            variable=self.var_entropy,
            command=self._on_toggle_entropy,
        )

        idle_row = ctk.CTkFrame(priv_card, fg_color="transparent")
        idle_row.pack(fill="x", padx=16, pady=(6, 14))
        self.combo_idle_wipe = ctk.CTkComboBox(
            idle_row,
            values=[self._idle_label(m) for m in VALID_IDLE_WIPE_MINUTES],
            width=180,
            height=30,
            font=self.font_small,
            state="readonly",
            command=self._on_idle_wipe_selected,
        )
        self.combo_idle_wipe.set(self._idle_label(self.sanitizer.idle_wipe_minutes))
        self.combo_idle_wipe.pack(side="right", padx=(10, 0))
        self._register_wrap_label(
            self._localized_widget(
                ctk.CTkLabel,
                idle_row,
                translation_key="lbl_idle_wipe",
                font=self.font_body,
                justify="left",
                text_color=("#0f172a", "#f8fafc"),
            ),
            lambda w: w - 250,
        ).pack(side="left", fill="x", expand=True)

    # ---------------- Page 6: Quick Guide ----------------

    def _build_page_guide(self) -> None:
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["guide"] = page

        # 3 visual bite-sized step cards at top
        steps_row = ctk.CTkFrame(page, fg_color="transparent")
        steps_row.pack(fill="x", pady=(0, 8))
        steps_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="gstep")

        self.guide_step_descs: List[Tuple[str, ctk.CTkLabel]] = []
        step_specs = (
            ("guide_step1_t", "guide_step1_d", ("#dbeafe", "#1e3a8a"), ("#1d4ed8", "#93c5fd")),
            ("guide_step2_t", "guide_step2_d", ("#dcfce7", "#064e3b"), ("#047857", "#6ee7b7")),
            ("guide_step3_t", "guide_step3_d", ("#fef3c7", "#451a03"), ("#b45309", "#fcd34d")),
        )
        for col_idx, (t_key, d_key, bg_pair, fg_pair) in enumerate(step_specs):
            padx = (0, 6) if col_idx == 0 else ((3, 3) if col_idx == 1 else (6, 0))
            card = ctk.CTkFrame(
                steps_row,
                fg_color=("#ffffff", "#1e293b"),
                corner_radius=10,
                border_width=1,
                border_color=("#e2e8f0", "#334155"),
            )
            card.grid(row=0, column=col_idx, sticky="nsew", padx=padx)
            pill = ctk.CTkFrame(card, fg_color=bg_pair, corner_radius=6)
            pill.pack(anchor="w", padx=10, pady=(8, 4))
            self._localized_widget(
                ctk.CTkLabel,
                pill,
                translation_key=t_key,
                font=self.font_small,
                text_color=fg_pair,
            ).pack(padx=8, pady=2)
            lbl_d = ctk.CTkLabel(
                card,
                text=self._format_hotkey_text(self._t(d_key)),
                font=self.font_small,
                text_color=("#334155", "#cbd5e1"),
                anchor="w",
                justify="left",
            )
            lbl_d.pack(anchor="w", fill="x", padx=10, pady=(0, 8))
            self.guide_step_descs.append((d_key, lbl_d))

        guide_card = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        guide_card.pack(fill="both", expand=True, pady=(0, 8))

        self.guide_box = ctk.CTkTextbox(
            guide_card,
            font=self.font_body,
            fg_color="transparent",
            text_color=("#0f172a", "#e2e8f0"),
            wrap="word",
        )
        self.guide_box.pack(fill="both", expand=True, padx=14, pady=10)
        inner_gb = getattr(self.guide_box, "_textbox", None)
        if inner_gb is not None:
            inner_gb.configure(spacing1=3, spacing2=3, spacing3=5)
            inner_gb.tag_configure("guide_heading", foreground="#38bdf8", font=self.font_h3)
        self.guide_box.insert("1.0", self._guide_text())
        self._style_guide_headings()
        self.guide_box.configure(state="disabled")

        # Collapsible bite-sized FAQ (collapsed by default so users aren't overwhelmed)
        faq_bar = ctk.CTkFrame(page, fg_color="transparent")
        faq_bar.pack(fill="x", pady=(0, 4))
        self.btn_guide_faq = ctk.CTkButton(
            faq_bar,
            text=self._t("guide_faq_hide" if self._guide_faq_open else "guide_faq_show"),
            font=self.font_small,
            height=28,
            corner_radius=8,
            fg_color=("#e2e8f0", "#1e293b"),
            hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._toggle_guide_faq,
        )
        self._reserve_bilingual_text(
            self.btn_guide_faq,
            [tr(lang, key) for lang in ("zh", "en") for key in ("guide_faq_show", "guide_faq_hide")],
        )
        self.btn_guide_faq.pack(anchor="w")

        self.guide_faq_card = ctk.CTkScrollableFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
            height=135,
        )
        for q_idx in range(1, 6):
            row = ctk.CTkFrame(self.guide_faq_card, fg_color=("#f8fafc", "#0f172a"), corner_radius=8)
            row.pack(fill="x", padx=4, pady=3)
            self._register_wrap_label(
                self._localized_widget(
                    ctk.CTkLabel,
                    row,
                    translation_key=f"guide_faq_q{q_idx}",
                    font=self.font_small,
                    text_color=("#0f172a", "#f8fafc"),
                    justify="left",
                ),
                lambda w: w - 48,
            ).pack(anchor="w", fill="x", padx=10, pady=(6, 1))
            self._register_wrap_label(
                self._localized_widget(
                    ctk.CTkLabel,
                    row,
                    translation_key=f"guide_faq_a{q_idx}",
                    font=self.font_small,
                    text_color=("#475569", "#94a3b8"),
                    justify="left",
                ),
                lambda w: w - 48,
            ).pack(anchor="w", fill="x", padx=10, pady=(0, 6))
        if self._guide_faq_open:
            self.guide_faq_card.pack(fill="x", pady=(2, 0))

    def _style_guide_headings(self) -> None:
        inner_gb = getattr(self, "guide_box", None)
        textbox = getattr(inner_gb, "_textbox", None) if inner_gb is not None else None
        if textbox is None:
            return
        textbox.tag_remove("guide_heading", "1.0", "end")
        content = self.guide_box.get("1.0", "end-1c")
        for line_no, line in enumerate(content.splitlines(), start=1):
            if line.startswith(("⚡", "✨", "🔒")):
                textbox.tag_add("guide_heading", f"{line_no}.0", f"{line_no}.end")

    def _toggle_guide_faq(self) -> None:
        self._guide_faq_open = not bool(getattr(self, "_guide_faq_open", False))
        if hasattr(self, "btn_guide_faq") and self.btn_guide_faq.winfo_exists():
            self.btn_guide_faq.configure(
                text=self._t("guide_faq_hide" if self._guide_faq_open else "guide_faq_show")
            )
        if hasattr(self, "guide_faq_card") and self.guide_faq_card.winfo_exists():
            if self._guide_faq_open:
                self.guide_faq_card.pack(fill="x", pady=(2, 0))
            else:
                self.guide_faq_card.pack_forget()

    # ---------------- About & In-App JSON Editor Modals ----------------

    def _show_about(self) -> None:
        if self._about_modal is not None and self._about_modal.winfo_exists():
            self._about_modal.lift()
            return
        modal = _StableCTkToplevel(self.root, fg_color=("#f1f5f9", "#0b0f19"))
        self._about_modal = modal
        modal.title(self._t("about_title"))
        modal.transient(self.root)
        modal.geometry(f"400x240+{self.root.winfo_x() + 120}+{self.root.winfo_y() + 100}")
        modal.resizable(False, False)
        ctk.CTkLabel(modal, text=APP_NAME, font=self.font_title).pack(pady=(24, 4))
        self._about_version_label = ctk.CTkLabel(
            modal,
            text=self._t("about_version").format(version=__version__),
            font=self.font_body,
        )
        self._about_version_label.pack(pady=(0, 12))
        self._localized_widget(
            ctk.CTkLabel,
            modal,
            translation_key="about_description",
            anchor="center",
            font=self.font_body,
            wraplength=350,
        ).pack(padx=24, pady=(0, 16))
        self._localized_widget(
            ctk.CTkButton,
            modal,
            translation_key="btn_close",
            width=100,
            height=32,
            command=modal.destroy,
        ).pack(pady=(0, 20))

    def open_in_app_json_modal(self) -> None:
        """Open a sleek built-in JSON editor modal window inside the app (never external IDE)."""
        if self._json_modal is not None and self._json_modal.winfo_exists():
            self._json_modal.lift()
            self._json_modal.focus_force()
            return

        modal = _StableCTkToplevel(self.root, fg_color=("#f1f5f9", "#0b0f19"))
        self._json_modal = modal
        modal.title(self._t("json_modal_title"))
        modal.geometry("740x540")
        modal.transient(self.root)
        modal.lift()
        modal.focus_force()

        self._localized_widget(
            ctk.CTkLabel,
            modal,
            translation_key="json_modal_hint",
            font=self.font_body,
        ).pack(anchor="w", padx=18, pady=(14, 6))

        editor = ctk.CTkTextbox(
            modal,
            font=self.font_mono,
            fg_color=("#f8fafc", "#0f172a"),
            text_color=("#0f172a", "#e2e8f0"),
            corner_radius=10,
        )
        editor.pack(fill="both", expand=True, padx=18, pady=6)
        self._attach_text_context_menu(editor, is_textbox=True)

        cfg_path = self.sanitizer.ensure_config_exists()
        try:
            raw_json = cfg_path.read_text(encoding="utf-8")
        except Exception:
            raw_json = json.dumps(self.sanitizer.reload_config(), indent=2, ensure_ascii=False)
        editor.insert("1.0", raw_json)

        btn_bar = ctk.CTkFrame(modal, fg_color="transparent")
        btn_bar.pack(fill="x", padx=18, pady=(6, 14))

        def _format_json() -> None:
            content = editor.get("1.0", "end-1c").strip()
            try:
                parsed = json.loads(content)
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                editor.delete("1.0", "end")
                editor.insert("1.0", formatted)
            except json.JSONDecodeError as exc:
                messagebox.showerror(
                    "JSON Error",
                    self._t("msg_json_syntax_pos").format(line=exc.lineno, col=exc.colno),
                    parent=modal,
                )

        def _save_json() -> None:
            content = editor.get("1.0", "end-1c").strip()
            try:
                parsed = json.loads(content)
                validated = self.sanitizer.validate_config_dict(parsed)
                old_hk = self.sanitizer.hotkeys
                new_hk = validated.get("hotkeys", old_hk)
                if new_hk != old_hk and self.on_reload_hotkeys:
                    if not self.on_reload_hotkeys(new_hk):
                        raise ValueError("Global hotkey registration failed")
                self.sanitizer.save_config(validated)
                self._sync_ui_after_external_config_update()
                self.status_var.set(self._t("msg_json_saved"))
                messagebox.showinfo("OK", self._t("msg_json_saved"), parent=modal)
                modal.destroy()
            except json.JSONDecodeError as exc:
                messagebox.showerror(
                    "JSON Error",
                    self._t("msg_json_syntax_pos").format(line=exc.lineno, col=exc.colno),
                    parent=modal,
                )
            except Exception:
                messagebox.showerror("JSON Error", self._t("msg_operation_failed"), parent=modal)

        def _reveal_in_explorer() -> None:
            sys_name = platform.system()
            try:
                if sys_name == "Windows":
                    subprocess.Popen(["explorer", f"/select,{cfg_path}"])
                elif sys_name == "Darwin":
                    subprocess.Popen(["open", "-R", str(cfg_path)])
                else:
                    subprocess.Popen(["xdg-open", str(cfg_path.parent)])
            except Exception:
                pass

        self._localized_widget(
            ctk.CTkButton,
            btn_bar,
            translation_key="btn_save_json",
            font=self.font_h3,
            height=34,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            command=_save_json,
        ).pack(side="left", padx=(0, 8))

        self._localized_widget(
            ctk.CTkButton,
            btn_bar,
            translation_key="btn_format_json",
            font=self.font_small,
            height=34,
            corner_radius=8,
            fg_color=("#2563eb", "#2563eb"),
            hover_color=("#1d4ed8", "#1d4ed8"),
            command=_format_json,
        ).pack(side="left", padx=(0, 8))

        self._localized_widget(
            ctk.CTkButton,
            btn_bar,
            translation_key="btn_open_folder",
            font=self.font_small,
            height=34,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=_reveal_in_explorer,
        ).pack(side="left")

        self._localized_widget(
            ctk.CTkButton,
            btn_bar,
            translation_key="btn_close",
            font=self.font_small,
            width=84,
            height=34,
            corner_radius=8,
            fg_color=("#64748b", "#334155"),
            command=modal.destroy,
        ).pack(side="right")

    def _sync_ui_after_external_config_update(self) -> None:
        """Apply live theme, language, and hotkey changes after JSON modal save or full import."""
        new_theme = self.sanitizer.theme
        if new_theme != self.theme_mode:
            self.theme_mode = new_theme
            ctk.set_appearance_mode("Light" if self.theme_mode == "light" else "Dark")
            if hasattr(self, "btn_theme") and self.btn_theme.winfo_exists():
                self.btn_theme.configure(
                    text=self._t("btn_theme_light" if self.theme_mode == "dark" else "btn_theme_dark")
                )
            self._configure_sandbox_highlight_tag()
        new_lang = self.sanitizer.language
        if new_lang != self.lang:
            add_cat = self._label_to_cat(self.add_cat_combo.get()) if hasattr(self, "add_cat_combo") else "COMPANY"
            filter_cat = self._label_to_cat(self.filter_cat_combo.get()) if hasattr(self, "filter_cat_combo") else "ALL"
            self.lang = new_lang
            self._refresh_translations(add_cat, filter_cat)
            if self.on_language_changed:
                self.on_language_changed()
        self._refresh_hotkey_labels()
        self.refresh_all()

    # ---------------- Navigation & Refresh ----------------

    def _on_nav_selected(self, selected_label: str) -> None:
        page_key = self._label_to_nav_key.get(selected_label, "home")
        self._show_page(page_key)

    def _navigate_to_page(self, page_key: str) -> None:
        if hasattr(self, "nav_bar") and page_key in getattr(self, "_nav_key_to_label", {}):
            self.nav_bar.set(self._nav_key_to_label[page_key])
        self._show_page(page_key)

    def _open_rules_list_page(self) -> None:
        self._navigate_to_page("dict")
        if hasattr(self, "dict_mode_seg") and len(getattr(self, "_dict_mode_labels", [])) > 1:
            self.dict_mode_seg.set(self._dict_mode_labels[1])
        self._show_dict_submode("rules")

    def _show_page(self, page_key: str) -> None:
        if page_key != "settings":
            if self._recording_target is not None:
                self._cancel_hotkey_recording()
            for attr in ("combo_hk_sanitize", "combo_hk_restore"):
                box = getattr(self, attr, None)
                if box is not None and hasattr(box, "finish_manual_edit"):
                    box.finish_manual_edit(commit=False)
        self._active_page_key = page_key
        for frame in self.pages.values():
            frame.pack_forget()
        target = self.pages.get(page_key, self.pages["home"])
        target.pack(fill="both", expand=True)
        self.refresh_all()

    def _toggle_language(self) -> None:
        if getattr(self, "_in_language_toggle", False):
            return
        previous_lang = self.lang
        add_category = self._label_to_cat(self.add_cat_combo.get()) if hasattr(self, "add_cat_combo") else "COMPANY"
        filter_category = self._label_to_cat(self.filter_cat_combo.get()) if hasattr(self, "filter_cat_combo") else "ALL"
        previous_status = self.status_var.get()
        was_ready = previous_status == self._ready_status_text()
        sandbox_status = getattr(self, "_sandbox_status_texts", {})
        was_sandbox_status = previous_status == sandbox_status.get(previous_lang)
        self.lang = "en" if self.lang == "zh" else "zh"
        self._in_language_toggle = True
        try:
            self._refresh_translations(add_category, filter_category)
            self.sanitizer.set_language(self.lang)
        except Exception:
            self.lang = previous_lang
            try:
                self._refresh_translations(add_category, filter_category)
            except Exception:
                pass
            self.status_var.set(self._t("msg_operation_failed"))
            return
        finally:
            self._in_language_toggle = False
        if was_ready:
            self.status_var.set(self._ready_status_text())
        elif was_sandbox_status:
            self.status_var.set(sandbox_status[self.lang])
        if self.on_language_changed:
            self.on_language_changed()

    def _toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        try:
            self.sanitizer.set_theme(self.theme_mode)
        except OSError:
            self.theme_mode = "dark" if self.theme_mode == "light" else "light"
            self.status_var.set(self._t("msg_operation_failed"))
            return
        ctk.set_appearance_mode("Light" if self.theme_mode == "light" else "Dark")
        if hasattr(self, "btn_theme") and self.btn_theme.winfo_exists():
            self.btn_theme.configure(
                text=self._t("btn_theme_light")
                if self.theme_mode == "dark"
                else self._t("btn_theme_dark")
            )
        self._configure_sandbox_highlight_tag()

    def _on_dict_submode_selected(self, label: str) -> None:
        if len(self._dict_mode_labels) > 2 and label == self._dict_mode_labels[2]:
            mode = "regex"
        elif label == self._dict_mode_labels[1]:
            mode = "rules"
        else:
            mode = "words"
        self._show_dict_submode(mode)

    def _show_dict_submode(self, mode: str) -> None:
        self._dict_submode = mode
        self.dict_words_pane.pack_forget()
        self.dict_rules_pane.pack_forget()
        if hasattr(self, "dict_regex_pane"):
            self.dict_regex_pane.pack_forget()
        if mode == "rules":
            self.dict_rules_pane.pack(fill="both", expand=True)
            self.refresh_allowlist_and_rules_list()
        elif mode == "regex" and hasattr(self, "dict_regex_pane"):
            self.dict_regex_pane.pack(fill="both", expand=True)
            self.refresh_custom_regex_list()
            self._on_regex_live_test_changed()
        else:
            self.dict_words_pane.pack(fill="both", expand=True)
            self.refresh_dictionary_list()

    def refresh_all(self, *, check_startup: bool = False) -> None:
        if check_startup and hasattr(self, "var_startup") and platform.system() == "Windows":
            self.var_startup.set(is_startup_enabled())
        if hasattr(self, "var_auto_sanitize"):
            self.var_auto_sanitize.set(self.sanitizer.auto_sanitize_clipboard)
        if hasattr(self, "var_semantic_ip"):
            self.var_semantic_ip.set(self.sanitizer.semantic_ip_mode)
        if hasattr(self, "var_ai_hint"):
            self.var_ai_hint.set(self.sanitizer.ai_prompt_hint)
        if hasattr(self, "var_whole_word"):
            self.var_whole_word.set(self.sanitizer.custom_word_whole_word)
        if hasattr(self, "var_hud_enabled"):
            self.var_hud_enabled.set(self.sanitizer.hud_enabled)
        if hasattr(self, "var_clip_guard"):
            self.var_clip_guard.set(self.sanitizer.clipboard_privacy_guard)
        if hasattr(self, "var_entropy"):
            self.var_entropy.set(self.sanitizer.entropy_detection_enabled)
        if hasattr(self, "lbl_stat_hits"):
            self.lbl_stat_hits.configure(text=str(self.sanitizer.vault.total_intercepted_hits))
        if hasattr(self, "lbl_stat_vault"):
            self.lbl_stat_vault.configure(text=str(self.sanitizer.vault.size))
        if hasattr(self, "lbl_stat_rules"):
            active_r, total_r = self.sanitizer.active_rule_counts()
            self.lbl_stat_rules.configure(text=f"{active_r}/{total_r}")
        if hasattr(self, "combo_idle_wipe"):
            self.combo_idle_wipe.set(self._idle_label(self.sanitizer.idle_wipe_minutes))
        self._refresh_sidebar_status_label()
        self._refresh_hotkey_status_ui()
        self._refresh_recent_clipboard_card()
        self._update_idle_readout()

        if self._active_page_key == "dict":
            if self._dict_submode == "rules":
                self.refresh_allowlist_and_rules_list()
            elif self._dict_submode == "regex":
                self.refresh_custom_regex_list()
            else:
                self.refresh_dictionary_list()
        elif self._active_page_key == "vault":
            self.refresh_vault_list()

    def _schedule_rule_search_refresh(self) -> None:
        if self._rule_search_debounce_id is not None:
            try:
                self.root.after_cancel(self._rule_search_debounce_id)
            except Exception:
                pass
        self._rule_search_debounce_id = self.root.after(180, self.refresh_allowlist_and_rules_list)

    def _schedule_vault_search_refresh(self) -> None:
        self._vault_render_limit = _VAULT_PAGE_SIZE
        if self._vault_search_debounce_id is not None:
            try:
                self.root.after_cancel(self._vault_search_debounce_id)
            except Exception:
                pass
        self._vault_search_debounce_id = self.root.after(180, self.refresh_vault_list)

    def refresh_allowlist_and_rules_list(self) -> None:
        if self._rule_search_debounce_id is not None:
            try:
                self.root.after_cancel(self._rule_search_debounce_id)
            except Exception:
                pass
            self._rule_search_debounce_id = None
        if hasattr(self, "allowlist_scroll"):
            allow_items = list(self.sanitizer.get_allowlist())
            if allow_items != getattr(self, "_rendered_allowlist_items", None):
                for child in self.allowlist_scroll.winfo_children():
                    child.destroy()
                for idx, item in enumerate(allow_items, start=1):
                    row = ctk.CTkFrame(
                        self.allowlist_scroll,
                        fg_color=("#ffffff", "#1e293b"),
                        corner_radius=6,
                        height=30,
                    )
                    row.pack(fill="x", padx=4, pady=2)
                    # Pack delete button first so long allowlist values can never push it off-screen.
                    ctk.CTkButton(
                        row,
                        text="✕",
                        font=self.font_small,
                        width=26,
                        height=22,
                        corner_radius=6,
                        fg_color=("#fee2e2", "#7f1d1d"),
                        hover_color=("#fecaca", "#991b1b"),
                        text_color=("#991b1b", "#fecaca"),
                        command=lambda val=item: self._remove_allowlist_from_gui(val),
                    ).pack(side="right", padx=6, pady=4)
                    ctk.CTkLabel(
                        row,
                        text=f"#{idx}  {item}",
                        font=self.font_mono_sm,
                        anchor="w",
                        text_color=("#0f172a", "#f8fafc"),
                    ).pack(side="left", fill="x", expand=True, padx=8, pady=4)
                self._rendered_allowlist_items = allow_items

        if hasattr(self, "rules_toggle_scroll"):
            disabled_set = set(self.sanitizer.get_disabled_rules())
            query = self.rule_search_var.get().strip().lower() if hasattr(self, "rule_search_var") else ""
            is_zh = self.lang == "zh"
            matching_rules = []
            for rule in BUILTIN_RULES:
                friendly = (rule.label_zh if is_zh else rule.label_en) or rule.name
                if query and (
                    query not in friendly.lower()
                    and query not in rule.name.lower()
                    and query not in rule.category.lower()
                    and query not in rule.example.lower()
                ):
                    continue
                matching_rules.append((rule, friendly))

            target_names = [rule.name for rule, _ in matching_rules]
            cache = getattr(self, "_rule_row_cache", {})
            can_reuse = (
                target_names == getattr(self, "_rendered_rule_names", [])
                and len(cache) == len(target_names)
                and all(
                    name in cache and cache[name][0].winfo_exists()
                    for name in target_names
                )
            )
            if can_reuse:
                for rule, friendly in matching_rules:
                    chk, var_chk = cache[rule.name]
                    want_on = bool(rule.enabled_by_default and rule.name not in disabled_set)
                    if bool(var_chk.get()) != want_on:
                        var_chk.set(want_on)
                    new_lbl = f"[{rule.category}] {friendly}"
                    if chk.cget("text") != new_lbl:
                        chk.configure(text=new_lbl)
                return

            for child in self.rules_toggle_scroll.winfo_children():
                child.destroy()
            cache.clear()
            for rule, friendly in matching_rules:
                row = ctk.CTkFrame(
                    self.rules_toggle_scroll,
                    fg_color=("#ffffff", "#1e293b"),
                    corner_radius=8,
                )
                row.pack(fill="x", padx=4, pady=3)
                var_chk = tk.BooleanVar(
                    value=(rule.enabled_by_default and rule.name not in disabled_set)
                )
                chk = ctk.CTkCheckBox(
                    row,
                    text=f"[{rule.category}] {friendly}",
                    font=self.font_small,
                    variable=var_chk,
                    onvalue=True,
                    offvalue=False,
                    checkbox_width=16,
                    checkbox_height=16,
                    command=lambda rname=rule.name, v=var_chk: self._on_toggle_rule_checkbox(
                        rname, bool(v.get())
                    ),
                )
                chk.pack(anchor="w", padx=10, pady=(6, 1))
                cache[rule.name] = (chk, var_chk)
                if rule.example:
                    ctk.CTkLabel(
                        row,
                        text=f"    {rule.example}",
                        font=self.font_mono_sm,
                        text_color=("#64748b", "#94a3b8"),
                        anchor="w",
                    ).pack(anchor="w", padx=12, pady=(0, 5))
            self._rendered_rule_names = target_names

    def _apply_preset_from_gui(self, preset_name: str) -> None:
        active_r, total_r = self.sanitizer.apply_rule_preset(preset_name)
        self.refresh_allowlist_and_rules_list()
        if hasattr(self, "lbl_stat_rules"):
            self.lbl_stat_rules.configure(text=f"{active_r}/{total_r}")
        self.status_var.set(f"🎯 {preset_name.upper()} ({active_r}/{total_r})")

    def _add_allowlist_from_gui(self) -> None:
        raw = self.entry_allowlist.get().strip()
        if not raw:
            return
        candidates = [w.strip() for w in re.split(r"[,，;；\r\n]+", raw) if w.strip()]
        for c in candidates:
            self.sanitizer.add_allowlist_item(c)
        self.entry_allowlist.delete(0, "end")
        self._saved_entry_allowlist = ""
        self.refresh_allowlist_and_rules_list()

    def _remove_allowlist_from_gui(self, item: str) -> None:
        if self.sanitizer.remove_allowlist_item(item):
            self.refresh_allowlist_and_rules_list()

    def _on_toggle_rule_checkbox(self, rule_name: str, enabled: bool) -> None:
        self.sanitizer.set_rule_enabled(rule_name, enabled)
        if hasattr(self, "lbl_stat_rules"):
            active_r, total_r = self.sanitizer.active_rule_counts()
            self.lbl_stat_rules.configure(text=f"{active_r}/{total_r}")

    def refresh_dictionary_list(self) -> None:
        for child in self.dict_scroll.winfo_children():
            child.destroy()

        filter_cat = self._label_to_cat(self.filter_cat_combo.get())
        custom_dict = self.sanitizer.get_custom_dictionary()

        rows: List[tuple] = []
        if filter_cat == "ALL":
            for ck in CATEGORY_KEYS:
                for w in custom_dict.get(ck, []):
                    rows.append((ck, w))
        else:
            for w in custom_dict.get(filter_cat, []):
                rows.append((filter_cat, w))

        rows.sort(key=lambda item: len(item[1]), reverse=True)

        for idx, (cat_key, word) in enumerate(rows, start=1):
            row_card = ctk.CTkFrame(
                self.dict_scroll,
                fg_color=("#f8fafc", "#0f172a"),
                corner_radius=8,
                height=36,
            )
            row_card.pack(fill="x", padx=4, pady=2)

            ctk.CTkLabel(
                row_card,
                text=f"#{idx}",
                font=self.font_small,
                width=32,
                text_color=("#64748b", "#94a3b8"),
            ).pack(side="left", padx=(8, 4), pady=5)

            badge_color = CATEGORY_BADGE_COLORS.get(cat_key, ("#e2e8f0", "#334155"))
            ctk.CTkLabel(
                row_card,
                text=f" {cat_key} ",
                font=self.font_small,
                fg_color=badge_color,
                text_color=("#0f172a", "#f8fafc"),
                corner_radius=6,
                width=110,
            ).pack(side="left", padx=4, pady=5)

            ctk.CTkButton(
                row_card,
                text="✕",
                font=self.font_small,
                width=28,
                height=24,
                corner_radius=6,
                fg_color=("#fee2e2", "#7f1d1d"),
                hover_color=("#fecaca", "#991b1b"),
                text_color=("#991b1b", "#fecaca"),
                command=lambda c=cat_key, w=word: self._delete_single_word(c, w),
            ).pack(side="right", padx=8, pady=5)

            ctk.CTkLabel(
                row_card,
                text=word,
                font=self.font_body,
                anchor="w",
                text_color=("#0f172a", "#f8fafc"),
            ).pack(side="left", fill="x", expand=True, padx=8, pady=5)

    @staticmethod
    def _mask_secret(val: str) -> str:
        """Mask the middle of a sensitive string to prevent screen-share leaks (including short 3-4 char PINs)."""
        s = val.replace("\n", " ").strip()
        n = len(s)
        if n <= 4:
            return "•" * n
        if n <= 8:
            return f"{s[0]}{'•' * (n - 2)}{s[-1]}"
        return f"{s[:3]}••••••{s[-2:]}"

    @staticmethod
    def _mask_secret_preview(value: str) -> str:
        return _ModernControlCenter._mask_secret(value)

    def _on_toggle_reveal_vault(self) -> None:
        self._reveal_vault_originals = bool(self.var_reveal_vault.get())
        self.refresh_vault_list()

    def refresh_vault_list(self) -> None:
        if self._vault_search_debounce_id is not None:
            try:
                self.root.after_cancel(self._vault_search_debounce_id)
            except Exception:
                pass
            self._vault_search_debounce_id = None
        for child in self.vault_scroll.winfo_children():
            child.destroy()

        items = self.sanitizer.vault.snapshot_placeholders()
        keyword = self.vault_search_var.get().strip().lower() if hasattr(self, "vault_search_var") else ""

        filtered = [
            (ph, orig, cat)
            for ph, orig, cat in items
            if not keyword
            or keyword in ph.lower()
            or keyword in orig.lower()
            or keyword in cat.lower()
        ]

        if not filtered:
            ctk.CTkLabel(
                self.vault_scroll,
                text=self._format_hotkey_text(self._t("vault_empty")),
                font=self.font_body,
                wraplength=460,
                justify="center",
                text_color=("#64748b", "#94a3b8"),
            ).pack(padx=20, pady=40)
            return

        reveal = bool(self._reveal_vault_originals)
        palette_dark = RISK_TAG_STYLES["dark"]
        palette_light = RISK_TAG_STYLES["light"]
        visible = filtered[: self._vault_render_limit]

        for ph, orig, cat in visible:
            row_card = ctk.CTkFrame(
                self.vault_scroll,
                fg_color=("#f8fafc", "#0f172a"),
                corner_radius=8,
            )
            row_card.pack(fill="x", padx=4, pady=2)

            tier = RISK_TIERS.get(cat, "biz")
            l_bg, l_fg = palette_light[tier]
            d_bg, d_fg = palette_dark[tier]

            ctk.CTkLabel(
                row_card,
                text=f" {ph} ",
                font=self.font_mono_sm,
                fg_color=(l_bg, d_bg),
                text_color=(l_fg, d_fg),
                corner_radius=6,
                width=165,
            ).pack(side="left", padx=(8, 6), pady=6)

            ctk.CTkLabel(
                row_card,
                text=cat,
                font=self.font_small,
                width=92,
                text_color=("#64748b", "#94a3b8"),
            ).pack(side="left", padx=4, pady=6)

            if reveal:
                display_orig = orig if len(orig) <= 44 else orig[:41] + "..."
                display_orig = display_orig.replace("\n", " ")
            else:
                display_orig = self._mask_secret_preview(orig)

            ctk.CTkButton(
                row_card,
                text="✕",
                font=self.font_small,
                width=26,
                height=24,
                corner_radius=6,
                fg_color=("#fee2e2", "#7f1d1d"),
                hover_color=("#fecaca", "#991b1b"),
                text_color=("#991b1b", "#fecaca"),
                command=lambda p=ph: self._remove_single_vault_mapping(p),
            ).pack(side="right", padx=(4, 8), pady=5)

            self._localized_widget(
                ctk.CTkButton,
                row_card,
                translation_key="btn_copy_ph",
                font=self.font_small,
                width=72,
                height=24,
                corner_radius=6,
                fg_color=("#e2e8f0", "#334155"),
                hover_color=("#cbd5e1", "#475569"),
                text_color=("#0f172a", "#f8fafc"),
                command=lambda p=ph: self._copy_text(p),
            ).pack(side="right", padx=2, pady=5)

            ctk.CTkLabel(
                row_card,
                text=display_orig,
                font=self.font_mono_sm,
                anchor="w",
                text_color=("#0f172a", "#f8fafc"),
            ).pack(side="left", fill="x", expand=True, padx=6, pady=6)

        if len(filtered) > self._vault_render_limit:
            rem = len(filtered) - self._vault_render_limit
            ctk.CTkButton(
                self.vault_scroll,
                text=f"Load more (+{rem})" if self.lang == "en" else f"加载更多 (+{rem})",
                font=self.font_small,
                height=28,
                corner_radius=8,
                fg_color=("#e2e8f0", "#334155"),
                text_color=("#0f172a", "#f8fafc"),
                command=self._load_more_vault_rows,
            ).pack(pady=8)

    def _load_more_vault_rows(self) -> None:
        self._vault_render_limit += _VAULT_PAGE_SIZE
        self.refresh_vault_list()

    def _remove_single_vault_mapping(self, placeholder: str) -> None:
        if self.sanitizer.vault.remove_mapping(placeholder):
            if self.on_state_changed:
                self.on_state_changed()
            self.refresh_all()

    # ---------------- Actions ----------------

    def _add_word(self) -> None:
        raw_input = self.entry_new_word.get().strip()
        if not raw_input:
            return
        cat_key = self._label_to_cat(self.add_cat_combo.get())
        candidates = [w.strip() for w in re.split(r"[,，;；\r\n]+", raw_input) if w.strip()]
        added = 0
        for w in candidates:
            if self.sanitizer.add_custom_word(cat_key, w):
                added += 1
        self.entry_new_word.delete(0, "end")
        self._saved_entry_new_word = ""
        self.refresh_dictionary_list()
        if added > 0:
            self.status_var.set(f"✅ [{cat_key}] +{added}")

    def _delete_single_word(self, cat_key: str, word: str) -> None:
        if self.sanitizer.remove_custom_word(cat_key, word):
            self.refresh_dictionary_list()
            # Never echo the deleted secret word in plaintext on the status bar.
            self.status_var.set(f"{self._t('msg_word_removed')} [{cat_key}]")

    def _confirm_clear_all_custom_words(self) -> None:
        if messagebox.askyesno(
            self._t("confirm_clear_dict_title"),
            self._t("confirm_clear_dict_msg"),
            parent=self.root,
        ):
            self._clear_all_custom_words()

    def _clear_all_custom_words(self) -> None:
        self.sanitizer.clear_custom_dictionary()
        self.refresh_dictionary_list()
        self.status_var.set(self._t("msg_dict_cleared"))

    def _export_dictionary(self) -> None:
        if not messagebox.askokcancel("Export", self._t("msg_export_warning"), parent=self.root):
            return
        target = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".json",
            initialfile="ai-privacy-sanitizer-backup.local.json",
            filetypes=[("JSON", "*.json")],
        )
        if target:
            try:
                self.sanitizer.export_config(Path(target))
                self.status_var.set(self._t("msg_export_ok"))
            except OSError:
                messagebox.showerror("Export", self._t("msg_operation_failed"), parent=self.root)

    def _import_dictionary(self) -> None:
        source = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("JSON", "*.json")],
        )
        if source:
            try:
                self.sanitizer.import_config(Path(source), dictionary_only=True)
                self.refresh_all()
                # Never expose full local file paths (containing usernames) in the status bar.
                self.status_var.set(self._t("msg_import_ok"))
            except Exception:
                messagebox.showerror("Import", self._t("msg_operation_failed"), parent=self.root)

    def _export_encrypted_vault_from_gui(self) -> None:
        if self.sanitizer.vault.size == 0:
            self.status_var.set(self._format_hotkey_text(self._t("vault_empty")))
            return
        passphrase = simpledialog.askstring(
            self._t("prompt_passphrase_title"),
            self._t("prompt_passphrase_export"),
            show="•",
            parent=self.root,
        )
        if not passphrase:
            return
        target = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".vault.json",
            initialfile="sanitizer-session.vault.json",
            filetypes=[("Encrypted Vault JSON", "*.json")],
        )
        if target:
            try:
                self.sanitizer.vault.save_to_file(Path(target), passphrase=passphrase)
                self.status_var.set(self._t("msg_enc_vault_saved"))
            except Exception:
                messagebox.showerror("Vault", self._t("msg_operation_failed"), parent=self.root)

    def _import_encrypted_vault_from_gui(self) -> None:
        source = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("Vault JSON", "*.json")],
        )
        if not source:
            return
        passphrase = simpledialog.askstring(
            self._t("prompt_passphrase_title"),
            self._t("prompt_passphrase_import"),
            show="•",
            parent=self.root,
        )
        if passphrase is None:
            return
        try:
            self.sanitizer.vault.load_from_file(Path(source), passphrase=passphrase or None)
            if self.on_state_changed:
                self.on_state_changed()
            self.refresh_all()
            self.status_var.set(self._t("msg_enc_vault_loaded"))
        except Exception:
            messagebox.showerror("Vault", self._t("msg_operation_failed"), parent=self.root)

    def _sanitize_local_file_dialog(self) -> None:
        source = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[
                ("Text / Config / Logs", "*.env *.log *.txt *.json *.yaml *.yml *.csv *.ini *.conf *.py *.js *.ts"),
                ("All Files", "*.*"),
            ],
        )
        if not source:
            return
        src_path = Path(source)
        try:
            with src_path.open(encoding="utf-8", errors="replace") as stream:
                raw = stream.read(MAX_SANITIZE_CHARS + 1)
            if len(raw) > MAX_SANITIZE_CHARS:
                raise InputTooLargeError()
            res = self.sanitizer.sanitize(raw)
        except InputTooLargeError:
            self.status_var.set(self._t("notify_input_too_large"))
            messagebox.showwarning("Sanitizer", self._t("notify_input_too_large"), parent=self.root)
            return
        except OSError:
            messagebox.showerror("Sanitizer", self._t("msg_operation_failed"), parent=self.root)
            return

        suggested = f"{src_path.stem}.sanitized{src_path.suffix}"
        target = filedialog.asksaveasfilename(
            parent=self.root,
            initialdir=str(src_path.parent),
            initialfile=suggested,
        )
        if not target:
            return
        try:
            out_path = Path(target)
            if out_path.resolve() == src_path.resolve():
                raise ValueError("Output must differ from input")
            atomic_write_private(out_path, res.sanitized_text, overwrite=True)
            if self.on_state_changed:
                self.on_state_changed()
            self.refresh_all()
            self.status_var.set(f"{self._t('msg_file_sanitized')} · {res.format_summary(self.lang)}")
        except Exception:
            messagebox.showerror("Sanitizer", self._t("msg_operation_failed"), parent=self.root)

    def _restore_local_file_dialog(self) -> None:
        source = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[
                ("Text / Config / Logs", "*.env *.log *.txt *.json *.yaml *.yml *.csv *.ini *.conf *.py *.js *.ts"),
                ("All Files", "*.*"),
            ],
        )
        if not source:
            return
        src_path = Path(source)
        try:
            with src_path.open(encoding="utf-8", errors="replace") as stream:
                raw = stream.read(MAX_SANITIZE_CHARS + 1)
            if len(raw) > MAX_SANITIZE_CHARS:
                raise InputTooLargeError()
            res = self.sanitizer.restore(raw)
        except InputTooLargeError:
            self.status_var.set(self._t("notify_input_too_large"))
            return
        except OSError:
            messagebox.showerror("Sanitizer", self._t("msg_operation_failed"), parent=self.root)
            return

        suggested = f"{src_path.stem}.restored{src_path.suffix}"
        target = filedialog.asksaveasfilename(
            parent=self.root,
            initialdir=str(src_path.parent),
            initialfile=suggested,
        )
        if not target:
            return
        try:
            out_path = Path(target)
            if out_path.resolve() == src_path.resolve():
                raise ValueError("Output must differ from input")
            atomic_write_private(out_path, res.restored_text, overwrite=True)
            msg = res.format_summary(self.lang)
            if res.restored_count > 0:
                msg += " · " + self._t("msg_restore_warning")
            self.status_var.set(f"{self._t('msg_file_restored')} · {msg}")
        except Exception:
            messagebox.showerror("Sanitizer", self._t("msg_operation_failed"), parent=self.root)

    def _on_toggle_entropy(self) -> None:
        self.sanitizer.set_entropy_detection_enabled(bool(self.var_entropy.get()))

    def _on_drop_mode_selected(self, label: str) -> None:
        if hasattr(self, "_drop_mode_labels") and len(self._drop_mode_labels) > 1 and label == self._drop_mode_labels[1]:
            self._drop_mode = "restore"
        else:
            self._drop_mode = "sanitize"

    def _batch_folder_dialog(self) -> None:
        folder = filedialog.askdirectory(parent=self.root)
        if not folder:
            return
        self.handle_dropped_paths([Path(folder)], mode=self._drop_mode)

    def _open_batch_output_dir(self) -> None:
        out_path = getattr(self, "_last_batch_output_path", None)
        if out_path is None:
            return
        target = out_path if out_path.is_dir() else out_path.parent
        if not target.exists():
            return
        try:
            if platform.system() == "Windows":
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception:
            messagebox.showerror("Sanitizer", self._t("msg_operation_failed"), parent=self.root)

    def handle_dropped_paths(
        self, paths: Sequence[Path], mode: Optional[str] = None
    ) -> Optional[Any]:
        """Process dropped files or folders using shared SessionVault without overwriting sources."""
        active_mode = mode or getattr(self, "_drop_mode", "sanitize")
        try:
            batch_res = process_batch_paths(self.sanitizer, paths, mode=active_mode)
        except Exception:
            messagebox.showerror("Sanitizer", self._t("msg_operation_failed"), parent=self.root)
            return None

        self._last_batch_output_path = None
        if not batch_res.processed_files and not batch_res.skipped_files:
            msg = self._t("msg_batch_empty")
        elif not batch_res.processed_files:
            msg = self._t("msg_batch_empty")
        else:
            if len(batch_res.processed_files) == 1:
                dest_path = batch_res.processed_files[0][1]
                dest_label = dest_path.name
                self._last_batch_output_path = dest_path.parent
            else:
                dest_label = f"{batch_res.output_root.name}/"
                self._last_batch_output_path = batch_res.output_root
            msg = self._t("msg_batch_done").format(
                ok=len(batch_res.processed_files),
                hits=batch_res.total_hits,
                skip=len(batch_res.skipped_files),
                dest=dest_label,
            )
            if active_mode == "restore" and batch_res.total_hits > 0:
                msg += " · " + self._t("msg_restore_warning")

        self._saved_batch_status = msg
        if hasattr(self, "lbl_batch_result") and self.lbl_batch_result.winfo_exists():
            self.lbl_batch_result.configure(text=msg)
            self.lbl_batch_result.pack(anchor="w", fill="x", padx=10, pady=(0, 4))
        if hasattr(self, "btn_open_batch_out") and self.btn_open_batch_out.winfo_exists():
            if self._last_batch_output_path is not None:
                self.btn_open_batch_out.pack(anchor="w", padx=10, pady=(0, 6))
            else:
                self.btn_open_batch_out.pack_forget()
        if self.on_state_changed:
            self.on_state_changed()
        self.refresh_all()
        if hasattr(self, "status_var"):
            self.status_var.set(msg)
        return batch_res

    def _refresh_hotkey_status_ui(self) -> None:
        status_fn = getattr(self, "get_hotkey_status", None)
        if callable(status_fn):
            info = status_fn()
        else:
            hk = self.sanitizer.hotkeys
            info = {
                "state": "disabled" if platform.system() == "Darwin" else "ready",
                "conflict_key": None,
                "bound": dict(hk),
                "configured": dict(hk),
            }
        state = info.get("state", "ready")
        conflict = info.get("conflict_key")
        hk_active = info.get("bound") or info.get("configured") or self.sanitizer.hotkeys
        san_u = str(hk_active.get("sanitize", "alt+s")).upper()
        res_u = str(hk_active.get("restore", "alt+r")).upper()

        if state == "conflict":
            conflict_u = str(conflict or hk_active.get("restore", "alt+r")).upper()
            side_text = self._t("hk_status_side_conflict").format(key=conflict_u)
            home_text = self._t("hk_status_home_conflict").format(key=conflict_u)
            set_text = self._t("hk_status_settings_conflict").format(key=conflict_u)
            color = ("#d97706", "#fbbf24")
        elif state == "disabled":
            side_text = self._t("hk_status_side_disabled")
            home_text = self._t("hk_status_home_disabled")
            set_text = self._t("hk_status_settings_disabled")
            color = ("#64748b", "#94a3b8")
        else:
            side_text = self._t("hk_status_side_ready")
            home_text = self._t("hk_status_home_ready").format(san=san_u, res=res_u)
            set_text = self._t("hk_status_settings_ready").format(san=san_u, res=res_u)
            color = ("#059669", "#34d399")

        if hasattr(self, "lbl_side_hk_status") and self.lbl_side_hk_status.winfo_exists():
            self.lbl_side_hk_status.configure(text=side_text, text_color=color)
        if hasattr(self, "btn_side_hk_fix") and self.btn_side_hk_fix.winfo_exists():
            if state == "conflict":
                self.btn_side_hk_fix.pack(side="right", padx=(4, 0))
            else:
                self.btn_side_hk_fix.pack_forget()

        if hasattr(self, "lbl_home_hk_status") and self.lbl_home_hk_status.winfo_exists():
            self.lbl_home_hk_status.configure(text=home_text, text_color=color)
        if hasattr(self, "btn_home_hk_fix") and self.btn_home_hk_fix.winfo_exists():
            if state == "conflict":
                self.btn_home_hk_fix.pack(side="right", padx=(8, 0))
            else:
                self.btn_home_hk_fix.pack_forget()

        if hasattr(self, "lbl_settings_hk_status") and self.lbl_settings_hk_status.winfo_exists():
            self.lbl_settings_hk_status.configure(text=set_text, text_color=color)
        if hasattr(self, "btn_hk_autofix") and self.btn_hk_autofix.winfo_exists():
            if state == "conflict":
                self.btn_hk_autofix.pack(side="right", padx=(8, 10), pady=6)
            else:
                self.btn_hk_autofix.pack_forget()

    def _auto_fix_hotkeys_from_gui(self) -> None:
        fix_fn = getattr(self, "on_auto_fix_hotkeys", None)
        if not callable(fix_fn):
            self._reset_default_hotkeys()
            return
        ok, updated, _conflict = fix_fn()
        self._refresh_hotkey_labels()
        self._refresh_hotkey_status_ui()
        if ok:
            msg = (
                self._t("msg_hk_autofix_ok")
                .replace("{san}", updated["sanitize"].upper())
                .replace("{res}", updated["restore"].upper())
            )
            self.status_var.set(msg)
        else:
            err = self._t("msg_hk_autofix_fail")
            self.status_var.set(err)
            messagebox.showwarning("Hotkey", err, parent=self.root)

    def _on_toggle_recent_reveal(self) -> None:
        self._recent_reveal_originals = bool(self.var_recent_reveal.get())
        self._refresh_recent_clipboard_card()

    def _allowlist_and_rerun_from_recent(self, original_value: str) -> None:
        rerun_fn = getattr(self, "on_allowlist_and_rerun", None)
        if callable(rerun_fn):
            _ok, msg = rerun_fn(original_value)
            self.refresh_all()
            self.status_var.set(msg)
        elif self.sanitizer.add_allowlist_item(original_value):
            self.refresh_all()
            self.status_var.set(self._t("msg_allowlist_added"))

    def _refresh_recent_clipboard_card(self) -> None:
        if not hasattr(self, "home_recent_body") or not self.home_recent_body.winfo_exists():
            return

        getter = getattr(self, "get_last_clipboard_record", None)
        rec = getter() if callable(getter) else None
        if rec is None or not getattr(rec, "items", None):
            if hasattr(self, "lbl_recent_meta") and self.lbl_recent_meta.winfo_exists():
                self.lbl_recent_meta.configure(text="")
            if hasattr(self, "home_recent_items") and self.home_recent_items.winfo_exists():
                for child in self.home_recent_items.winfo_children():
                    child.destroy()
                self.home_recent_items.pack_forget()
            if hasattr(self, "lbl_recent_empty") and self.lbl_recent_empty.winfo_exists():
                self.lbl_recent_empty.configure(
                    text=self._format_hotkey_text(self._t("recent_clip_empty"))
                )
                if not self.lbl_recent_empty.winfo_manager():
                    self.lbl_recent_empty.pack(anchor="w", fill="x")
            return

        if hasattr(self, "lbl_recent_empty") and self.lbl_recent_empty.winfo_exists():
            self.lbl_recent_empty.pack_forget()
        if hasattr(self, "home_recent_items") and self.home_recent_items.winfo_exists():
            for child in self.home_recent_items.winfo_children():
                child.destroy()
            if not self.home_recent_items.winfo_manager():
                self.home_recent_items.pack(fill="x")

        src_key = "recent_src_cruise" if rec.source == "cruise" else "recent_src_hotkey"
        if hasattr(self, "lbl_recent_meta") and self.lbl_recent_meta.winfo_exists():
            self.lbl_recent_meta.configure(
                text=f"[{self._t(src_key)}] · {rec.total_count}"
            )

        preview_san = rec.sanitized_text.replace("\r", " ").replace("\n", " ")
        if len(preview_san) > 140:
            preview_san = preview_san[:137] + "..."
        ctk.CTkLabel(
            self.home_recent_items,
            text=preview_san,
            font=self.font_mono_sm,
            text_color=("#059669", "#34d399"),
            anchor="w",
            justify="left",
        ).pack(anchor="w", fill="x", pady=(0, 6))

        palette_light = RISK_TAG_STYLES["light"]
        palette_dark = RISK_TAG_STYLES["dark"]
        reveal = bool(self._recent_reveal_originals)
        for ph, orig, cat in rec.items[:6]:
            row = ctk.CTkFrame(
                self.home_recent_items,
                fg_color=("#f8fafc", "#0f172a"),
                corner_radius=8,
            )
            row.pack(fill="x", pady=2)

            tier = RISK_TIERS.get(cat, "biz")
            l_bg, l_fg = palette_light[tier]
            d_bg, d_fg = palette_dark[tier]

            ctk.CTkLabel(
                row,
                text=f" {ph} ",
                font=self.font_mono_sm,
                fg_color=(l_bg, d_bg),
                text_color=(l_fg, d_fg),
                corner_radius=6,
            ).pack(side="left", padx=(8, 6), pady=5)

            ctk.CTkButton(
                row,
                text=self._t("btn_allowlist_rerun"),
                font=self.font_small,
                width=148,
                height=24,
                corner_radius=6,
                fg_color=("#e2e8f0", "#334155"),
                hover_color=("#cbd5e1", "#475569"),
                text_color=("#0f172a", "#f8fafc"),
                command=lambda val=orig: self._allowlist_and_rerun_from_recent(val),
            ).pack(side="right", padx=8, pady=5)

            orig_disp = orig.replace("\n", " ") if reveal else self._mask_secret_preview(orig)
            if len(orig_disp) > 48:
                orig_disp = orig_disp[:45] + "..."
            ctk.CTkLabel(
                row,
                text=orig_disp,
                font=self.font_mono_sm,
                anchor="w",
                text_color=("#334155", "#cbd5e1"),
            ).pack(side="left", fill="x", expand=True, padx=4, pady=5)

    def _on_regex_live_test_changed(self) -> None:
        if not hasattr(self, "lbl_regex_test_result") or not self.lbl_regex_test_result.winfo_exists():
            return
        pat = self.entry_regex_pattern.get() if hasattr(self, "entry_regex_pattern") else ""
        sample = self.entry_regex_test.get() if hasattr(self, "entry_regex_test") else ""
        cat = self.entry_regex_cat.get() if hasattr(self, "entry_regex_cat") else "CUSTOM_REGEX"
        tpl = self.combo_regex_tpl.get() if hasattr(self, "combo_regex_tpl") else ALLOWED_PLACEHOLDER_TEMPLATES[0]

        if not pat.strip():
            self.lbl_regex_test_result.configure(
                text=self._t("regex_test_idle"),
                text_color=("#64748b", "#94a3b8"),
            )
            return
        res = self.sanitizer.test_custom_regex_rule(pat, sample, category=cat, placeholder_template=tpl)
        if not res.get("ok"):
            self.lbl_regex_test_result.configure(
                text=self._t("msg_regex_err").format(err=res.get("error", "invalid")),
                text_color=("#dc2626", "#f87171"),
            )
            return
        grp_txt = self._t("regex_test_partial") if res.get("target_group") else ""
        preview = str(res.get("sanitized", "")).replace("\n", " ")
        if len(preview) > 72:
            preview = preview[:69] + "..."
        self.lbl_regex_test_result.configure(
            text=self._t("regex_test_ok").format(
                ms=res.get("elapsed_ms", 0),
                cnt=len(res.get("matches", [])),
                grp=grp_txt,
                preview=preview or "-",
            ),
            text_color=("#059669", "#34d399"),
        )

    def _add_custom_regex_from_gui(self) -> None:
        name = self.entry_regex_name.get().strip()
        pat = self.entry_regex_pattern.get()
        cat = sanitize_category_name(self.entry_regex_cat.get())
        tpl = self.combo_regex_tpl.get()
        try:
            added = self.sanitizer.add_custom_regex_rule(
                name=name,
                pattern=pat,
                category=cat,
                placeholder_template=tpl,
                enabled=True,
            )
        except (RegexSafetyError, ValueError) as exc:
            err_msg = self._t("msg_regex_err").format(err=str(exc))
            if hasattr(self, "lbl_regex_test_result") and self.lbl_regex_test_result.winfo_exists():
                self.lbl_regex_test_result.configure(text=err_msg, text_color=("#dc2626", "#f87171"))
            self.status_var.set(err_msg)
            messagebox.showwarning("Regex", err_msg, parent=self.root)
            return
        self.entry_regex_name.delete(0, "end")
        self.entry_regex_pattern.delete(0, "end")
        self._saved_regex_name = ""
        self._saved_regex_pattern = ""
        self.refresh_custom_regex_list()
        self._on_regex_live_test_changed()
        self.status_var.set(self._t("msg_regex_added").format(cat=added["category"], name=added["name"]))

    def _toggle_custom_regex_from_gui(self, name: str, enabled: bool) -> None:
        self.sanitizer.set_custom_regex_rule_enabled(name, enabled)

    def _remove_custom_regex_from_gui(self, name: str) -> None:
        if self.sanitizer.remove_custom_regex_rule(name):
            self.refresh_custom_regex_list()
            self.status_var.set(self._t("msg_regex_removed"))

    def refresh_custom_regex_list(self) -> None:
        if not hasattr(self, "custom_regex_scroll") or not self.custom_regex_scroll.winfo_exists():
            return
        for child in self.custom_regex_scroll.winfo_children():
            child.destroy()

        rules = self.sanitizer.get_custom_regex_rules()
        if not rules:
            ctk.CTkLabel(
                self.custom_regex_scroll,
                text=self._t("regex_empty"),
                font=self.font_small,
                text_color=("#64748b", "#94a3b8"),
                wraplength=460,
                justify="center",
            ).pack(padx=20, pady=28)
            return

        for rule in rules:
            row = ctk.CTkFrame(
                self.custom_regex_scroll,
                fg_color=("#f8fafc", "#0f172a"),
                corner_radius=8,
            )
            row.pack(fill="x", padx=4, pady=3)

            ctk.CTkButton(
                row,
                text="✕",
                font=self.font_small,
                width=26,
                height=24,
                corner_radius=6,
                fg_color=("#fee2e2", "#7f1d1d"),
                hover_color=("#fecaca", "#991b1b"),
                text_color=("#991b1b", "#fecaca"),
                command=lambda rname=rule["name"]: self._remove_custom_regex_from_gui(rname),
            ).pack(side="right", padx=8, pady=6)

            var_en = tk.BooleanVar(value=bool(rule.get("enabled", True)))
            ctk.CTkCheckBox(
                row,
                text=f"[{rule['category']}] {rule['name']}",
                font=self.font_small,
                variable=var_en,
                onvalue=True,
                offvalue=False,
                checkbox_width=16,
                checkbox_height=16,
                command=lambda rname=rule["name"], v=var_en: self._toggle_custom_regex_from_gui(
                    rname, bool(v.get())
                ),
            ).pack(side="left", padx=(10, 8), pady=6)

            pat_disp = rule["pattern"]
            if len(pat_disp) > 52:
                pat_disp = pat_disp[:49] + "..."
            ctk.CTkLabel(
                row,
                text=pat_disp,
                font=self.font_mono_sm,
                text_color=("#64748b", "#94a3b8"),
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=4, pady=6)

    def _on_toggle_startup(self) -> None:
        desired = bool(self.var_startup.get())
        if not set_startup_enabled(desired):
            self.var_startup.set(is_startup_enabled())

    def _on_toggle_auto_sanitize(self) -> None:
        self.sanitizer.set_auto_sanitize_clipboard(bool(self.var_auto_sanitize.get()))
        self._refresh_sidebar_status_label()
        if self.on_state_changed:
            self.on_state_changed()

    def _on_toggle_semantic_ip(self) -> None:
        self.sanitizer.set_semantic_ip_mode(bool(self.var_semantic_ip.get()))

    def _on_toggle_ai_hint(self) -> None:
        self.sanitizer.set_ai_prompt_hint(bool(self.var_ai_hint.get()))

    def _on_toggle_whole_word(self) -> None:
        self.sanitizer.set_custom_word_whole_word(bool(self.var_whole_word.get()))

    def _on_toggle_hud(self) -> None:
        self.sanitizer.set_hud_enabled(bool(self.var_hud_enabled.get()))

    def _on_toggle_clip_guard(self) -> None:
        self.sanitizer.set_clipboard_privacy_guard(bool(self.var_clip_guard.get()))

    def _on_idle_wipe_selected(self, label: str) -> None:
        minutes = self._label_to_idle_minutes(label)
        self.sanitizer.set_idle_wipe_minutes(minutes)
        self._update_idle_readout()

    def _on_toggle_sandbox_isolate(self) -> None:
        self._sandbox_isolate = bool(self.var_sandbox_isolate.get())

    def _sync_sandbox_to_global_vault(self) -> None:
        merged = self.sanitizer.vault.merge_from(self._sandbox_vault)
        if self.on_state_changed:
            self.on_state_changed()
        self.refresh_all()
        self.status_var.set(f"{self._t('msg_sandbox_synced')} (+{merged})")

    def _cancel_hotkey_recording(self) -> None:
        self._recording_target = None
        for seq in ("<KeyPress>", "<KeyRelease>"):
            try:
                self.root.unbind(seq)
            except Exception:
                pass
        if hasattr(self, "combo_hk_sanitize") and hasattr(self.combo_hk_sanitize, "set_recording"):
            self.combo_hk_sanitize.set_recording(False)
        if hasattr(self, "combo_hk_restore") and hasattr(self.combo_hk_restore, "set_recording"):
            self.combo_hk_restore.set_recording(False)
        if hasattr(self, "btn_rec_san"):
            self.btn_rec_san.configure(text=self._t("btn_hk_record"))
        if hasattr(self, "btn_rec_res"):
            self.btn_rec_res.configure(text=self._t("btn_hk_record"))

    def _update_edit_button_visual(self, target: str, editing: bool) -> None:
        attr = "btn_edit_san" if target == "sanitize" else "btn_edit_res"
        btn = getattr(self, attr, None)
        if btn is None:
            return
        try:
            if not btn.winfo_exists():
                return
        except Exception:
            return
        if editing:
            btn.configure(
                text="✓",
                fg_color=("#059669", "#059669"),
                hover_color=("#047857", "#047857"),
                text_color="#ffffff",
            )
        else:
            btn.configure(
                text="✏️",
                fg_color=("#e2e8f0", "#334155"),
                hover_color=("#cbd5e1", "#475569"),
                text_color=("#0f172a", "#f8fafc"),
            )

    def _toggle_manual_hotkey_edit(self, target: str) -> None:
        if platform.system() == "Darwin":
            self.status_var.set(self._t("macos_preview_hotkeys"))
            return
        if getattr(self, "_recording_target", None) is not None:
            self._cancel_hotkey_recording()
        box = self.combo_hk_sanitize if target == "sanitize" else self.combo_hk_restore
        other = self.combo_hk_restore if target == "sanitize" else self.combo_hk_sanitize
        if getattr(box, "_editing", False):
            typed = box._entry.get().strip().lower()
            if not typed:
                box.finish_manual_edit(commit=False)
                self.status_var.set(self._t("msg_hk_cancelled"))
            else:
                self._save_and_apply_hotkeys()
            return
        if hasattr(other, "finish_manual_edit"):
            other.finish_manual_edit(commit=False)
        if hasattr(box, "start_manual_edit"):
            box.start_manual_edit()
            if getattr(box, "_editing", False):
                self.status_var.set(self._t("hk_box_edit_hint"))

    def _start_hotkey_recording(self, target: str) -> None:
        if platform.system() == "Darwin":
            self.status_var.set(self._t("macos_preview_hotkeys"))
            return
        if self._recording_target == target:
            self._cancel_hotkey_recording()
            self.status_var.set(self._t("msg_hk_cancelled"))
            return
        self._cancel_hotkey_recording()
        for box in (self.combo_hk_sanitize, self.combo_hk_restore):
            if hasattr(box, "finish_manual_edit"):
                box.finish_manual_edit(commit=False)
        self._recording_target = target
        if target == "sanitize":
            self.btn_rec_san.configure(text=self._t("btn_hk_recording"))
            if hasattr(self.combo_hk_sanitize, "set_recording"):
                self.combo_hk_sanitize.set_recording(True)
        else:
            self.btn_rec_res.configure(text=self._t("btn_hk_recording"))
            if hasattr(self.combo_hk_restore, "set_recording"):
                self.combo_hk_restore.set_recording(True)
        self.root.bind("<KeyPress>", self._on_hotkey_keypress)
        self.root.bind("<KeyRelease>", self._on_hotkey_keyrelease)
        self.root.focus_force()

    def _on_hotkey_keyrelease(self, event: tk.Event) -> str:
        if not self._recording_target:
            return "break"
        mods, _token, _is_pure = normalize_tk_key_event(event)
        keysym = str(getattr(event, "keysym", "") or "")
        released_mod = _PURE_MODIFIER_KEYSYMS.get(keysym) or _PURE_MODIFIER_VKS.get(int(getattr(event, "keycode", 0) or 0))
        if released_mod and released_mod in mods:
            mods = [m for m in mods if m != released_mod]
        box = self.combo_hk_sanitize if self._recording_target == "sanitize" else self.combo_hk_restore
        if hasattr(box, "set_recording"):
            preview = (" + ".join(m.upper() for m in mods) + " + ...") if mods else ""
            box.set_recording(True, preview=preview)
        return "break"

    def _on_hotkey_keypress(self, event: tk.Event) -> str:
        if not self._recording_target:
            return "break"
        keysym = str(getattr(event, "keysym", "") or "")
        keycode = int(getattr(event, "keycode", 0) or 0)
        # Pressing Esc cancels recording instead of hijacking Escape globally!
        if keysym.lower() in ("escape", "esc") or keycode == 0x1B:
            self._cancel_hotkey_recording()
            self.status_var.set(self._t("msg_hk_cancelled"))
            return "break"

        mods, key_token, is_pure_mod = normalize_tk_key_event(event)
        box = self.combo_hk_sanitize if self._recording_target == "sanitize" else self.combo_hk_restore
        if is_pure_mod or not key_token:
            if hasattr(box, "set_recording") and mods:
                box.set_recording(True, preview=" + ".join(m.upper() for m in mods) + " + ...")
            return "break"

        # Reject bare non-function keys so users cannot accidentally bind 'a' or 'space' globally.
        if not mods and not re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key_token):
            self.status_var.set(self._t("msg_hk_modifier_required"))
            return "break"

        combo_str = "+".join(mods + [key_token])
        target = self._recording_target
        self._cancel_hotkey_recording()

        if target == "sanitize":
            self.combo_hk_sanitize.set(combo_str)
        else:
            self.combo_hk_restore.set(combo_str)
        self._save_and_apply_hotkeys()
        return "break"

    def _save_and_apply_hotkeys(self) -> None:
        if platform.system() == "Darwin":
            self.status_var.set(self._t("macos_preview_hotkeys"))
            return
        san_val = self.combo_hk_sanitize.get().strip().lower()
        res_val = self.combo_hk_restore.get().strip().lower()
        if getattr(self, "_recording_target", None) is not None:
            self._cancel_hotkey_recording()
        try:
            candidate = self.sanitizer.normalize_hotkeys(san_val, res_val)
            if self.on_reload_hotkeys:
                if not self.on_reload_hotkeys(candidate):
                    conflict_getter = getattr(self, "get_last_hotkey_conflict", None)
                    conflict = conflict_getter() if callable(conflict_getter) else None
                    err_text = (
                        self._t("msg_hk_occupied").replace("{key}", str(conflict).upper())
                        if conflict
                        else self._t("msg_hk_err")
                    )
                    for box in (self.combo_hk_sanitize, self.combo_hk_restore):
                        if hasattr(box, "finish_manual_edit"):
                            box.finish_manual_edit(commit=False)
                    self._sync_hotkey_inputs()
                    self._refresh_hotkey_status_ui()
                    self.status_var.set(err_text)
                    messagebox.showwarning("Hotkey", err_text, parent=self.root)
                    return
            else:
                self.sanitizer.set_hotkeys(candidate["sanitize"], candidate["restore"])
            for box in (self.combo_hk_sanitize, self.combo_hk_restore):
                if hasattr(box, "finish_manual_edit"):
                    box.finish_manual_edit(commit=True)
            updated = self.sanitizer.hotkeys
            self._refresh_hotkey_labels()
            msg = (
                self._t("msg_hk_saved")
                .replace("{san}", updated["sanitize"].upper())
                .replace("{res}", updated["restore"].upper())
            )
            self.status_var.set(msg)
        except HotkeyRollbackError:
            for box in (self.combo_hk_sanitize, self.combo_hk_restore):
                if hasattr(box, "finish_manual_edit"):
                    box.finish_manual_edit(commit=False)
            self._sync_hotkey_inputs()
            self.status_var.set(self._t("msg_hk_rollback_err"))
            messagebox.showwarning("Hotkey", self._t("msg_hk_rollback_err"), parent=self.root)
        except Exception:
            for box in (self.combo_hk_sanitize, self.combo_hk_restore):
                if hasattr(box, "finish_manual_edit"):
                    box.finish_manual_edit(commit=False)
            self._sync_hotkey_inputs()
            self.status_var.set(self._t("msg_hk_err"))
            messagebox.showwarning("Hotkey", self._t("msg_hk_err"), parent=self.root)

    def _sync_hotkey_inputs(self) -> None:
        hk = self.sanitizer.hotkeys
        if hasattr(self, "combo_hk_sanitize") and not getattr(self.combo_hk_sanitize, "_recording", False):
            self.combo_hk_sanitize.set(hk.get("sanitize", "alt+s"))
        if hasattr(self, "combo_hk_restore") and not getattr(self.combo_hk_restore, "_recording", False):
            self.combo_hk_restore.set(hk.get("restore", "alt+r"))

    def _reset_default_hotkeys(self) -> None:
        if platform.system() == "Darwin":
            self.status_var.set(self._t("macos_preview_hotkeys"))
            return
        if getattr(self, "_recording_target", None) is not None:
            self._cancel_hotkey_recording()
        for box in (self.combo_hk_sanitize, self.combo_hk_restore):
            if hasattr(box, "finish_manual_edit"):
                box.finish_manual_edit(commit=False)
        if not self.on_reload_hotkeys:
            self.combo_hk_sanitize.set("alt+s")
            self.combo_hk_restore.set("alt+r")
            self._save_and_apply_hotkeys()
            return

        conflict_getter = getattr(self, "get_last_hotkey_conflict", None)
        first_conflict: Optional[str] = None
        for idx, (san_cand, res_cand) in enumerate(_DEFAULT_HOTKEY_CANDIDATES):
            try:
                ok = bool(self.on_reload_hotkeys({"sanitize": san_cand, "restore": res_cand}))
            except HotkeyRollbackError:
                self._sync_hotkey_inputs()
                self.status_var.set(self._t("msg_hk_rollback_err"))
                messagebox.showwarning("Hotkey", self._t("msg_hk_rollback_err"), parent=self.root)
                return
            if ok:
                self._refresh_hotkey_labels()
                updated = self.sanitizer.hotkeys
                if idx == 0:
                    msg = (
                        self._t("msg_hk_saved")
                        .replace("{san}", updated["sanitize"].upper())
                        .replace("{res}", updated["restore"].upper())
                    )
                else:
                    msg = (
                        self._t("msg_hk_reset_fallback")
                        .replace("{conflict}", (first_conflict or "alt+r").upper())
                        .replace("{san}", updated["sanitize"].upper())
                        .replace("{res}", updated["restore"].upper())
                    )
                self.status_var.set(msg)
                return
            if idx == 0 and callable(conflict_getter):
                first_conflict = conflict_getter()

        self._sync_hotkey_inputs()
        err_text = (
            self._t("msg_hk_occupied").replace("{key}", str(first_conflict).upper())
            if first_conflict
            else self._t("msg_hk_err")
        )
        self.status_var.set(err_text)
        messagebox.showwarning("Hotkey", err_text, parent=self.root)

    def _refresh_hotkey_labels(self) -> None:
        self._sync_hotkey_inputs()
        if hasattr(self, "btn_hero_san"):
            self.btn_hero_san.configure(
                text=self._format_hotkey_text(self._t("btn_hero_sanitize"))
            )
        if hasattr(self, "btn_hero_res"):
            self.btn_hero_res.configure(
                text=self._format_hotkey_text(self._t("btn_hero_restore"))
            )
        if hasattr(self, "lbl_workflow"):
            self.lbl_workflow.configure(
                text=self._format_hotkey_text(f"{self._t('workflow_title')}：{self._t('workflow_steps')}")
            )
        if hasattr(self, "lbl_side_status"):
            self._refresh_sidebar_status_label()
        self._refresh_hotkey_status_ui()
        if hasattr(self, "vault_scroll") and self.sanitizer.vault.size == 0:
            self.refresh_vault_list()
        if hasattr(self, "guide_box"):
            position = self.guide_box.yview()[0]
            self.guide_box.configure(state="normal")
            self.guide_box.delete("1.0", "end")
            self.guide_box.insert("1.0", self._guide_text())
            self._style_guide_headings()
            self.guide_box.configure(state="disabled")
            self.guide_box.yview_moveto(position)
        if hasattr(self, "guide_step_descs"):
            for d_key, lbl_d in self.guide_step_descs:
                if lbl_d.winfo_exists():
                    lbl_d.configure(text=self._format_hotkey_text(self._t(d_key)))
        if hasattr(self, "btn_guide_faq") and self.btn_guide_faq.winfo_exists():
            self.btn_guide_faq.configure(
                text=self._t("guide_faq_hide" if getattr(self, "_guide_faq_open", False) else "guide_faq_show")
            )
        if not getattr(self, "_in_language_toggle", False) and getattr(self, "_last_layout_logical_w", 0) > 0:
            if hasattr(self, "lbl_workflow"):
                self.lbl_workflow._aps_last_wrap = None
            if hasattr(self, "home_btn_row"):
                self.home_btn_row.update_idletasks()
            self._apply_responsive_layout(self._last_layout_logical_w, force=True)

    def _highlight_placeholders_in_output(self) -> None:
        inner_text = getattr(self.sandbox_output, "_textbox", None)
        if inner_text is None:
            return
        for tag in ("placeholder_tag", "tier_api", "tier_pass", "tier_pii", "tier_net", "tier_biz"):
            inner_text.tag_remove(tag, "1.0", "end")
        vault = self._active_sandbox_vault()
        for ph, _orig, cat in vault.snapshot_placeholders():
            tier_tag = f"tier_{RISK_TIERS.get(cat, 'biz')}"
            start_idx = "1.0"
            while True:
                pos = inner_text.search(ph, start_idx, stopindex="end", exact=True)
                if not pos:
                    break
                end_pos = f"{pos}+{len(ph)}c"
                inner_text.tag_add("placeholder_tag", pos, end_pos)
                inner_text.tag_add(tier_tag, pos, end_pos)
                start_idx = end_pos

    def _on_sandbox_input_changed(self, _event=None) -> None:
        if self._sandbox_debounce_id is not None:
            try:
                self.root.after_cancel(self._sandbox_debounce_id)
            except Exception:
                pass
        self._sandbox_debounce_id = self.root.after(260, self._run_sandbox_sanitize)

    def _load_sample_into_sandbox(self) -> None:
        self.sandbox_input.delete("1.0", "end")
        self.sandbox_input.insert("1.0", SAMPLE_TEST_PAYLOAD.strip())
        self._run_sandbox_sanitize()

    def _render_sandbox_category_pills(self, category_counts: Dict[str, int]) -> None:
        if not hasattr(self, "sandbox_cat_inner"):
            return
        for child in self.sandbox_cat_inner.winfo_children():
            child.destroy()

        if not category_counts:
            self._localized_widget(
                ctk.CTkLabel,
                self.sandbox_cat_inner,
                translation_key="sandbox_cat_empty",
                font=self.font_small,
                text_color=("#64748b", "#94a3b8"),
            ).pack(side="left")
            return

        # Wrap category pills cleanly across multiple rows (max 5 pills per row) so nothing clips!
        items = sorted(category_counts.items())
        pills_per_row = 5
        palette_light = RISK_TAG_STYLES["light"]
        palette_dark = RISK_TAG_STYLES["dark"]
        for row_idx in range(0, len(items), pills_per_row):
            row_frame = ctk.CTkFrame(self.sandbox_cat_inner, fg_color="transparent")
            row_frame.pack(fill="x", pady=1)
            if row_idx == 0:
                self._localized_widget(
                    ctk.CTkLabel,
                    row_frame,
                    translation_key="sandbox_cat_prefix",
                    font=self.font_small,
                    text_color=("#0f172a", "#f8fafc"),
                ).pack(side="left", padx=(0, 6))
            for cat, cnt in items[row_idx : row_idx + pills_per_row]:
                tier = RISK_TIERS.get(cat, "biz")
                l_bg, l_fg = palette_light[tier]
                d_bg, d_fg = palette_dark[tier]
                ctk.CTkLabel(
                    row_frame,
                    text=f" {cat}: {cnt} ",
                    font=self.font_small,
                    fg_color=(l_bg, d_bg),
                    text_color=(l_fg, d_fg),
                    corner_radius=6,
                ).pack(side="left", padx=3, pady=1)

    def _run_sandbox_sanitize(self) -> None:
        raw = self.sandbox_input.get("1.0", "end").rstrip("\n")
        self._sandbox_debounce_id = None
        use_isolated = getattr(self, "_sandbox_isolate", False) and getattr(self, "_sandbox_vault", None) is not None
        target_vault = SessionVault() if use_isolated else None
        try:
            res = self.sanitizer.sanitize(raw, vault=target_vault)
        except InputTooLargeError:
            self.sandbox_output.delete("1.0", "end")
            self._saved_sandbox_output = ""
            self._saved_sandbox_cat_counts = {}
            self._render_sandbox_category_pills({})
            self.status_var.set(self._t("notify_input_too_large"))
            return
        if use_isolated and target_vault is not None:
            self._sandbox_vault = target_vault
        self.sandbox_output.delete("1.0", "end")
        self.sandbox_output.insert("1.0", res.sanitized_text)
        self._saved_sandbox_input = raw
        self._saved_sandbox_output = res.sanitized_text
        self._saved_sandbox_cat_counts = dict(res.category_counts)
        self._highlight_placeholders_in_output()
        self._render_sandbox_category_pills(res.category_counts)
        if not use_isolated:
            if self.on_state_changed:
                self.on_state_changed()
            self.refresh_all()
        self._sandbox_status_texts = {lang: res.format_summary(lang) for lang in ("zh", "en")}
        self.status_var.set(self._sandbox_status_texts[self.lang])

    def _run_sandbox_restore(self) -> None:
        sanitized = self.sandbox_output.get("1.0", "end").rstrip("\n")
        if not sanitized.strip():
            sanitized = self.sandbox_input.get("1.0", "end").rstrip("\n")
        use_isolated = getattr(self, "_sandbox_isolate", False) and getattr(self, "_sandbox_vault", None) is not None
        try:
            if use_isolated and self._sandbox_vault.size > 0:
                res = self.sanitizer.restore(sanitized, vault=self._sandbox_vault)
                if res.restored_count == 0 and self.sanitizer.vault.size > 0:
                    res = self.sanitizer.restore(sanitized)
            else:
                res = self.sanitizer.restore(sanitized)
        except InputTooLargeError:
            self.status_var.set(self._t("notify_input_too_large"))
            return
        self.sandbox_output.delete("1.0", "end")
        self.sandbox_output.insert("1.0", res.restored_text)
        self._saved_sandbox_output = res.restored_text
        if res.restored_count > 0:
            self._sandbox_status_texts = {
                lang: res.format_summary(lang) + " · " + tr(lang, "msg_restore_warning")
                for lang in ("zh", "en")
            }
        else:
            self._sandbox_status_texts = {lang: res.format_summary(lang) for lang in ("zh", "en")}
        self.status_var.set(self._sandbox_status_texts[self.lang])

    def _copy_sandbox_output(self) -> None:
        out = self.sandbox_output.get("1.0", "end-1c")
        if out.strip():
            self._copy_text(out)

    def _clear_sandbox(self) -> None:
        if self._sandbox_debounce_id is not None:
            try:
                self.root.after_cancel(self._sandbox_debounce_id)
            except Exception:
                pass
            self._sandbox_debounce_id = None
        self.sandbox_input.delete("1.0", "end")
        self.sandbox_output.delete("1.0", "end")
        if getattr(self, "_sandbox_vault", None) is not None:
            self._sandbox_vault.clear()
        self._saved_sandbox_input = ""
        self._saved_sandbox_output = ""
        self._saved_sandbox_cat_counts = {}
        self._render_sandbox_category_pills({})

    def _copy_text(self, text: str, *, conceal: bool = False) -> None:
        if getattr(self, "on_copy_to_clipboard", None) is not None:
            if self.on_copy_to_clipboard(text, conceal=conceal):
                self.status_var.set(self._t("msg_copied"))
                return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(self._t("msg_copied"))

    def _confirm_clear_vault_from_gui(self) -> None:
        if self.sanitizer.vault.size == 0:
            self._clear_vault_from_gui()
            return
        if messagebox.askyesno(
            self._t("confirm_clear_vault_title"),
            self._t("confirm_clear_vault_msg"),
            parent=self.root,
        ):
            self._clear_vault_from_gui()

    def _clear_vault_from_gui(self) -> None:
        if self.on_clear_session:
            self.on_clear_session()
        else:
            self.sanitizer.clear_session()
        self.refresh_all()
        lang = getattr(self, "lang", "zh")
        self.status_var.set(tr(lang, "msg_vault_cleared_status"))

    def _trigger_sanitize_clipboard(self) -> None:
        if self.on_sanitize_clipboard:
            self.on_sanitize_clipboard()
        self.refresh_all()

    def _trigger_restore_clipboard(self) -> None:
        if self.on_restore_clipboard:
            self.on_restore_clipboard()
        self.refresh_all()

    def _trigger_undo_sanitize(self) -> None:
        if self.on_undo_sanitize:
            self.on_undo_sanitize()
        self.refresh_all()

    def _trigger_exit_app(self) -> None:
        self.detach_drop_target()
        if self.on_exit_app:
            self.on_exit_app()
        else:
            self.root.quit()
            self.root.destroy()

    def present(self) -> None:
        self.refresh_all(check_startup=True)
        self.root.deiconify()
        try:
            self.root.state("normal")
        except Exception:
            pass
        self._ensure_drop_target_attached()
        self.root.lift()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(180, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()
