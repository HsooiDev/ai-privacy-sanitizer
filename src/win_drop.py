"""Zero-dependency Windows native drag-and-drop handler via Win32 WM_DROPFILES."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import platform
from typing import Callable, List, Optional


WM_NCDESTROY = 0x0082
WM_DROPFILES = 0x0233
WM_COPYDATA = 0x004A
WM_COPYGLOBALDATA = 0x0049
MSGFLT_ALLOW = 1
GWLP_WNDPROC = -4
GA_ROOT = 2

LONG_PTR = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class _WinDropAPI:
    """Thin ctypes wrapper for Win32 window subclassing and Shell DragAcceptFiles."""

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.shell32 = ctypes.WinDLL("shell32", use_last_error=True)

        self.user32.GetParent.argtypes = [wintypes.HWND]
        self.user32.GetParent.restype = wintypes.HWND

        self._get_ancestor = getattr(self.user32, "GetAncestor", None)
        if self._get_ancestor is not None:
            self._get_ancestor.argtypes = [wintypes.HWND, wintypes.UINT]
            self._get_ancestor.restype = wintypes.HWND

        self._set_wndproc = getattr(self.user32, "SetWindowLongPtrW", None) or getattr(
            self.user32, "SetWindowLongW"
        )
        self._set_wndproc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        self._set_wndproc.restype = ctypes.c_void_p

        self.user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.CallWindowProcW.restype = LONG_PTR

        self.shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
        self.shell32.DragAcceptFiles.restype = None

        self.shell32.DragQueryFileW.argtypes = [
            wintypes.HANDLE,
            wintypes.UINT,
            wintypes.LPWSTR,
            wintypes.UINT,
        ]
        self.shell32.DragQueryFileW.restype = wintypes.UINT

        self.shell32.DragFinish.argtypes = [wintypes.HANDLE]
        self.shell32.DragFinish.restype = None

        self._change_filter = getattr(self.user32, "ChangeWindowMessageFilterEx", None)
        if self._change_filter is not None:
            self._change_filter.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                wintypes.DWORD,
                ctypes.c_void_p,
            ]
            self._change_filter.restype = wintypes.BOOL

    def get_top_hwnd(self, widget_id: int) -> int:
        hwnd = wintypes.HWND(widget_id)
        if self._get_ancestor is not None:
            root_hwnd = self._get_ancestor(hwnd, GA_ROOT)
            if root_hwnd:
                return int(root_hwnd)
        parent = self.user32.GetParent(hwnd)
        return int(parent) if parent else int(widget_id)

    def drag_accept_files(self, hwnd: int, accept: bool) -> None:
        self.shell32.DragAcceptFiles(wintypes.HWND(hwnd), bool(accept))
        if accept and self._change_filter is not None:
            for msg in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
                try:
                    self._change_filter(wintypes.HWND(hwnd), msg, MSGFLT_ALLOW, None)
                except Exception:
                    pass

    def set_wndproc(self, hwnd: int, proc_ptr) -> int:
        res = self._set_wndproc(wintypes.HWND(hwnd), GWLP_WNDPROC, proc_ptr)
        return int(res or 0)

    def call_wndproc(self, prev_proc: int, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        return int(
            self.user32.CallWindowProcW(
                ctypes.c_void_p(prev_proc),
                wintypes.HWND(hwnd),
                msg,
                wparam,
                lparam,
            )
        )

    def extract_drop_paths(self, hdrop: int) -> List[Path]:
        handle = wintypes.HANDLE(hdrop)
        paths: List[Path] = []
        try:
            count = self.shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
            for idx in range(int(count)):
                length = self.shell32.DragQueryFileW(handle, idx, None, 0)
                if length <= 0:
                    continue
                buf = ctypes.create_unicode_buffer(int(length) + 1)
                self.shell32.DragQueryFileW(handle, idx, buf, int(length) + 1)
                if buf.value:
                    paths.append(Path(buf.value))
        finally:
            self.shell32.DragFinish(handle)
        return paths


class WindowsFileDropTarget:
    """Attach native Windows Explorer file/folder drag-and-drop support to a Tk root window."""

    def __init__(
        self,
        root,
        on_drop_paths: Callable[[List[Path]], None],
        *,
        api: Optional[_WinDropAPI] = None,
    ) -> None:
        self._root = root
        self._on_drop_paths = on_drop_paths
        self._api = api
        self._hwnd: Optional[int] = None
        self._prev_wndproc: int = 0
        self._wndproc_cb = None
        self.attached: bool = False

    def attach(self) -> bool:
        """Register DragAcceptFiles and hook WM_DROPFILES on the top-level HWND."""
        if self.attached:
            return True
        if self._api is None and platform.system() != "Windows":
            return False
        try:
            api = self._api if self._api is not None else _WinDropAPI()
            self._api = api
            hwnd = api.get_top_hwnd(int(self._root.winfo_id()))
            if not hwnd:
                return False

            prev_ref = [0]

            def _wndproc(h_wnd, msg, wparam, lparam):
                if msg == WM_DROPFILES:
                    try:
                        paths = api.extract_drop_paths(int(wparam))
                        if paths:
                            if hasattr(self._root, "after"):
                                self._root.after(0, lambda p=paths: self._on_drop_paths(p))
                            else:
                                self._on_drop_paths(paths)
                    except Exception:
                        pass
                    return 0
                prev_proc = prev_ref[0] or self._prev_wndproc
                if msg == WM_NCDESTROY:
                    self.attached = False
                    self._hwnd = None
                    self._prev_wndproc = 0
                    if prev_proc:
                        try:
                            api.set_wndproc(int(h_wnd), ctypes.c_void_p(prev_proc))
                        except Exception:
                            pass
                    try:
                        return api.call_wndproc(prev_proc, h_wnd, msg, wparam, lparam) if prev_proc else 0
                    finally:
                        self._wndproc_cb = None
                return api.call_wndproc(prev_proc, h_wnd, msg, wparam, lparam) if prev_proc else 0

            self._wndproc_cb = WNDPROC(_wndproc)
            prev = api.set_wndproc(hwnd, ctypes.cast(self._wndproc_cb, ctypes.c_void_p))
            if not prev:
                self._wndproc_cb = None
                return False
            prev_ref[0] = prev
            self._hwnd = hwnd
            self._prev_wndproc = prev
            api.drag_accept_files(hwnd, True)
            self.attached = True
            return True
        except Exception:
            self._wndproc_cb = None
            self._hwnd = None
            self._prev_wndproc = 0
            self.attached = False
            return False

    def handle_drop_message(self, hdrop: int) -> List[Path]:
        """Extract dropped paths for a WM_DROPFILES handle and dispatch the callback."""
        if self._api is None:
            self._api = _WinDropAPI()
        paths = self._api.extract_drop_paths(hdrop)
        if paths:
            if hasattr(self._root, "after"):
                self._root.after(0, lambda p=paths: self._on_drop_paths(p))
            else:
                self._on_drop_paths(paths)
        return paths

    def detach(self) -> None:
        """Restore original WndProc and disable DragAcceptFiles."""
        if not self.attached or self._api is None or not self._hwnd:
            self.attached = False
            return
        try:
            if self._prev_wndproc:
                self._api.set_wndproc(self._hwnd, ctypes.c_void_p(self._prev_wndproc))
            self._api.drag_accept_files(self._hwnd, False)
        except Exception:
            pass
        finally:
            self.attached = False
            self._hwnd = None
            self._prev_wndproc = 0
            self._wndproc_cb = None

    def __del__(self) -> None:
        try:
            self.detach()
        except Exception:
            pass
