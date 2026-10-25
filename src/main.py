"""System tray application, GUI launcher, clipboard cruise monitor, global hotkeys, and notifications."""

import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import time
from typing import List, Optional

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Guard stdio for PyInstaller --windowed mode where sys.stdout / sys.stderr may be None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from src.gui import GuiController, enable_high_dpi_awareness
from src.i18n import tr
from src.rules import SAMPLE_TEST_PAYLOAD
from src.sanitizer import PrivacySanitizer
from src.startup import SingleInstanceGuard, is_startup_enabled, set_startup_enabled


APP_NAME = "AI Privacy Sanitizer"


def create_shield_lock_icon(size: int = 64) -> Image.Image:
    """Dynamically draw a clean shield + padlock icon using Pillow (zero external asset files)."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    shield_points = [
        (size * 0.50, size * 0.06),
        (size * 0.88, size * 0.18),
        (size * 0.86, size * 0.54),
        (size * 0.50, size * 0.94),
        (size * 0.14, size * 0.54),
        (size * 0.12, size * 0.18),
    ]
    draw.polygon(shield_points, fill=(16, 110, 190, 255), outline=(255, 255, 255, 240))

    inner_points = [
        (size * 0.50, size * 0.13),
        (size * 0.80, size * 0.23),
        (size * 0.78, size * 0.52),
        (size * 0.50, size * 0.85),
        (size * 0.22, size * 0.52),
        (size * 0.20, size * 0.23),
    ]
    draw.polygon(inner_points, fill=(24, 144, 235, 255))

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
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(16, 110, 190, 255))
    draw.line(
        [(cx, cy + r * 0.5), (cx, size * 0.67)],
        fill=(16, 110, 190, 255),
        width=max(2, size // 24),
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


def _safe_clipboard_copy(text: str, retries: int = 3) -> None:
    """Write clipboard with retry backoff to handle transient Windows clipboard locks."""
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


class SanitizerTrayApp:
    """System tray controller managing GUI, clipboard cruise mode, sanitization, restoration, and hotkeys."""

    def __init__(self, sanitizer: Optional[PrivacySanitizer] = None) -> None:
        self.sanitizer = sanitizer or PrivacySanitizer()
        self.icon = None
        self._action_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._last_written_clipboard: str = ""
        self._clipboard_undo_stack: List[str] = []
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
        )

    def _t(self, key: str) -> str:
        return tr(self.sanitizer.language, key)

    def _push_undo_snapshot(self, raw_text: str) -> None:
        if not raw_text:
            return
        if self._clipboard_undo_stack and self._clipboard_undo_stack[-1] == raw_text:
            return
        self._clipboard_undo_stack.append(raw_text)
        if len(self._clipboard_undo_stack) > 5:
            self._clipboard_undo_stack = self._clipboard_undo_stack[-5:]

    def notify(self, message: str, title: str = APP_NAME) -> None:
        """Send a desktop Toast notification via tray icon or plyer fallback."""
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

    def sanitize_clipboard(self, *_args) -> None:
        """Read clipboard, sanitize sensitive content, write back, and show Toast."""
        with self._action_lock:
            try:
                raw_text = _safe_clipboard_paste()
            except Exception as exc:
                self.notify(self._t("notify_clip_read_err").format(err=exc))
                return

            if not raw_text or not raw_text.strip():
                self.notify(self._t("notify_clip_empty_san"))
                return

            result = self.sanitizer.sanitize(raw_text)
            if result.total_count > 0:
                try:
                    self._push_undo_snapshot(raw_text)
                    self._last_written_clipboard = result.sanitized_text
                    _safe_clipboard_copy(result.sanitized_text)
                except Exception as exc:
                    self.notify(self._t("notify_clip_write_err").format(err=exc))
                    return
                self.gui.request_refresh()

            self.notify(result.format_summary(self.sanitizer.language))

    def restore_clipboard(self, *_args) -> None:
        """Read clipboard, restore placeholders to original sensitive values, write back."""
        with self._action_lock:
            try:
                raw_text = _safe_clipboard_paste()
            except Exception as exc:
                self.notify(self._t("notify_clip_read_err").format(err=exc))
                return

            if not raw_text or not raw_text.strip():
                self.notify(self._t("notify_clip_empty_res"))
                return

            result = self.sanitizer.restore(raw_text)
            if result.restored_count > 0:
                try:
                    self._last_written_clipboard = result.restored_text
                    _safe_clipboard_copy(result.restored_text)
                except Exception as exc:
                    self.notify(self._t("notify_clip_write_err").format(err=exc))
                    return
                self.gui.request_refresh()

            self.notify(result.format_summary(self.sanitizer.language))

    def undo_last_sanitize(self, *_args) -> None:
        """Restore clipboard to the previous pre-sanitized raw text from the in-memory undo stack."""
        with self._action_lock:
            if not self._clipboard_undo_stack:
                self.notify(self._t("notify_undo_empty"))
                return
            previous_raw = self._clipboard_undo_stack.pop()
            try:
                self._last_written_clipboard = previous_raw
                _safe_clipboard_copy(previous_raw)
                self.gui.request_refresh()
                self.notify(
                    self._t("notify_undo_ok").format(left=len(self._clipboard_undo_stack))
                )
            except Exception as exc:
                self.notify(self._t("notify_clip_write_err").format(err=exc))

    def open_gui_center(self, *_args) -> None:
        """Show the visual GUI Control Center window."""
        self.gui.show_window()

    def open_config_file(self, *_args) -> None:
        """Open `config.json` in the built-in in-app JSON editor modal (never jumps to external apps)."""
        self.gui.show_json_editor()

    def toggle_auto_sanitize_mode(self, *_args) -> None:
        """Toggle clipboard auto-sanitize cruise mode."""
        new_state = not self.sanitizer.auto_sanitize_clipboard
        self.sanitizer.set_auto_sanitize_clipboard(new_state)
        if new_state:
            self.notify(self._t("notify_cruise_on"))
        else:
            self.notify(self._t("notify_cruise_off"))

    def toggle_startup_mode(self, *_args) -> None:
        """Toggle Windows login auto-startup registration."""
        new_state = not is_startup_enabled()
        if set_startup_enabled(new_state):
            if new_state:
                self.notify(self._t("notify_startup_on"))
            else:
                self.notify(self._t("notify_startup_off"))
        else:
            self.notify(self._t("notify_startup_err"))

    def clear_session_map(self, *_args) -> None:
        """Clear all in-memory bidirectional mappings and undo history."""
        with self._action_lock:
            self._clipboard_undo_stack.clear()
        cleared = self.sanitizer.clear_session()
        self.gui.request_refresh()
        self.notify(self._t("notify_vault_cleared").format(count=cleared))

    def exit_app(self, *_args) -> None:
        """Unregister hotkeys, stop GUI and clipboard watcher, and stop system tray loop."""
        self._stop_event.set()
        with self._action_lock:
            self._clipboard_undo_stack.clear()
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

    def _start_clipboard_cruise_watcher(self) -> None:
        """Background daemon thread that auto-sanitizes clipboard when cruise mode is enabled."""
        def _cruise_loop() -> None:
            last_seen = ""
            try:
                last_seen = _safe_clipboard_paste()
            except Exception:
                pass

            while not self._stop_event.is_set():
                time.sleep(0.55)
                if not self.sanitizer.auto_sanitize_clipboard:
                    continue
                try:
                    current = _safe_clipboard_paste()
                except Exception:
                    continue

                if (
                    not current
                    or not current.strip()
                    or len(current) > 1_000_000
                    or current == last_seen
                    or current == self._last_written_clipboard
                ):
                    last_seen = current or ""
                    continue

                last_seen = current
                with self._action_lock:
                    res = self.sanitizer.sanitize(current)
                    if res.total_count > 0:
                        try:
                            self._push_undo_snapshot(current)
                            self._last_written_clipboard = res.sanitized_text
                            last_seen = res.sanitized_text
                            _safe_clipboard_copy(res.sanitized_text)
                            self.gui.request_refresh()
                            summary_body = res.format_summary(self.sanitizer.language)[1:]
                            self.notify(self._t("notify_cruise_hit").format(summary=summary_body))
                        except Exception:
                            pass

        threading.Thread(target=_cruise_loop, daemon=True).start()

    def register_hotkeys(self) -> bool:
        """Register global hotkeys from `config.json`."""
        hotkeys = self.sanitizer.hotkeys
        sanitize_key = hotkeys.get("sanitize", "alt+s")
        restore_key = hotkeys.get("restore", "alt+r")
        try:
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
        """Refresh tray tooltip and menu labels when language or hotkeys change."""
        if self.icon is not None:
            try:
                hk = self.sanitizer.hotkeys
                san_u = hk.get("sanitize", "alt+s").upper()
                res_u = hk.get("restore", "alt+r").upper()
                self.icon.title = self._t("tray_tooltip").format(
                    app=APP_NAME, san=san_u, res=res_u
                )
                self.icon.update_menu()
            except Exception:
                pass

    def reload_hotkeys(self) -> bool:
        """Unhook existing global hotkeys and register the newly configured hotkeys immediately."""
        try:
            import keyboard

            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        ok = self.register_hotkeys()
        self.refresh_tray_i18n()
        return ok

    def run(self, show_gui_on_start: bool = False) -> None:
        """Start global hotkeys, cruise watcher, background system tray icon, and main-thread GUI loop."""
        import pystray
        from pystray import Menu, MenuItem

        self.register_hotkeys()
        self._start_clipboard_cruise_watcher()

        icon_image = create_shield_lock_icon(64)

        menu = Menu(
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
            MenuItem(
                lambda _item: self._t("tray_startup"),
                self.toggle_startup_mode,
                checked=lambda _item: is_startup_enabled(),
            ),
            Menu.SEPARATOR,
            MenuItem(lambda _item: self._t("tray_open_config"), self.open_config_file),
            MenuItem(lambda _item: self._t("tray_clear_vault"), self.clear_session_map),
            Menu.SEPARATOR,
            MenuItem(lambda _item: self._t("tray_exit"), self.exit_app),
        )

        hk = self.sanitizer.hotkeys
        self.icon = pystray.Icon(
            name="ai-privacy-sanitizer",
            icon=icon_image,
            title=self._t("tray_tooltip").format(
                app=APP_NAME,
                san=hk.get("sanitize", "alt+s").upper(),
                res=hk.get("restore", "alt+r").upper(),
            ),
            menu=menu,
        )
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.gui.run_main_loop(show_on_start=show_gui_on_start)


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
    sanitizer = PrivacySanitizer()
    icon = create_shield_lock_icon(64)
    assert icon.size == (64, 64)

    san_res = sanitizer.sanitize(SAMPLE_TEST_PAYLOAD)
    res_res = sanitizer.restore(san_res.sanitized_text)
    assert res_res.restored_text == SAMPLE_TEST_PAYLOAD, "Restoration mismatch!"
    if sys.stdout is not None:
        sys.stdout.write(f"{san_res.format_summary()}\n")
        sys.stdout.write(f"{res_res.format_summary()}\n")
    return 0


def main(
    argv: Optional[List[str]] = None,
    sanitizer: Optional[PrivacySanitizer] = None,
) -> int:
    enable_high_dpi_awareness()
    parser = argparse.ArgumentParser(
        description="ai-privacy-sanitizer: 100% Local Clipboard & CLI Privacy Sanitizer & Restorer"
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
        help="Read raw text from stdin, write sanitized text to stdout and summary to stderr",
    )
    parser.add_argument(
        "--restore-stdin",
        action="store_true",
        help="Read sanitized text from stdin, write restored text to stdout and summary to stderr",
    )
    parser.add_argument(
        "--file",
        type=str,
        default="",
        help="Path to input file to sanitize locally",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Optional path to output file (used with --file; defaults to stdout if omitted)",
    )
    parser.add_argument(
        "--vault-file",
        type=str,
        default="",
        help="Optional path to save/load session vault mappings for cross-process CLI restoration",
    )
    args = parser.parse_args(argv)

    if args.export_ico:
        export_shield_ico(Path(args.export_ico))
        return 0

    if args.self_test:
        return run_self_test()

    if args.stdin or args.restore_stdin or args.file:
        _configure_stdio_utf8()
        active_sanitizer = sanitizer or PrivacySanitizer()
        vault_path = Path(args.vault_file) if args.vault_file else None
        if vault_path is not None and vault_path.exists():
            active_sanitizer.vault.load_from_file(vault_path)

        if args.stdin:
            raw_input = sys.stdin.read() if sys.stdin is not None else ""
            san_res = active_sanitizer.sanitize(raw_input)
            if vault_path is not None:
                active_sanitizer.vault.save_to_file(vault_path)
            if sys.stdout is not None:
                sys.stdout.write(san_res.sanitized_text)
                sys.stdout.flush()
            if sys.stderr is not None:
                sys.stderr.write(f"{san_res.format_summary(active_sanitizer.language)}\n")
                sys.stderr.flush()
            return 0

        if args.restore_stdin:
            raw_input = sys.stdin.read() if sys.stdin is not None else ""
            res_res = active_sanitizer.restore(raw_input)
            if sys.stdout is not None:
                sys.stdout.write(res_res.restored_text)
                sys.stdout.flush()
            if sys.stderr is not None:
                sys.stderr.write(f"{res_res.format_summary(active_sanitizer.language)}\n")
                sys.stderr.flush()
            return 0

        if args.file:
            in_path = Path(args.file)
            raw_input = in_path.read_text(encoding="utf-8")
            san_res = active_sanitizer.sanitize(raw_input)
            if vault_path is not None:
                active_sanitizer.vault.save_to_file(vault_path)
            if args.output:
                out_path = Path(args.output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(san_res.sanitized_text, encoding="utf-8")
            elif sys.stdout is not None:
                sys.stdout.write(san_res.sanitized_text)
                sys.stdout.flush()
            if sys.stderr is not None:
                sys.stderr.write(f"{san_res.format_summary(active_sanitizer.language)}\n")
                sys.stderr.flush()
            return 0

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
