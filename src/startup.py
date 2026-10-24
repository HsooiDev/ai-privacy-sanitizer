"""Windows auto-startup registry management and kernel-level single-instance wakeup/hot-replace IPC."""

import ctypes
from pathlib import Path
import platform
import sys
import tempfile
import threading
import time
from typing import Callable, Optional


RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "AIPrivacySanitizer"
MUTEX_NAME = "Local\\AIPrivacySanitizer_Mutex_v1"
SHOW_GUI_EVENT_NAME = "Local\\AIPrivacySanitizer_ShowGUI_Event_v1"
QUIT_EVENT_NAME = "Local\\AIPrivacySanitizer_Quit_Event_v1"
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0x00000000
INSTANCE_META_FILE = Path(tempfile.gettempdir()) / "ai_privacy_sanitizer_instance.meta"


def get_current_exe_signature() -> str:
    """Return a signature of the current executable/script path and its modification timestamp."""
    try:
        target = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve()
        stat = target.stat()
        return f"{target}|{stat.st_mtime_ns}|{stat.st_size}"
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


def is_startup_enabled() -> bool:
    """Check whether AI Privacy Sanitizer is registered in HKCU Run."""
    if platform.system() != "Windows":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ
        ) as key:
            val, _ = winreg.QueryValueEx(key, APP_REG_NAME)
            return bool(val)
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
        self._stop_watching = threading.Event()
        self.already_running = False

        if platform.system() == "Windows":
            kernel32 = ctypes.windll.kernel32
            self._show_event_handle = kernel32.CreateEventW(
                None, False, False, SHOW_GUI_EVENT_NAME
            )
            self._quit_event_handle = kernel32.CreateEventW(
                None, False, False, QUIT_EVENT_NAME
            )
            self._mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
            last_err = kernel32.GetLastError()

            if last_err == ERROR_ALREADY_EXISTS:
                current_sig = get_current_exe_signature()
                old_sig = ""
                try:
                    if INSTANCE_META_FILE.exists():
                        old_sig = INSTANCE_META_FILE.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

                # If executable was updated (mtime/size changed) or --replace passed,
                # tell the old running instance to quit and take over!
                if force_replace or (old_sig and old_sig != current_sig):
                    if self._quit_event_handle:
                        kernel32.SetEvent(self._quit_event_handle)
                    if self._mutex_handle:
                        kernel32.CloseHandle(self._mutex_handle)
                        self._mutex_handle = None
                    # Wait briefly for old instance to exit and release mutex
                    for _ in range(25):
                        time.sleep(0.1)
                        self._mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
                        if kernel32.GetLastError() != ERROR_ALREADY_EXISTS:
                            self.already_running = False
                            break
                        kernel32.CloseHandle(self._mutex_handle)
                        self._mutex_handle = None
                    else:
                        self.already_running = True
                else:
                    self.already_running = True

            if not self.already_running:
                try:
                    INSTANCE_META_FILE.write_text(get_current_exe_signature(), encoding="utf-8")
                except Exception:
                    pass

    def notify_existing_instance(self) -> None:
        """Signal the already-running instance to pop up its GUI settings window."""
        if platform.system() == "Windows" and self._show_event_handle:
            ctypes.windll.kernel32.SetEvent(self._show_event_handle)

    def start_wakeup_listener(
        self,
        on_wakeup: Callable[[], None],
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        """Listen in a daemon thread for wakeup or hot-replace quit signals."""
        if platform.system() != "Windows":
            return

        def _watch_loop() -> None:
            kernel32 = ctypes.windll.kernel32
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
        """Release kernel handles cleanly."""
        self._stop_watching.set()
        if platform.system() == "Windows":
            kernel32 = ctypes.windll.kernel32
            if self._show_event_handle:
                kernel32.CloseHandle(self._show_event_handle)
                self._show_event_handle = None
            if self._quit_event_handle:
                kernel32.CloseHandle(self._quit_event_handle)
                self._quit_event_handle = None
            if self._mutex_handle:
                kernel32.CloseHandle(self._mutex_handle)
                self._mutex_handle = None
