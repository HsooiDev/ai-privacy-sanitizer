"""Platform-aware clipboard privacy helpers preventing secrets from entering OS clipboard history."""

import ctypes
import platform
import struct
import time
from typing import Optional


def _copy_windows_concealed(text: str) -> bool:
    """Write CF_UNICODETEXT on Windows with Clipboard History & Cloud Sync exclusion markers."""
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    def _alloc_and_set(fmt: int, raw_bytes: bytes) -> bool:
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(raw_bytes))
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            return False
        try:
            ctypes.memmove(ptr, raw_bytes, len(raw_bytes))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(fmt, handle):
            kernel32.GlobalFree(handle)
            return False
        return True

    if not user32.OpenClipboard(None):
        return False
    try:
        if not user32.EmptyClipboard():
            return False
        encoded = (text + "\x00").encode("utf-16-le")
        if not _alloc_and_set(CF_UNICODETEXT, encoded):
            return False
        zero_dword = struct.pack("<I", 0)
        for fmt_name in (
            "ExcludeClipboardContentFromMonitorProcessing",
            "CanIncludeInClipboardHistory",
            "CanUploadToCloudClipboard",
        ):
            fmt_id = user32.RegisterClipboardFormatW(fmt_name)
            if fmt_id:
                _alloc_and_set(fmt_id, zero_dword)
        return True
    finally:
        user32.CloseClipboard()


def _copy_macos_concealed(text: str) -> bool:
    """Write NSPasteboard string with ConcealedType and TransientType markers on macOS."""
    try:
        import AppKit

        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.declareTypes_owner_(
            [
                AppKit.NSPasteboardTypeString,
                "org.nspasteboard.ConcealedType",
                "org.nspasteboard.TransientType",
            ],
            None,
        )
        ok = bool(pb.setString_forType_(text, AppKit.NSPasteboardTypeString))
        pb.setData_forType_(AppKit.NSData.data(), "org.nspasteboard.ConcealedType")
        pb.setData_forType_(AppKit.NSData.data(), "org.nspasteboard.TransientType")
        return ok
    except Exception:
        return False


def copy_clipboard_concealed(text: str, retries: int = 3) -> bool:
    """Best-effort concealed clipboard write (excludes Win+V / Cloud Clipboard / macOS clipboard managers)."""
    system = platform.system()
    if system == "Windows":
        for _ in range(max(1, retries)):
            try:
                if _copy_windows_concealed(text):
                    return True
            except Exception:
                pass
            time.sleep(0.05)
        return False
    if system == "Darwin":
        return _copy_macos_concealed(text)
    return False
