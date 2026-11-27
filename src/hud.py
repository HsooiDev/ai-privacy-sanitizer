"""Lightweight non-focus-stealing bottom-right Micro-HUD toast for desktop feedback."""

import ctypes
import platform
import tkinter as tk
from typing import Optional, Tuple

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode import CTkAppearanceModeBaseClass
from customtkinter.windows.widgets.scaling import CTkScalingBaseClass


_IGNORED_FOREGROUND_CLASSES = frozenset(
    {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
)
_HUD_FG_COLOR = ("#ffffff", "#131c31")


class _HudToplevel(ctk.CTkToplevel):
    """Frameless CTkToplevel that avoids titlebar withdraw/focus hacks and DPI snap-resizing."""

    def _windows_set_titlebar_color(self, color_mode: str) -> None:
        return None

    def _windows_set_titlebar_icon(self) -> None:
        return None

    def _set_scaling(self, new_widget_scaling, new_window_scaling) -> None:
        CTkScalingBaseClass._set_scaling(self, new_widget_scaling, new_window_scaling)

    def _set_appearance_mode(self, mode_string: str) -> None:
        CTkAppearanceModeBaseClass._set_appearance_mode(self, mode_string)
        tk.Toplevel.configure(self, bg=self._apply_appearance_mode(self._fg_color))


def format_tk_geometry(w: int, h: int, x: int, y: int) -> str:
    """Format a Tk geometry string preserving negative multi-monitor coordinates."""
    return f"{int(w)}x{int(h)}{int(x):+d}{int(y):+d}"


def compute_hud_geometry(
    req_w: int,
    req_h: int,
    work_area: Tuple[int, int, int, int],
    *,
    scale: float = 1.0,
    margin_right: int = 20,
    margin_bottom: int = 20,
) -> Tuple[int, int, int, int]:
    """Compute physical (w, h, x, y) strictly inside the target monitor's work area."""
    eff_scale = max(1.0, float(scale))
    left, top, right, bottom = (int(v) for v in work_area)
    work_w = max(1, right - left)
    work_h = max(1, bottom - top)

    pad_x = round(margin_right * eff_scale)
    pad_y = round(margin_bottom * eff_scale)
    min_w = round(260 * eff_scale)
    max_w = round(420 * eff_scale)
    min_h = round(64 * eff_scale)
    max_h = round(220 * eff_scale)

    avail_w = max(1, work_w - 2 * pad_x) if work_w > 2 * pad_x else work_w
    avail_h = max(1, work_h - 2 * pad_y) if work_h > 2 * pad_y else work_h

    w = min(max(min_w, min(max_w, int(req_w))), avail_w)
    h = min(max(min_h, min(max_h, int(req_h))), avail_h)

    x = max(left, min(right - w - pad_x, right - w))
    y = max(top, min(bottom - h - pad_y, bottom - h))
    return (w, h, x, y)


def _get_windows_target_monitor(
    exclude_hwnd: Optional[int] = None,
) -> Optional[Tuple[Tuple[int, int, int, int], float]]:
    """Return (rcWork, dpi_scale) for the active Windows monitor (foreground or cursor)."""
    if platform.system() != "Windows":
        return None
    try:
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HMONITOR
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL

        MONITOR_DEFAULTTOPRIMARY = 1
        MONITOR_DEFAULTTONEAREST = 2

        hmon = None
        fg_hwnd = user32.GetForegroundWindow()
        if fg_hwnd and (exclude_hwnd is None or int(fg_hwnd) != int(exclude_hwnd)):
            if user32.IsWindowVisible(fg_hwnd):
                buf = ctypes.create_unicode_buffer(128)
                if user32.GetClassNameW(fg_hwnd, buf, len(buf)) > 0:
                    if buf.value not in _IGNORED_FOREGROUND_CLASSES:
                        hmon = user32.MonitorFromWindow(fg_hwnd, MONITOR_DEFAULTTONEAREST)

        if not hmon:
            pt = wintypes.POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)

        if not hmon:
            hmon = user32.MonitorFromPoint(wintypes.POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
        if not hmon:
            return None

        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None

        work_area = (
            int(mi.rcWork.left),
            int(mi.rcWork.top),
            int(mi.rcWork.right),
            int(mi.rcWork.bottom),
        )

        scale = 1.0
        try:
            shcore = ctypes.WinDLL("shcore", use_last_error=True)
            shcore.GetDpiForMonitor.argtypes = [
                wintypes.HMONITOR,
                ctypes.c_int,
                ctypes.POINTER(wintypes.UINT),
                ctypes.POINTER(wintypes.UINT),
            ]
            shcore.GetDpiForMonitor.restype = ctypes.c_long
            dpi_x = wintypes.UINT()
            dpi_y = wintypes.UINT()
            if shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                if dpi_x.value >= 96:
                    scale = max(1.0, float(dpi_x.value) / 96.0)
        except Exception:
            pass

        return (work_area, scale)
    except Exception:
        return None


def get_target_work_area(
    root: tk.Misc, exclude_hwnd: Optional[int] = None
) -> Tuple[Tuple[int, int, int, int], float]:
    """Return ((left, top, right, bottom), dpi_scale) for the target display work area."""
    win_info = _get_windows_target_monitor(exclude_hwnd=exclude_hwnd)
    if win_info is not None:
        return win_info
    sw = max(1, int(root.winfo_screenwidth()))
    sh = max(1, int(root.winfo_screenheight()))
    return ((0, 0, sw, max(1, sh - 48)), 1.0)


class FloatingMicroHud:
    """Brief floating pill notification that never steals focus from the active editor."""

    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._window: Optional[ctk.CTkToplevel] = None
        self._card: Optional[ctk.CTkFrame] = None
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
                win = _HudToplevel(self._root, fg_color=_HUD_FG_COLOR)
                win.withdraw()
                win.overrideredirect(True)
                try:
                    win.attributes("-topmost", True)
                except tk.TclError:
                    pass
                card = ctk.CTkFrame(
                    win,
                    fg_color=_HUD_FG_COLOR,
                    corner_radius=10,
                    border_width=2,
                    border_color=accent,
                )
                card.pack(fill="both", expand=True, padx=0, pady=0)
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

            exclude_hwnd = None
            try:
                exclude_hwnd = int(self._window.winfo_id())
            except tk.TclError:
                pass

            work_area, target_scale = get_target_work_area(self._root, exclude_hwnd=exclude_hwnd)
            win_scaling = max(1.0, float(getattr(self._window, "_get_window_scaling", lambda: 1.0)()))
            self._window.update_idletasks()
            w, h, x, y = compute_hud_geometry(
                self._window.winfo_reqwidth(),
                self._window.winfo_reqheight(),
                work_area,
                scale=max(target_scale, win_scaling),
            )

            # Use raw tk.Toplevel.geometry so CTkToplevel does not double-multiply w/h by DPI scaling.
            tk.Toplevel.geometry(self._window, format_tk_geometry(w, h, x, y))
            self._window._current_width = max(1, round(w / win_scaling))
            self._window._current_height = max(1, round(h / win_scaling))

            self._apply_windows_no_activate()
            self._window.deiconify()
            self._position_windows_topmost_no_activate(x, y, w, h)
            self._hide_timer = self._root.after(duration_ms, self.hide)
        except tk.TclError:
            pass

    def _apply_windows_no_activate(self) -> None:
        if platform.system() != "Windows" or self._window is None:
            return
        try:
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            user32.SetWindowLongW.restype = ctypes.c_long
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            hwnd = wintypes.HWND(self._window.winfo_id())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        except Exception:
            pass

    def _position_windows_topmost_no_activate(self, x: int, y: int, w: int, h: int) -> None:
        if platform.system() != "Windows" or self._window is None:
            return
        try:
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            user32.SetWindowPos.restype = wintypes.BOOL
            HWND_TOPMOST = wintypes.HWND(-1)
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            SWP_FRAMECHANGED = 0x0020
            hwnd = wintypes.HWND(self._window.winfo_id())
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                int(x),
                int(y),
                int(w),
                int(h),
                SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED,
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
