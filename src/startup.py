"""Windows auto-startup registry management and cross-platform single-instance wakeup/hot-replace IPC."""

import ctypes
import os
from pathlib import Path
import platform
import shlex
import sys
import tempfile
import threading
import time
from typing import Callable, Optional

from src.secure_io import atomic_write_private, validate_private_path


RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "AIPrivacySanitizer"
MUTEX_NAME = "Local\\AIPrivacySanitizer_Mutex_v1"
SHOW_GUI_EVENT_NAME = "Local\\AIPrivacySanitizer_ShowGUI_Event_v1"
QUIT_EVENT_NAME = "Local\\AIPrivacySanitizer_Quit_Event_v1"
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0x00000000


def _get_instance_meta_file() -> Path:
    """Store single-instance executable signature in a user-private directory (never shared %TEMP%)."""
    if platform.system() == "Windows":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "Sanitizer" / "instance.meta"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "AI-Privacy-Sanitizer" / "instance.meta"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "ai-privacy-sanitizer" / "instance.meta"


def _get_posix_lock_file() -> Path:
    """Return user-private lockfile path for macOS / Linux single-instance protection."""
    return _get_instance_meta_file().with_suffix(".lock")


INSTANCE_META_FILE = _get_instance_meta_file()


def _load_windows_kernel32():
    """Return a WinDLL kernel32 handle with explicit 64-bit-safe argtypes/restypes and use_last_error."""
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def get_current_exe_signature() -> str:
    """Return a signature of the current executable/script path and its modification timestamp."""
    try:
        target = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
        stat_info = target.stat()
        return f"{target}|{stat_info.st_mtime_ns}|{stat_info.st_size}"
    except Exception:
        return "unknown"


def get_launch_command() -> str:
    """Return the command string used for Windows Startup registration (starts minimized in tray)."""
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}" --minimized'
    python_exe = Path(sys.executable).resolve()
    pythonw = python_exe.with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else python_exe
    main_script = (Path(__file__).resolve().parent / "main.py").resolve()
    return f'"{runner}" "{main_script}" --minimized'


def _registered_executable_exists(command_str: str) -> bool:
    """Verify the first executable token in a Windows Run registry command points to an existing file."""
    cleaned = str(command_str or "").strip()
    if not cleaned:
        return False
    try:
        if cleaned.startswith('"'):
            end_quote = cleaned.find('"', 1)
            exe_part = cleaned[1:end_quote] if end_quote > 1 else cleaned.strip('"')
        else:
            parts = shlex.split(cleaned, posix=False)
            exe_part = parts[0] if parts else ""
        return bool(exe_part) and Path(exe_part).exists()
    except Exception:
        return False


def is_startup_enabled() -> bool:
    """Check whether AI Privacy Sanitizer is registered in HKCU Run and points to a valid executable."""
    if platform.system() != "Windows":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ
        ) as key:
            val, _ = winreg.QueryValueEx(key, APP_REG_NAME)
            return bool(val) and _registered_executable_exists(str(val))
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_startup_enabled(enabled: bool) -> bool:
    """Enable or disable Windows login auto-startup in HKCU Run (no admin required)."""
    if platform.system() != "Windows":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                cmd = get_launch_command()
                winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_REG_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


class SingleInstanceGuard:
    """OS-level single-instance lock with auto-replace on executable update and wakeup IPC."""

    def __init__(self, force_replace: bool = False) -> None:
        self._mutex_handle: Optional[int] = None
        self._show_event_handle: Optional[int] = None
        self._quit_event_handle: Optional[int] = None
        self._kernel32 = None
        self._posix_lock_fd: Optional[int] = None
        self._stop_watching = threading.Event()
        self.already_running = False

        if platform.system() == "Windows":
            kernel32 = _load_windows_kernel32()
            self._kernel32 = kernel32
            self._show_event_handle = kernel32.CreateEventW(
                None, False, False, SHOW_GUI_EVENT_NAME
            )
            self._quit_event_handle = kernel32.CreateEventW(
                None, False, False, QUIT_EVENT_NAME
            )
            self._mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
            last_err = ctypes.get_last_error()

            if last_err == ERROR_ALREADY_EXISTS:
                current_sig = get_current_exe_signature()
                old_sig = ""
                try:
                    meta_path = _get_instance_meta_file()
                    if meta_path.exists():
                        validate_private_path(meta_path)
                        old_sig = meta_path.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

                # If executable was updated (mtime/size changed) or --replace passed,
                # tell the old running instance to quit and take over.
                if force_replace or (old_sig and old_sig != current_sig):
                    if self._quit_event_handle:
                        kernel32.SetEvent(self._quit_event_handle)
                    if self._mutex_handle:
                        kernel32.CloseHandle(self._mutex_handle)
                        self._mutex_handle = None
                    for _ in range(25):
                        time.sleep(0.1)
                        self._mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
                        if ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
                            self.already_running = False
                            break
                        if self._mutex_handle:
                            kernel32.CloseHandle(self._mutex_handle)
                            self._mutex_handle = None
                    else:
                        self.already_running = True
                else:
                    self.already_running = True

            if not self.already_running:
                try:
                    atomic_write_private(_get_instance_meta_file(), get_current_exe_signature())
                except Exception:
                    pass
        elif os.name == "posix":
            self._acquire_posix_lock()

    def _acquire_posix_lock(self) -> None:
        """Acquire a non-blocking advisory flock on macOS/Linux to prevent duplicate tray processes."""
        try:
            import fcntl

            lock_path = _get_posix_lock_file()
            lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            validate_private_path(lock_path)
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                self.already_running = True
                return
            self._posix_lock_fd = fd
        except Exception:
            # Never fail startup if lock directory is read-only or flock unsupported.
            self._posix_lock_fd = None

    def notify_existing_instance(self) -> None:
        """Signal the already-running instance to pop up its GUI settings window."""
        if platform.system() == "Windows" and self._show_event_handle and self._kernel32 is not None:
            self._kernel32.SetEvent(self._show_event_handle)

    def start_wakeup_listener(
        self,
        on_wakeup: Callable[[], None],
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        """Listen in a daemon thread for wakeup or hot-replace quit signals."""
        if platform.system() != "Windows" or self._kernel32 is None:
            return

        kernel32 = self._kernel32

        def _watch_loop() -> None:
            while not self._stop_watching.is_set():
                if self._quit_event_handle:
                    q_res = kernel32.WaitForSingleObject(self._quit_event_handle, 50)
                    if q_res == WAIT_OBJECT_0 and not self._stop_watching.is_set():
                        if on_quit:
                            try:
                                on_quit()
                            except Exception:
                                pass
                        return
                if self._show_event_handle:
                    s_res = kernel32.WaitForSingleObject(self._show_event_handle, 250)
                    if s_res == WAIT_OBJECT_0 and not self._stop_watching.is_set():
                        try:
                            on_wakeup()
                        except Exception:
                            pass

        thread = threading.Thread(target=_watch_loop, daemon=True)
        thread.start()

    def close(self) -> None:
        """Release kernel/file lock handles cleanly."""
        self._stop_watching.set()
        if platform.system() == "Windows" and self._kernel32 is not None:
            kernel32 = self._kernel32
            if self._show_event_handle:
                kernel32.CloseHandle(self._show_event_handle)
                self._show_event_handle = None
            if self._quit_event_handle:
                kernel32.CloseHandle(self._quit_event_handle)
                self._quit_event_handle = None
            if self._mutex_handle:
                kernel32.CloseHandle(self._mutex_handle)
                self._mutex_handle = None
        if self._posix_lock_fd is not None:
            try:
                import fcntl

                fcntl.flock(self._posix_lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(self._posix_lock_fd)
            except Exception:
                pass
            self._posix_lock_fd = None
