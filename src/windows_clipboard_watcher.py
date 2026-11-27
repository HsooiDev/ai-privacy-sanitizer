"""Zero-polling Windows native clipboard event listener using AddClipboardFormatListener."""

import ctypes
from ctypes import wintypes
import platform
import threading
from typing import Callable, Optional


WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_CLIPBOARDUPDATE = 0x031D
HWND_MESSAGE = wintypes.HWND(-3)

LONG_PTR = ctypes.c_ssize_t
_FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
WNDPROC = _FUNCTYPE(LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class _WinClipboardAPI:
    """Thin ctypes wrapper around User32 AddClipboardFormatListener and message-only window APIs."""

    def __init__(self) -> None:
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self.kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self.kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        self.user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.DefWindowProcW.restype = LONG_PTR

        self.user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
        self.user32.RegisterClassExW.restype = wintypes.ATOM

        self.user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        self.user32.CreateWindowExW.restype = wintypes.HWND

        self.user32.DestroyWindow.argtypes = [wintypes.HWND]
        self.user32.DestroyWindow.restype = wintypes.BOOL

        self.user32.AddClipboardFormatListener.argtypes = [wintypes.HWND]
        self.user32.AddClipboardFormatListener.restype = wintypes.BOOL

        self.user32.RemoveClipboardFormatListener.argtypes = [wintypes.HWND]
        self.user32.RemoveClipboardFormatListener.restype = wintypes.BOOL

        self.user32.GetClipboardSequenceNumber.argtypes = []
        self.user32.GetClipboardSequenceNumber.restype = wintypes.DWORD

        self.user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self.user32.GetMessageW.restype = ctypes.c_int

        self.user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        self.user32.TranslateMessage.restype = wintypes.BOOL

        self.user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        self.user32.DispatchMessageW.restype = LONG_PTR

        self.user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self.user32.PostMessageW.restype = wintypes.BOOL

        self.user32.PostQuitMessage.argtypes = [ctypes.c_int]
        self.user32.PostQuitMessage.restype = None

    def create_message_window(self, class_name: str, wndproc_cb) -> int:
        hinst = self.kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = wndproc_cb
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        atom = self.user32.RegisterClassExW(ctypes.byref(wc))
        if not atom and ctypes.get_last_error() != 1410:  # ERROR_CLASS_ALREADY_EXISTS
            raise OSError("RegisterClassExW failed for clipboard watcher")
        hwnd = self.user32.CreateWindowExW(
            0, class_name, "APSClipboardWatcher", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None
        )
        if not hwnd:
            raise OSError("CreateWindowExW failed for clipboard watcher")
        return int(hwnd)

    def def_window_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        return int(self.user32.DefWindowProcW(wintypes.HWND(hwnd), msg, wparam, lparam))

    def add_listener(self, hwnd: int) -> bool:
        return bool(self.user32.AddClipboardFormatListener(wintypes.HWND(hwnd)))

    def remove_listener(self, hwnd: int) -> bool:
        return bool(self.user32.RemoveClipboardFormatListener(wintypes.HWND(hwnd)))

    def get_sequence_number(self) -> int:
        return int(self.user32.GetClipboardSequenceNumber())

    def get_message(self, message: wintypes.MSG) -> int:
        return int(self.user32.GetMessageW(ctypes.byref(message), None, 0, 0))

    def translate_and_dispatch(self, message: wintypes.MSG) -> None:
        self.user32.TranslateMessage(ctypes.byref(message))
        self.user32.DispatchMessageW(ctypes.byref(message))

    def post_close(self, hwnd: int) -> bool:
        return bool(self.user32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0))

    def destroy_window(self, hwnd: int) -> bool:
        return bool(self.user32.DestroyWindow(wintypes.HWND(hwnd)))

    def post_quit(self) -> None:
        self.user32.PostQuitMessage(0)


class WindowsClipboardWatcher:
    """Event-driven Windows clipboard watcher (zero background polling)."""

    def __init__(
        self,
        on_clipboard_update: Callable[[], None],
        *,
        api: Optional[_WinClipboardAPI] = None,
    ) -> None:
        self._on_clipboard_update = on_clipboard_update
        self._api = api
        self._ready = threading.Event()
        self._stop_requested = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._hwnd: Optional[int] = None
        self._error: Optional[BaseException] = None
        self._wndproc_cb = None
        self._last_seq: Optional[int] = None

    @property
    def active(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._error is None
            and not self._stop_requested.is_set()
        )

    def _dispatch_update(self) -> None:
        if self._api is None or self._stop_requested.is_set():
            return
        try:
            seq = self._api.get_sequence_number()
        except Exception:
            seq = None
        if seq is not None and seq == self._last_seq:
            return
        if seq is not None:
            self._last_seq = seq
        try:
            self._on_clipboard_update()
        except Exception:
            pass

    def start(self) -> None:
        if self.active:
            return
        if self._api is None and platform.system() != "Windows":
            raise OSError("WindowsClipboardWatcher is only supported on Windows")
        if self._api is None:
            self._api = _WinClipboardAPI()
        self._ready.clear()
        self._stop_requested.clear()
        self._error = None
        self._last_seq = None

        def _run() -> None:
            api = self._api
            assert api is not None
            hwnd = 0
            listener_added = False
            try:
                def _wndproc(h_wnd, msg, wparam, lparam):
                    if msg == WM_CLIPBOARDUPDATE:
                        self._dispatch_update()
                        return 0
                    if msg == WM_CLOSE:
                        api.destroy_window(int(h_wnd))
                        return 0
                    if msg == WM_DESTROY:
                        api.post_quit()
                        return 0
                    return api.def_window_proc(int(h_wnd), msg, wparam, lparam)

                self._wndproc_cb = WNDPROC(_wndproc)
                class_name = f"APSClipWatcher_{threading.get_native_id()}"
                hwnd = api.create_message_window(class_name, self._wndproc_cb)
                self._hwnd = hwnd
                if not api.add_listener(hwnd):
                    raise OSError("AddClipboardFormatListener failed")
                listener_added = True
                self._ready.set()

                message = wintypes.MSG()
                while not self._stop_requested.is_set():
                    res = api.get_message(message)
                    if res == -1:
                        raise OSError("GetMessageW failed in clipboard watcher")
                    if res == 0:
                        break
                    if message.message == WM_CLIPBOARDUPDATE:
                        self._dispatch_update()
                    else:
                        api.translate_and_dispatch(message)
            except Exception as exc:
                self._error = exc
            finally:
                if listener_added and hwnd:
                    try:
                        api.remove_listener(hwnd)
                    except Exception:
                        pass
                if hwnd:
                    try:
                        api.destroy_window(hwnd)
                    except Exception:
                        pass
                self._hwnd = None
                self._wndproc_cb = None
                self._ready.set()

        self._thread = threading.Thread(target=_run, daemon=True, name="aps-win-clip-watch")
        self._thread.start()
        if not self._ready.wait(5):
            self.stop()
            raise OSError("Windows clipboard watcher startup timed out")
        if self._error is not None:
            self._thread.join(2)
            raise self._error

    def stop(self) -> None:
        self._stop_requested.set()
        if self._thread is not None and self._thread.is_alive() and self._api is not None:
            hwnd = self._hwnd
            if hwnd:
                try:
                    self._api.post_close(hwnd)
                except Exception:
                    pass
            self._thread.join(2)
