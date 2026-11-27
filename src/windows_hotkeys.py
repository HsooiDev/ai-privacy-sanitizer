"""Windows system hotkeys without a low-level, all-key keyboard hook."""

import ctypes
from ctypes import wintypes
import re
import threading


_MODIFIER_FLAGS = {
    "alt": 1,
    "ctrl": 2,
    "control": 2,
    "shift": 4,
    "win": 8,
    "windows": 8,
    "super": 8,
    "meta": 8,
    "cmd": 8,
    "command": 8,
}

_OEM_VKS = {
    ";": 0xBA, "semicolon": 0xBA,
    "=": 0xBB, "equal": 0xBB, "equals": 0xBB, "plus": 0xBB,
    ",": 0xBC, "comma": 0xBC,
    "-": 0xBD, "minus": 0xBD,
    ".": 0xBE, "period": 0xBE, "dot": 0xBE,
    "/": 0xBF, "slash": 0xBF,
    "`": 0xC0, "grave": 0xC0, "backquote": 0xC0,
    "[": 0xDB, "bracketleft": 0xDB,
    "\\": 0xDC, "backslash": 0xDC,
    "]": 0xDD, "bracketright": 0xDD,
    "'": 0xDE, "apostrophe": 0xDE, "quote": 0xDE,
}


def parse_hotkey(binding: str, key_scan) -> tuple[int, int]:
    """Translate single-chord hotkey settings into Windows RegisterHotKey inputs."""
    parts = binding.lower().replace(" ", "").split("+")
    if any(not part for part in parts):
        raise ValueError("Invalid hotkey format")
    modifiers = 0
    for part in parts[:-1]:
        flag = _MODIFIER_FLAGS.get(part)
        if flag is None or modifiers & flag:
            raise ValueError("Unsupported hotkey modifiers")
        modifiers |= flag
    key = parts[-1]
    named = {
        "space": 0x20, "tab": 9, "enter": 13, "return": 13,
        "esc": 27, "escape": 27, "backspace": 8, "insert": 0x2D,
        "delete": 0x2E, "home": 0x24, "end": 0x23,
        "pageup": 0x21, "page_up": 0x21, "prior": 0x21,
        "pagedown": 0x22, "page_down": 0x22, "next": 0x22,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "capslock": 0x14, "caps_lock": 0x14, "numlock": 0x90, "num_lock": 0x90,
        "scrolllock": 0x91, "scroll_lock": 0x91, "pause": 0x13,
        "printscreen": 0x2C, "print_screen": 0x2C,
        "num_mul": 0x6A, "numpad_multiply": 0x6A,
        "num_add": 0x6B, "numpad_add": 0x6B,
        "num_sub": 0x6D, "numpad_subtract": 0x6D,
        "num_dec": 0x6E, "numpad_decimal": 0x6E,
        "num_div": 0x6F, "numpad_divide": 0x6F,
        **{f"num{d}": 0x60 + d for d in range(10)},
        **{f"numpad{d}": 0x60 + d for d in range(10)},
    }
    if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key):
        vk = 0x70 + int(key[1:]) - 1
    elif key in named:
        vk = named[key]
    elif len(key) == 1:
        scanned = key_scan(key)
        if scanned != -1 and not ((scanned >> 8) & ~7):
            vk = scanned & 0xFF
            state = (scanned >> 8) & 7
            modifiers |= (4 if state & 1 else 0) | (2 if state & 2 else 0) | (1 if state & 4 else 0)
        elif key in _OEM_VKS:
            vk = _OEM_VKS[key]
        else:
            raise ValueError("Hotkey is unavailable for this keyboard layout")
    elif key in _OEM_VKS:
        vk = _OEM_VKS[key]
    else:
        raise ValueError("Unsupported hotkey key")
    return modifiers, vk


class _WindowsAPI:
    def __init__(self):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.user.RegisterHotKey.restype = wintypes.BOOL
        self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.UnregisterHotKey.restype = wintypes.BOOL
        self.user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self.user.GetMessageW.restype = ctypes.c_int
        self.user.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.PostThreadMessageW.restype = wintypes.BOOL
        self.user.VkKeyScanW.argtypes = [wintypes.WCHAR]
        self.user.VkKeyScanW.restype = ctypes.c_short
        self.kernel.GetCurrentThreadId.restype = wintypes.DWORD

    def key_scan(self, key):
        return self.user.VkKeyScanW(key)

    def thread_id(self):
        return self.kernel.GetCurrentThreadId()

    def register(self, identity, modifiers, key):
        return bool(self.user.RegisterHotKey(None, identity, modifiers | 0x4000, key))

    def unregister(self, identity):
        return self.user.UnregisterHotKey(None, identity)

    def get_message(self, message):
        return self.user.GetMessageW(ctypes.byref(message), None, 0, 0)

    def stop(self, thread_id):
        return bool(self.user.PostThreadMessageW(thread_id, 0x12, 0, 0))


class WindowsHotkeys:
    """Own just the configured system chords on a dedicated message thread."""

    def __init__(self, bindings, api=None):
        self.bindings = tuple(bindings)
        self._api = api if api is not None else _WindowsAPI()
        self._chords = [parse_hotkey(binding, self._api.key_scan) for binding, _ in self.bindings]
        if len(set(self._chords)) != len(self._chords):
            raise ValueError("Duplicate system hotkeys")
        self._ready = threading.Event()
        self._thread = None
        self._thread_id = None
        self._error = None
        self.failed_binding = None

    @property
    def active(self):
        return self._thread is not None and self._thread.is_alive() and self._error is None

    def start(self):
        if self.active:
            return
        self._ready.clear()
        self._error = None
        self.failed_binding = None

        def run():
            registered = []
            try:
                self._thread_id = self._api.thread_id()
                for identity, (modifiers, key) in enumerate(self._chords, 1):
                    if not self._api.register(identity, modifiers, key):
                        self.failed_binding = self.bindings[identity - 1][0]
                        raise OSError(
                            f"Global hotkey '{self.failed_binding}' is unavailable or already registered"
                        )
                    registered.append(identity)
                self._ready.set()
                message = wintypes.MSG()
                while True:
                    result = self._api.get_message(message)
                    if result == -1:
                        raise OSError("Windows hotkey message retrieval failed")
                    if result == 0:
                        return
                    if message.message == 0x312:
                        identity = int(message.wParam)
                        if identity in registered:
                            self.bindings[identity - 1][1]()
            except Exception as error:
                self._error = error
            finally:
                for identity in registered:
                    self._api.unregister(identity)
                self._ready.set()

        self._thread = threading.Thread(target=run, daemon=True, name="aps-windows-hotkeys")
        self._thread.start()
        if not self._ready.wait(5):
            self.stop()
            raise OSError("Windows hotkey registration timed out")
        if self._error is not None:
            self._thread.join(2)
            raise self._error

    def stop(self):
        if self._thread is not None and self._thread.is_alive():
            if not self._api.stop(self._thread_id):
                raise OSError("Could not stop Windows hotkeys")
            self._thread.join(2)
            if self._thread.is_alive():
                raise OSError("Windows hotkeys did not stop")
