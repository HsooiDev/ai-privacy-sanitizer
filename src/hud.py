"""Lightweight non-focus-stealing bottom-right Micro-HUD toast for desktop feedback."""

import ctypes
import platform
import tkinter as tk
from typing import Optional

import customtkinter as ctk


class FloatingMicroHud:
    """Brief floating pill notification that never steals focus from the active editor."""

    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._window: Optional[ctk.CTkToplevel] = None
        self._title_lbl: Optional[ctk.CTkLabel] = None
        self._body_lbl: Optional[ctk.CTkLabel] = None
        self._hide_timer: Optional[str] = None

    def show(self, title: str, message: str, *, duration_ms: int = 2400, tone: str = "info") -> None:
        """Display or update the Micro-HUD without taking input focus."""
        try:
            if not self._root.winfo_exists():
                return
        except tk.TclError:
            return

        if self._hide_timer is not None:
            try:
                self._root.after_cancel(self._hide_timer)
            except tk.TclError:
                pass
            self._hide_timer = None

        accent_map = {
            "success": ("#059669", "#34d399"),
            "warning": ("#d97706", "#fbbf24"),
            "error": ("#dc2626", "#f87171"),
            "info": ("#2563eb", "#60a5fa"),
        }
        accent = accent_map.get(tone, accent_map["info"])

        try:
            if self._window is None or not self._window.winfo_exists():
                win = ctk.CTkToplevel(self._root)
                win.withdraw()
                win.overrideredirect(True)
                try:
                    win.attributes("-topmost", True)
                except tk.TclError:
                    pass
                card = ctk.CTkFrame(
                    win,
                    fg_color=("#ffffff", "#131c31"),
                    corner_radius=12,
                    border_width=2,
                    border_color=accent,
                )
                card.pack(fill="both", expand=True, padx=2, pady=2)
                self._card = card
                self._title_lbl = ctk.CTkLabel(
                    card,
                    text=title,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=accent,
                    anchor="w",
                )
                self._title_lbl.pack(fill="x", padx=14, pady=(10, 2))
                self._body_lbl = ctk.CTkLabel(
                    card,
                    text=message,
                    font=ctk.CTkFont(size=11),
                    text_color=("#334155", "#cbd5e1"),
                    anchor="w",
                    wraplength=310,
                    justify="left",
                )
                self._body_lbl.pack(fill="x", padx=14, pady=(0, 10))
                self._window = win
            else:
                self._card.configure(border_color=accent)
                self._title_lbl.configure(text=title, text_color=accent)
                self._body_lbl.configure(text=message)

            self._window.update_idletasks()
            w = max(260, min(360, self._window.winfo_reqwidth()))
            h = max(64, self._window.winfo_reqheight())
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()
            x = max(16, sw - w - 24)
            y = max(16, sh - h - 68)
            self._window.geometry(f"{w}x{h}+{x}+{y}")
            self._window.deiconify()
            self._apply_windows_no_activate()
            self._hide_timer = self._root.after(duration_ms, self.hide)
        except tk.TclError:
            pass

    def _apply_windows_no_activate(self) -> None:
        if platform.system() != "Windows" or self._window is None:
            return
        try:
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = self._window.winfo_id()
            style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
            user32.SetWindowLongW(
                wintypes.HWND(hwnd),
                GWL_EXSTYLE,
                style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
            )
        except Exception:
            pass

    def hide(self) -> None:
        self._hide_timer = None
        if self._window is not None:
            try:
                if self._window.winfo_exists():
                    self._window.withdraw()
            except tk.TclError:
                pass

    def destroy(self) -> None:
        if self._hide_timer is not None:
            try:
                self._root.after_cancel(self._hide_timer)
            except tk.TclError:
                pass
            self._hide_timer = None
        if self._window is not None:
            try:
                if self._window.winfo_exists():
                    self._window.destroy()
            except tk.TclError:
                pass
            self._window = None
