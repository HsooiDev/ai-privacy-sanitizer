"""System tray application, GUI launcher, clipboard cruise monitor, global hotkeys, and CLI."""

import argparse
import getpass
import json
import os
from pathlib import Path
import platform
import sys
import threading
import tempfile
import time
from typing import Dict, List, Optional

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Guard stdio for PyInstaller --windowed mode where sys.stdout / sys.stderr may be None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from src import APP_NAME
from src.clipboard_privacy import copy_clipboard_concealed
from src.gui import GuiController, enable_high_dpi_awareness
from src.i18n import tr
from src.rules import SAMPLE_TEST_PAYLOAD
from src.sanitizer import HotkeyRollbackError, InputTooLargeError, MAX_SANITIZE_CHARS, PrivacySanitizer
from src.secure_io import atomic_write_private, validate_private_path
from src.startup import SingleInstanceGuard, is_startup_enabled, set_startup_enabled
from src.vault_crypto import is_encrypted_vault_payload


def create_shield_lock_icon(size: int = 64, state: str = "ready") -> Image.Image:
    """Dynamically draw a clean shield + padlock icon using Pillow with optional live status tint.

    States:
      - 'ready': Classic blue shield (manual hotkey mode, empty vault)
      - 'cruise': Emerald green shield with lightning badge (auto-sanitize cruise active)
      - 'vault': Classic blue shield with amber dot (active in-memory secrets awaiting clear)
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if state == "cruise":
        outer_fill = (5, 122, 85, 255)
        inner_fill = (16, 185, 129, 255)
        keyhole_fill = (5, 122, 85, 255)
    else:
        outer_fill = (16, 110, 190, 255)
        inner_fill = (24, 144, 235, 255)
        keyhole_fill = (16, 110, 190, 255)

    shield_points = [
        (size * 0.50, size * 0.06),
        (size * 0.88, size * 0.18),
        (size * 0.86, size * 0.54),
        (size * 0.50, size * 0.94),
        (size * 0.14, size * 0.54),
        (size * 0.12, size * 0.18),
    ]
    draw.polygon(shield_points, fill=outer_fill, outline=(255, 255, 255, 240))

    inner_points = [
        (size * 0.50, size * 0.13),
        (size * 0.80, size * 0.23),
        (size * 0.78, size * 0.52),
        (size * 0.50, size * 0.85),
        (size * 0.22, size * 0.52),
        (size * 0.20, size * 0.23),
    ]
    draw.polygon(inner_points, fill=inner_fill)

    shackle_box = [
        size * 0.37,
        size * 0.26,
        size * 0.63,
        size * 0.52,
    ]
    draw.arc(shackle_box, start=180, end=0, fill=(255, 255, 255, 255), width=max(3, size // 14))
    draw.line(
        [(size * 0.38, size * 0.38), (size * 0.38, size * 0.46)],
        fill=(255, 255, 255, 255),
        width=max(3, size // 16),
    )
    draw.line(
        [(size * 0.62, size * 0.38), (size * 0.62, size * 0.46)],
        fill=(255, 255, 255, 255),
        width=max(3, size // 16),
    )

    body_box = [
        size * 0.32,
        size * 0.45,
        size * 0.68,
        size * 0.73,
    ]
    draw.rounded_rectangle(body_box, radius=max(3, size // 16), fill=(255, 255, 255, 255))

    cx, cy = size * 0.50, size * 0.56
    r = max(2, size // 22)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=keyhole_fill)
    draw.line(
        [(cx, cy + r * 0.5), (cx, size * 0.67)],
        fill=keyhole_fill,
        width=max(2, size // 24),
    )

    # Status indicator badge in top-right corner
    if state in ("cruise", "vault"):
        dot_r = max(5, int(size * 0.16))
        bx = int(size * 0.78)
        by = int(size * 0.22)
        dot_color = (250, 204, 21, 255) if state == "cruise" else (245, 158, 11, 255)
        draw.ellipse(
            [bx - dot_r, by - dot_r, bx + dot_r, by + dot_r],
            fill=dot_color,
            outline=(255, 255, 255, 255),
            width=max(1, size // 32),
        )

    return image


def export_shield_ico(target_path: Path) -> Path:
    """Export multi-resolution Windows .ico file from Pillow shield icon."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    base_img = create_shield_lock_icon(256)
    base_img.save(
        target_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return target_path


def _safe_clipboard_paste(retries: int = 3) -> str:
    """Read clipboard with retry backoff to handle transient Windows clipboard locks."""
    import pyperclip

    last_err: Optional[Exception] = None
    for _ in range(retries):
        try:
            return pyperclip.paste() or ""
        except Exception as exc:
            last_err = exc
            time.sleep(0.05)
    if last_err is not None:
        raise last_err
    return ""


def _safe_clipboard_copy(text: str, retries: int = 3, *, conceal: bool = False) -> None:
    """Write clipboard with retry backoff; when conceal=True, mark to bypass OS clipboard history."""
    if conceal and copy_clipboard_concealed(text, retries=retries):
        return

    import pyperclip

    last_err: Optional[Exception] = None
    for _ in range(retries):
        try:
            pyperclip.copy(text)
            return
        except Exception as exc:
            last_err = exc
            time.sleep(0.05)
    if last_err is not None:
        raise last_err


def _replace_clipboard_if_unchanged(expected: str, replacement: str, *, conceal: bool = False) -> bool:
    """Recheck before every write attempt; pyperclip cannot provide an OS-wide atomic CAS."""
    for attempt in range(3):
        if _safe_clipboard_paste() != expected:
            return False
        try:
            if conceal:
                _safe_clipboard_copy(replacement, retries=1, conceal=True)
            else:
                _safe_clipboard_copy(replacement, retries=1)
            return True
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.05)
    return False


class SanitizerTrayApp:
    """System tray controller managing GUI, clipboard cruise mode, idle auto-wipe, hotkeys, and HUD."""

    def __init__(self, sanitizer: Optional[PrivacySanitizer] = None) -> None:
        self.sanitizer = sanitizer or PrivacySanitizer()
        self.icon = None
        self._action_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._last_written_clipboard: str = ""
        self._clipboard_undo_stack: List[str] = []
        self._last_oversize_notice = float("-inf")
        self._last_activity_ts: float = time.monotonic()
        self._last_tray_state: str = ""
        self._windows_hotkeys = None
        self.gui = GuiController(
            sanitizer=self.sanitizer,
            icon_factory=create_shield_lock_icon,
            on_sanitize_clipboard=self.sanitize_clipboard,
            on_restore_clipboard=self.restore_clipboard,
            on_undo_sanitize=self.undo_last_sanitize,
            on_open_raw_config=self.open_config_file,
            on_exit_app=self.exit_app,
            on_reload_hotkeys=self.reload_hotkeys,
            on_language_changed=self.refresh_tray_i18n,
            on_clear_session=self.clear_session_map,
            on_copy_to_clipboard=self.copy_to_clipboard,
            on_state_changed=self._update_tray_icon_state,
            get_idle_seconds_left=self.get_idle_seconds_remaining,
        )

    def _t(self, key: str) -> str:
        return tr(self.sanitizer.language, key)

    def _touch_activity(self) -> None:
        self._last_activity_ts = time.monotonic()

    def get_idle_seconds_remaining(self) -> Optional[int]:
        """Return seconds left before idle RAM vault auto-wipe, or None if disabled/empty."""
        minutes = self.sanitizer.idle_wipe_minutes
        if minutes <= 0 or self.sanitizer.vault.size == 0:
            return None
        elapsed = time.monotonic() - self._last_activity_ts
        return max(0, int(minutes * 60 - elapsed))

    def _compute_tray_state(self) -> str:
        if self.sanitizer.auto_sanitize_clipboard:
            return "cruise"
        if self.sanitizer.vault.size > 0:
            return "vault"
        return "ready"

    def _update_tray_icon_state(self) -> None:
        """Refresh tray icon tint dynamically based on cruise mode and vault state."""
        if self.icon is None:
            return
        state = self._compute_tray_state()
        if state == self._last_tray_state:
            return
        try:
            self.icon.icon = create_shield_lock_icon(64, state=state)
            self._last_tray_state = state
        except Exception:
            pass

    def _push_undo_snapshot(self, raw_text: str) -> None:
        if not raw_text:
            return
        if self._clipboard_undo_stack and self._clipboard_undo_stack[-1] == raw_text:
            return
        self._clipboard_undo_stack.append(raw_text)
        if len(self._clipboard_undo_stack) > 5:
            self._clipboard_undo_stack = self._clipboard_undo_stack[-5:]

    def notify(self, message: str, title: str = APP_NAME, *, tone: str = "info") -> None:
        """Send a non-intrusive Micro-HUD toast (if enabled) plus desktop Toast notification."""
        if self.sanitizer.hud_enabled and hasattr(self, "gui") and self.gui is not None:
            try:
                self.gui.show_hud(title, message, tone=tone)
            except Exception:
                pass
        if self.icon is None:
            return
        notified = False
        try:
            self.icon.notify(message, title)
            notified = True
        except Exception:
            notified = False

        if not notified:
            try:
                from plyer import notification

                notification.notify(
                    title=title,
                    message=message,
                    app_name=APP_NAME,
                    timeout=3,
                )
            except Exception:
                pass

    def copy_to_clipboard(self, text: str, *, conceal: bool = False) -> bool:
        """Write text to clipboard from GUI while informing Cruise Mode to ignore this self-write."""
        with self._action_lock:
            try:
                use_conceal = bool(conceal and self.sanitizer.clipboard_privacy_guard)
                if use_conceal:
                    _safe_clipboard_copy(text, conceal=True)
                else:
                    _safe_clipboard_copy(text)
                self._last_written_clipboard = text
                self._touch_activity()
                return True
            except Exception:
                return False

    def sanitize_clipboard(self, *_args) -> None:
        """Read clipboard, sanitize sensitive content, write back, and show Toast/HUD."""
        with self._action_lock:
            self._touch_activity()
            try:
                raw_text = _safe_clipboard_paste()
            except Exception:
                self.notify(self._t("notify_clip_read_err").format(err="unavailable"), tone="error")
                return

            if not raw_text or not raw_text.strip():
                self.notify(self._t("notify_clip_empty_san"), tone="info")
                return

            try:
                result = self.sanitizer.sanitize(raw_text)
            except InputTooLargeError:
                self.notify(self._t("notify_input_too_large"), tone="error")
                return
            if result.total_count > 0:
                try:
                    if not _replace_clipboard_if_unchanged(raw_text, result.sanitized_text):
                        self.notify(self._t("notify_clip_changed"), tone="warning")
                        return
                    self._push_undo_snapshot(raw_text)
                    self._last_written_clipboard = result.sanitized_text
                except Exception:
                    self.notify(self._t("notify_clip_write_err").format(err="unavailable"), tone="error")
                    return
                self._update_tray_icon_state()
                self.gui.request_refresh()

            tone = "success" if result.total_count > 0 else "info"
            self.notify(result.format_summary(self.sanitizer.language), tone=tone)

    def restore_clipboard(self, *_args) -> None:
        """Read clipboard, restore placeholders to original sensitive values, write back securely."""
        with self._action_lock:
            self._touch_activity()
            try:
                raw_text = _safe_clipboard_paste()
            except Exception:
                self.notify(self._t("notify_clip_read_err").format(err="unavailable"), tone="error")
                return

            if not raw_text or not raw_text.strip():
                self.notify(self._t("notify_clip_empty_res"), tone="info")
                return

            try:
                result = self.sanitizer.restore(raw_text)
            except InputTooLargeError:
                self.notify(self._t("notify_input_too_large"), tone="error")
                return

            if result.restored_count > 0:
                try:
                    use_conceal = self.sanitizer.clipboard_privacy_guard
                    if not _replace_clipboard_if_unchanged(raw_text, result.restored_text, conceal=use_conceal):
                        self.notify(self._t("notify_clip_changed"), tone="warning")
                        return
                    self._last_written_clipboard = result.restored_text
                except Exception:
                    self.notify(self._t("notify_clip_write_err").format(err="unavailable"), tone="error")
                    return
                self.gui.request_refresh()
                self.notify(
                    result.format_summary(self.sanitizer.language) + " · " + self._t("msg_restore_warning"),
                    tone="warning",
                )
            else:
                self.notify(result.format_summary(self.sanitizer.language), tone="info")

    def undo_last_sanitize(self, *_args) -> None:
        """Restore clipboard to the previous pre-sanitized raw text from the in-memory undo stack."""
        with self._action_lock:
            self._touch_activity()
            if not self._clipboard_undo_stack:
                self.notify(self._t("notify_undo_empty"), tone="info")
                return
            previous_raw = self._clipboard_undo_stack[-1]
            try:
                current = _safe_clipboard_paste()
                use_conceal = self.sanitizer.clipboard_privacy_guard
                if not _replace_clipboard_if_unchanged(current, previous_raw, conceal=use_conceal):
                    self.notify(self._t("notify_clip_changed"), tone="warning")
                    return
                self._clipboard_undo_stack.pop()
                self._last_written_clipboard = previous_raw
                self.gui.request_refresh()
                self.notify(
                    self._t("notify_undo_ok").format(left=len(self._clipboard_undo_stack)),
                    tone="info",
                )
            except Exception:
                self.notify(self._t("notify_clip_write_err").format(err="unavailable"), tone="error")

    def open_gui_center(self, *_args) -> None:
        """Show the visual GUI Control Center window."""
        self._touch_activity()
        self.gui.show_window()

    def open_config_file(self, *_args) -> None:
        """Open `config.json` in the built-in in-app JSON editor modal (never jumps to external apps)."""
        self._touch_activity()
        self.gui.show_json_editor()

    def toggle_auto_sanitize_mode(self, *_args) -> None:
        """Toggle clipboard auto-sanitize cruise mode."""
        new_state = not self.sanitizer.auto_sanitize_clipboard
        self.sanitizer.set_auto_sanitize_clipboard(new_state)
        self._update_tray_icon_state()
        self.gui.request_refresh()
        if new_state:
            self.notify(self._t("notify_cruise_on"), tone="success")
        else:
            self.notify(self._t("notify_cruise_off"), tone="info")

    def toggle_startup_mode(self, *_args) -> None:
        """Toggle Windows login auto-startup registration."""
        new_state = not is_startup_enabled()
        if set_startup_enabled(new_state):
            self.gui.request_refresh()
            if new_state:
                self.notify(self._t("notify_startup_on"), tone="success")
            else:
                self.notify(self._t("notify_startup_off"), tone="info")
        else:
            self.notify(self._t("notify_startup_err"), tone="error")

    def clear_session_map(self, *_args) -> None:
        """Clear all in-memory bidirectional mappings and undo history."""
        with self._action_lock:
            self._clipboard_undo_stack.clear()
            self._last_written_clipboard = ""
            cleared = self.sanitizer.clear_session()
            self._touch_activity()
        self._update_tray_icon_state()
        self.gui.request_refresh()
        self.notify(self._t("notify_vault_cleared").format(count=cleared), tone="info")

    def _check_idle_wipe(self) -> None:
        """Automatically clear RAM vault and undo snapshots after configured inactivity period."""
        remaining = self.get_idle_seconds_remaining()
        if remaining is not None and remaining <= 0:
            with self._action_lock:
                # Re-verify under lock
                if self.get_idle_seconds_remaining() == 0:
                    self._clipboard_undo_stack.clear()
                    self._last_written_clipboard = ""
                    cleared = self.sanitizer.clear_session()
                    self._touch_activity()
                else:
                    return
            self._update_tray_icon_state()
            self.gui.request_refresh()
            self.notify(self._t("notify_idle_wiped").format(count=cleared), tone="info")

    def exit_app(self, *_args) -> None:
        """Unregister hotkeys, stop GUI and clipboard watcher, and stop system tray loop."""
        self._stop_event.set()
        with self._action_lock:
            self._clipboard_undo_stack.clear()
        if platform.system() == "Windows":
            if self._windows_hotkeys is not None:
                self._windows_hotkeys.stop()
        elif platform.system() != "Darwin":
            try:
                import keyboard

                keyboard.unhook_all_hotkeys()
            except Exception:
                pass

        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
        self.gui.shutdown()

    def _cruise_once(self, last_seen: str) -> str:
        """Process one polling step; all application clipboard state shares the action lock."""
        with self._action_lock:
            if not self.sanitizer.auto_sanitize_clipboard:
                return last_seen
            try:
                current = _safe_clipboard_paste()
                if current != self._last_written_clipboard:
                    self._last_written_clipboard = ""
                if not current or current == last_seen or current == self._last_written_clipboard:
                    return current
                try:
                    result = self.sanitizer.sanitize(current)
                except InputTooLargeError:
                    now = time.monotonic()
                    if now - self._last_oversize_notice >= 30:
                        self.notify(self._t("notify_input_too_large"), tone="error")
                        self._last_oversize_notice = now
                    return current
                if result.total_count and _replace_clipboard_if_unchanged(current, result.sanitized_text):
                    self._push_undo_snapshot(current)
                    self._last_written_clipboard = result.sanitized_text
                    self._touch_activity()
                    self._update_tray_icon_state()
                    self.gui.request_refresh()
                    self.notify(
                        self._t("notify_cruise_hit").format(
                            summary=result.format_summary(self.sanitizer.language)
                        ),
                        tone="success",
                    )
                    return result.sanitized_text
                return current
            except Exception:
                # Keep last_seen unchanged on read/write failure so the next poll can retry.
                return last_seen

    def _start_clipboard_cruise_watcher(self) -> None:
        """Best-effort polling loop plus idle auto-wipe watchdog."""
        def _cruise_loop() -> None:
            last_seen = ""
            tick = 0
            while not self._stop_event.wait(0.55):
                last_seen = self._cruise_once(last_seen)
                tick += 1
                if tick % 4 == 0:
                    self._check_idle_wipe()

        threading.Thread(target=_cruise_loop, daemon=True).start()

    def register_hotkeys(self, hotkeys: Optional[Dict[str, str]] = None) -> bool:
        """Register persisted settings or a candidate that has not been saved yet."""
        if platform.system() == "Darwin":
            # keyboard's current Darwin backend requires root. Keep the preview unprivileged.
            return False
        hotkeys = self.sanitizer.hotkeys if hotkeys is None else hotkeys
        sanitize_key = hotkeys.get("sanitize", "alt+s")
        restore_key = hotkeys.get("restore", "alt+r")
        try:
            if platform.system() == "Windows":
                from src.windows_hotkeys import WindowsHotkeys

                previous = getattr(self, "_windows_hotkeys", None)
                candidate = WindowsHotkeys([
                    (sanitize_key, lambda: threading.Thread(target=self.sanitize_clipboard, daemon=True).start()),
                    (restore_key, lambda: threading.Thread(target=self.restore_clipboard, daemon=True).start()),
                ])
                if previous is not None:
                    previous.stop()
                try:
                    candidate.start()
                except Exception:
                    if previous is not None:
                        previous.start()
                    raise
                self._windows_hotkeys = candidate
                return True

            import keyboard

            keyboard.add_hotkey(
                sanitize_key,
                lambda: threading.Thread(target=self.sanitize_clipboard, daemon=True).start(),
            )
            keyboard.add_hotkey(
                restore_key,
                lambda: threading.Thread(target=self.restore_clipboard, daemon=True).start(),
            )
            return True
        except Exception as exc:
            if sys.stderr is not None:
                sys.stderr.write(
                    f"[WARN] Failed to register global hotkeys ({exc}). Tray menu remains active.\n"
                )
            return False

    def refresh_tray_i18n(self) -> None:
        """Refresh tray tooltip, icon state, and menu labels when language or hotkeys change."""
        if self.icon is not None:
            try:
                hk = self.sanitizer.hotkeys
                san_u = hk.get("sanitize", "alt+s").upper()
                res_u = hk.get("restore", "alt+r").upper()
                self.icon.title = self._t("tray_tooltip").format(
                    app=APP_NAME, san=san_u, res=res_u
                )
                self._update_tray_icon_state()
                self.icon.update_menu()
            except Exception:
                pass

    def _reload_hotkey_registration(self, hotkeys: Dict[str, str]) -> bool:
        """Replace platform registrations without changing the persisted settings."""
        if platform.system() != "Windows":
            try:
                import keyboard

                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        return self.register_hotkeys(hotkeys)

    def reload_hotkeys(self, hotkeys: Optional[Dict[str, str]] = None) -> bool:
        """Apply a candidate before committing it; a failed registration never writes settings."""
        if platform.system() == "Darwin":
            self.refresh_tray_i18n()
            return False
        previous = self.sanitizer.hotkeys
        candidate = previous if hotkeys is None else self.sanitizer.normalize_hotkeys(
            hotkeys["sanitize"], hotkeys["restore"]
        )
        if not self._reload_hotkey_registration(candidate):
            if platform.system() != "Windows":
                self._reload_hotkey_registration(previous)
            return False
        if hotkeys is not None:
            try:
                self.sanitizer.set_hotkeys(candidate["sanitize"], candidate["restore"])
            except Exception as error:
                if not self._reload_hotkey_registration(previous):
                    raise HotkeyRollbackError("Active global hotkeys could not be restored") from error
                raise
        self.refresh_tray_i18n()
        return True

    def run(self, show_gui_on_start: bool = False) -> None:
        """Start global hotkeys, cruise watcher, background system tray icon, and main-thread GUI loop."""
        import pystray
        from pystray import Menu, MenuItem

        if platform.system() == "Darwin":
            self.gui.startup_status = self._t("macos_preview_hotkeys")
        else:
            self.gui.startup_status = None if self.register_hotkeys() else self._t("msg_hk_err")
        self._start_clipboard_cruise_watcher()

        initial_state = self._compute_tray_state()
        icon_image = create_shield_lock_icon(64, state=initial_state)
        self._last_tray_state = initial_state

        menu_items = [
            MenuItem(lambda _item: self._t("tray_open_gui"), self.open_gui_center, default=True),
            Menu.SEPARATOR,
            MenuItem(
                lambda _item: self._t("tray_sanitize").format(
                    san=self.sanitizer.hotkeys.get("sanitize", "alt+s").upper()
                ),
                self.sanitize_clipboard,
            ),
            MenuItem(
                lambda _item: self._t("tray_restore").format(
                    res=self.sanitizer.hotkeys.get("restore", "alt+r").upper()
                ),
                self.restore_clipboard,
            ),
            MenuItem(
                lambda _item: self._t("tray_undo"),
                self.undo_last_sanitize,
            ),
            Menu.SEPARATOR,
            MenuItem(
                lambda _item: self._t("tray_cruise"),
                self.toggle_auto_sanitize_mode,
                checked=lambda _item: self.sanitizer.auto_sanitize_clipboard,
            ),
        ]
        if platform.system() == "Windows":
            menu_items.append(
                MenuItem(
                    lambda _item: self._t("tray_startup"),
                    self.toggle_startup_mode,
                    checked=lambda _item: is_startup_enabled(),
                )
            )
        menu_items.extend([
            Menu.SEPARATOR,
            MenuItem(lambda _item: self._t("tray_open_config"), self.open_config_file),
            MenuItem(lambda _item: self._t("tray_clear_vault"), self.clear_session_map),
            Menu.SEPARATOR,
            MenuItem(lambda _item: self._t("tray_exit"), self.exit_app),
        ])
        menu = Menu(*menu_items)

        hk = self.sanitizer.hotkeys

        def _start_tray() -> None:
            options = {}
            if platform.system() == "Darwin":
                import AppKit

                options["darwin_nsapplication"] = AppKit.NSApplication.sharedApplication()
            self.icon = pystray.Icon(
                name="ai-privacy-sanitizer",
                icon=icon_image,
                title=self._t("tray_tooltip").format(
                    app=APP_NAME,
                    san=hk.get("sanitize", "alt+s").upper(),
                    res=hk.get("restore", "alt+r").upper(),
                ),
                menu=menu,
                **options,
            )
            self._start_tray_loop()

        if platform.system() == "Darwin":
            self.gui.run_main_loop(show_on_start=show_gui_on_start, before_mainloop=_start_tray)
        else:
            _start_tray()
            self.gui.run_main_loop(show_on_start=show_gui_on_start)

    def _start_tray_loop(self) -> None:
        """Integrate macOS menu-bar events into Tk's main thread; retain other backends."""
        if platform.system() == "Darwin":
            self.icon.run_detached()
        else:
            threading.Thread(target=self.icon.run, daemon=True).start()


def _configure_stdio_utf8() -> None:
    """Ensure stdin, stdout, and stderr use UTF-8 encoding in CLI mode."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def run_self_test() -> int:
    """Run a quick CLI self-test verifying icon generation, sanitization, and 100% restoration."""
    _configure_stdio_utf8()
    with tempfile.TemporaryDirectory(prefix="aps-self-test-") as temporary:
        root = Path(temporary).resolve()
        sanitizer = PrivacySanitizer(
            config_path=root / "config.json", example_config_path=root / "unused-example.json"
        )
        icon = create_shield_lock_icon(64)
        assert icon.size == (64, 64)

        san_res = sanitizer.sanitize(SAMPLE_TEST_PAYLOAD)
        assert "ssw0rd99" not in san_res.sanitized_text, "Redis password fragment leaked!"
        res_res = sanitizer.restore(san_res.sanitized_text)
        assert res_res.restored_text == SAMPLE_TEST_PAYLOAD, "Restoration mismatch!"
        if sys.stdout is not None:
            sys.stdout.write(f"{san_res.format_summary()}\n")
            sys.stdout.write(f"{res_res.format_summary()}\n")
        return 0


def _obtain_cli_passphrase(args: argparse.Namespace, vault_path: Optional[Path]) -> Optional[str]:
    """Read passphrase securely from env/stdin/TTY when using --encrypt or an encrypted vault."""
    needs_passphrase = bool(args.encrypt)
    if not needs_passphrase and vault_path is not None and vault_path.exists():
        try:
            parsed = json.loads(vault_path.read_text(encoding="utf-8"))
            if is_encrypted_vault_payload(parsed):
                needs_passphrase = True
        except Exception:
            pass
    if not needs_passphrase:
        return None
    if args.passphrase_env:
        val = os.environ.get(args.passphrase_env, "")
        if not val:
            raise ValueError("Passphrase environment variable is empty")
        return val
    if args.passphrase_stdin:
        if args.stdin or args.restore_stdin:
            raise ValueError("--passphrase-stdin cannot be combined with --stdin or --restore-stdin")
        line = sys.stdin.readline() if sys.stdin is not None else ""
        pw = line.rstrip("\r\n")
        if not pw:
            raise ValueError("Empty passphrase on stdin")
        return pw
    return getpass.getpass("Vault passphrase: ")


def main(
    argv: Optional[List[str]] = None,
    sanitizer: Optional[PrivacySanitizer] = None,
) -> int:
    enable_high_dpi_awareness()
    parser = argparse.ArgumentParser(
        description="Sanitizer: 100% Local Clipboard & CLI Privacy Sanitizer & Restorer"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in self-test and exit without starting system tray",
    )
    parser.add_argument(
        "--export-ico",
        type=str,
        default="",
        help="Export shield icon to the specified .ico path and exit",
    )
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Start minimized in system tray without opening the GUI control center window",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Force replace any existing running instance",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read raw text from stdin, write sanitized text to stdout (or --output) and summary to stderr",
    )
    parser.add_argument(
        "--restore-stdin",
        action="store_true",
        help="Read sanitized text from stdin, write restored text to stdout (or --output) and summary to stderr",
    )
    parser.add_argument(
        "--file",
        type=str,
        default="",
        help="Path to input file to sanitize locally",
    )
    parser.add_argument(
        "--restore-file",
        type=str,
        default="",
        help="Path to sanitized input file to restore locally using --vault-file",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Explicitly replace an existing output file (never the input file)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional path to output file (defaults to stdout if omitted)",
    )
    parser.add_argument(
        "--encoding",
        type=str,
        default="utf-8",
        help="Text encoding for --file / --restore-file (default: utf-8; falls back gracefully on decode errors)",
    )
    parser.add_argument(
        "--vault-file",
        type=str,
        default="",
        help="Opt-in local secret mappings for cross-process CLI restoration (add --encrypt for AES-256-GCM)",
    )
    parser.add_argument(
        "--encrypt",
        action="store_true",
        help="Encrypt --vault-file with Scrypt + AES-256-GCM using a local passphrase",
    )
    parser.add_argument(
        "--passphrase-stdin",
        action="store_true",
        help="Read vault passphrase from first line of stdin (usable with --file / --restore-file)",
    )
    parser.add_argument(
        "--passphrase-env",
        type=str,
        default="",
        help="Name of environment variable holding vault passphrase (avoid passing secrets in argv)",
    )
    args = parser.parse_args(argv)

    if args.export_ico:
        export_shield_ico(Path(args.export_ico))
        return 0

    if args.self_test:
        return run_self_test()

    if args.stdin or args.restore_stdin or args.file or args.restore_file:
        _configure_stdio_utf8()
        try:
            mode_count = sum(bool(value) for value in (args.stdin, args.restore_stdin, args.file, args.restore_file))
            if mode_count != 1:
                raise ValueError("Choose exactly one CLI input mode")
            if args.encrypt and not args.vault_file:
                raise ValueError("--encrypt requires --vault-file")
            active_sanitizer = sanitizer or PrivacySanitizer()
            in_path = Path(args.file or args.restore_file) if (args.file or args.restore_file) else None
            out_path = validate_private_path(Path(args.output)) if args.output else None
            vault_path = validate_private_path(Path(args.vault_file)) if args.vault_file else None
            paths = [p for p in (in_path, out_path, vault_path, active_sanitizer.config_path) if p is not None]
            for index, left in enumerate(paths):
                for right in paths[index + 1:]:
                    if left.resolve() == right.resolve() or (
                        left.exists() and right.exists() and os.path.samefile(left, right)
                    ):
                        raise ValueError("Input, output, vault and config paths must be distinct files")
            if out_path is not None and out_path.exists() and not args.overwrite:
                raise FileExistsError("Output already exists; use --overwrite to replace it")
            passphrase = _obtain_cli_passphrase(args, vault_path)
            if vault_path is not None:
                if passphrase is None:
                    sys.stderr.write("Warning: --vault-file stores original secrets as local plaintext (use --encrypt to protect with AES-256-GCM).\n")
                active_sanitizer.vault.load_from_file(vault_path, passphrase=passphrase)
            if in_path is not None:
                with in_path.open(encoding=args.encoding, errors="replace") as stream:
                    raw_input = stream.read(MAX_SANITIZE_CHARS + 1)
            else:
                raw_input = sys.stdin.read(MAX_SANITIZE_CHARS + 1) if sys.stdin is not None else ""
            if len(raw_input) > MAX_SANITIZE_CHARS:
                raise InputTooLargeError()
            if args.restore_stdin or args.restore_file:
                result = active_sanitizer.restore(raw_input)
                output = result.restored_text
                if result.restored_count > 0:
                    sys.stderr.write("Warning: restored output contains original values; review locally before sharing.\n")
            else:
                result = active_sanitizer.sanitize(raw_input)
                output = result.sanitized_text
                if vault_path is not None:
                    active_sanitizer.vault.save_to_file(vault_path, passphrase=passphrase)
            if out_path is not None:
                atomic_write_private(out_path, output, overwrite=args.overwrite)
            elif sys.stdout is not None:
                sys.stdout.write(output)
                sys.stdout.flush()
            if sys.stderr is not None:
                sys.stderr.write(f"{result.format_summary(active_sanitizer.language)}\n")
                sys.stderr.flush()
            return 0
        except InputTooLargeError:
            sys.stderr.write(f"Error: input exceeds {MAX_SANITIZE_CHARS:,} characters; no output produced.\n")
        except (OSError, ValueError):
            # Paths, parser errors and exception objects may contain secrets. Never echo them.
            sys.stderr.write("Error: CLI operation failed; check distinct paths, private permissions, passphrase/JSON and --overwrite. No text output produced.\n")
        return 2

    guard = SingleInstanceGuard(force_replace=args.replace)
    if guard.already_running:
        guard.notify_existing_instance()
        guard.close()
        return 0

    app = SanitizerTrayApp()
    guard.start_wakeup_listener(on_wakeup=app.open_gui_center, on_quit=app.exit_app)
    try:
        app.run(show_gui_on_start=not args.minimized)
    finally:
        guard.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
