"""Tests for FloatingMicroHud high-DPI geometry, multi-monitor clamping, and Windows non-activating behavior."""

import ctypes
import sys
import tkinter as tk

import customtkinter as ctk
import pytest

from src.gui import _StableCTk, enable_high_dpi_awareness
from src.hud import FloatingMicroHud, compute_hud_geometry, format_tk_geometry


def _assert_inside_work_area(geom, work_area):
    w, h, x, y = geom
    left, top, right, bottom = work_area
    assert w > 0 and h > 0
    assert x >= left
    assert y >= top
    assert x + w <= right
    assert y + h <= bottom


def test_compute_hud_geometry_clamps_within_125_and_150_dpi_monitors():
    wa_125 = (0, 0, 1920, 1140)
    g_125 = compute_hud_geometry(440, 110, wa_125, scale=1.25)
    _assert_inside_work_area(g_125, wa_125)

    wa_150 = (0, 0, 1920, 1020)
    g_150 = compute_hud_geometry(520, 140, wa_150, scale=1.5)
    _assert_inside_work_area(g_150, wa_150)


def test_compute_hud_geometry_supports_secondary_right_and_left_negative_monitors():
    wa_right = (1920, 0, 4480, 1392)
    g_right = compute_hud_geometry(340, 90, wa_right, scale=1.0)
    _assert_inside_work_area(g_right, wa_right)
    assert format_tk_geometry(*g_right) == f"{g_right[0]}x{g_right[1]}+{g_right[2]}+{g_right[3]}"

    wa_left = (-1920, 0, 0, 1040)
    g_left = compute_hud_geometry(340, 90, wa_left, scale=1.0)
    _assert_inside_work_area(g_left, wa_left)
    geom_str = format_tk_geometry(*g_left)
    assert "+-" not in geom_str
    assert geom_str.startswith(f"{g_left[0]}x{g_left[1]}-")


def test_compute_hud_geometry_clamps_small_work_area():
    wa_small = (0, 0, 300, 200)
    g_small = compute_hud_geometry(360, 120, wa_small, scale=1.0)
    _assert_inside_work_area(g_small, wa_small)


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows HWND rect & style verification")
def test_windows_live_hud_bounds_no_activate_and_theme_toggle(monkeypatch):
    enable_high_dpi_awareness()
    ctk.set_appearance_mode("Dark")
    try:
        root = _StableCTk()
    except tk.TclError as exc:
        if "display" in str(exc).lower():
            pytest.skip("Tk display unavailable")
        raise
    root.withdraw()

    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND

    GWL_EXSTYLE = -20
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080

    hud = FloatingMicroHud(root)
    try:
        for work_area, scale in [
            ((0, 0, 1920, 1140), 1.25),
            ((1920, 0, 4480, 1392), 1.0),
        ]:
            monkeypatch.setattr("src.hud.get_target_work_area", lambda _r, exclude_hwnd=None, wa=work_area, sc=scale: (wa, sc))
            hud.show(
                "AI Privacy Sanitizer",
                "已脱敏：共拦截 12 处敏感信息（API_KEY: 4, DB_PASS: 3, PRIVATE_IP: 5）",
                duration_ms=2000,
                tone="success",
            )
            root.update()
            hwnd = int(hud._window.winfo_id())
            rect = RECT()
            assert user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
            left, top, right, bottom = work_area
            assert rect.left >= left
            assert rect.top >= top
            assert rect.right <= right
            assert rect.bottom <= bottom
            assert rect.right - rect.left >= hud._window.winfo_reqwidth()
            assert rect.bottom - rect.top >= hud._window.winfo_reqheight()

            ex_style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
            assert ex_style & WS_EX_NOACTIVATE
            assert ex_style & WS_EX_TOOLWINDOW
            assert int(user32.GetForegroundWindow() or 0) != hwnd

        ctk.set_appearance_mode("Light")
        root.update()
        ctk.set_appearance_mode("Dark")
        root.update()
        hud.hide()
    finally:
        hud.destroy()
        for timer in root.tk.splitlist(root.tk.call("after", "info")):
            root.tk.call("after", "cancel", timer)
        root.destroy()
