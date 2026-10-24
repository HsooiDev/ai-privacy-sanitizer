"""Modern Dark/Light Bilingual (Simplified Chinese & English) GUI Control Center using CustomTkinter."""

import ctypes
import io
import json
from pathlib import Path
import platform
import queue
import re
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from src import __version__
from src.i18n import tr
from src.rules import BUILTIN_RULES, SAMPLE_TEST_PAYLOAD
from src.sanitizer import PrivacySanitizer
from src.startup import is_startup_enabled, set_startup_enabled


def enable_high_dpi_awareness() -> None:
    """Enable Windows Per-Monitor High-DPI awareness so fonts and widgets render razor-sharp."""
    if platform.system() != "Windows":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


CATEGORY_KEYS = ["COMPANY", "CLIENT", "PROJECT", "CUSTOM_SECRET"]

CATEGORY_BADGE_COLORS: Dict[str, tuple] = {
    "COMPANY": ("#dbeafe", "#1e3a8a"),
    "CLIENT": ("#fce7f3", "#831843"),
    "PROJECT": ("#fef3c7", "#78350f"),
    "CUSTOM_SECRET": ("#ede9fe", "#4c1d95"),
}


class GuiController:
    """Thread-safe CustomTkinter GUI manager that hides to tray on close and re-opens on demand."""

    def __init__(
        self,
        sanitizer: PrivacySanitizer,
        icon_factory: Optional[Callable[[int], object]] = None,
        on_sanitize_clipboard: Optional[Callable[[], None]] = None,
        on_restore_clipboard: Optional[Callable[[], None]] = None,
        on_undo_sanitize: Optional[Callable[[], None]] = None,
        on_open_raw_config: Optional[Callable[[], None]] = None,
        on_exit_app: Optional[Callable[[], None]] = None,
        on_reload_hotkeys: Optional[Callable[[], bool]] = None,
        on_language_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.sanitizer = sanitizer
        self.icon_factory = icon_factory
        self.on_sanitize_clipboard = on_sanitize_clipboard
        self.on_restore_clipboard = on_restore_clipboard
        self.on_undo_sanitize = on_undo_sanitize
        self.on_open_raw_config = on_open_raw_config
        self.on_exit_app = on_exit_app
        self.on_reload_hotkeys = on_reload_hotkeys
        self.on_language_changed = on_language_changed
        self._cmd_queue: "queue.Queue[str]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()

    def ensure_started(self) -> None:
        """No-op when running on main thread via `run_main_loop`; starts thread only if used headless."""
        pass

    def show_window(self) -> None:
        """Request the GUI window to appear on the Home Dashboard."""
        self._cmd_queue.put("SHOW")

    def show_json_editor(self) -> None:
        """Request the GUI window to appear and open the built-in JSON editor modal."""
        self._cmd_queue.put("SHOW_JSON")

    def shutdown(self) -> None:
        """Request the CustomTkinter loop to terminate cleanly."""
        self._cmd_queue.put("QUIT")

    def run_main_loop(self, show_on_start: bool = True) -> None:
        """Run CustomTkinter on the main thread (recommended for Windows DWM & OLE dialogs)."""
        enable_high_dpi_awareness()
        ctk.set_default_color_theme("blue")
        initial_theme = "Light" if self.sanitizer.theme == "light" else "Dark"
        ctk.set_appearance_mode(initial_theme)

        root = ctk.CTk()
        if not show_on_start:
            root.withdraw()

        app_win = _ModernControlCenter(
            root=root,
            sanitizer=self.sanitizer,
            icon_factory=self.icon_factory,
            on_sanitize_clipboard=self.on_sanitize_clipboard,
            on_restore_clipboard=self.on_restore_clipboard,
            on_undo_sanitize=self.on_undo_sanitize,
            on_exit_app=self.on_exit_app,
            on_reload_hotkeys=self.on_reload_hotkeys,
            on_language_changed=self.on_language_changed,
        )
        if show_on_start:
            root.after(80, app_win.present)

        self._started.set()

        def _poll_commands() -> None:
            try:
                while True:
                    cmd = self._cmd_queue.get_nowait()
                    if cmd == "SHOW":
                        app_win.present()
                    elif cmd == "SHOW_JSON":
                        app_win.present()
                        app_win.open_in_app_json_modal()
                    elif cmd == "QUIT":
                        root.quit()
                        root.destroy()
                        return
            except queue.Empty:
                pass
            root.after(120, _poll_commands)

        root.after(120, _poll_commands)
        root.mainloop()


class _ModernControlCenter:
    """Sleek modern Dark/Light bilingual desktop UI built with CustomTkinter."""

    def __init__(
        self,
        root: ctk.CTk,
        sanitizer: PrivacySanitizer,
        icon_factory: Optional[Callable[[int], object]] = None,
        on_sanitize_clipboard: Optional[Callable[[], None]] = None,
        on_restore_clipboard: Optional[Callable[[], None]] = None,
        on_undo_sanitize: Optional[Callable[[], None]] = None,
        on_exit_app: Optional[Callable[[], None]] = None,
        on_reload_hotkeys: Optional[Callable[[], bool]] = None,
        on_language_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.root = root
        self.sanitizer = sanitizer
        self.on_sanitize_clipboard = on_sanitize_clipboard
        self.on_restore_clipboard = on_restore_clipboard
        self.on_undo_sanitize = on_undo_sanitize
        self.on_exit_app = on_exit_app
        self.on_reload_hotkeys = on_reload_hotkeys
        self.on_language_changed = on_language_changed
        self._tk_icon = None
        self._json_modal: Optional[ctk.CTkToplevel] = None
        self._active_page_key: str = "home"
        self._dict_submode: str = "words"
        self._reveal_vault_originals: bool = False
        self._recording_target: Optional[str] = None

        self.lang = self.sanitizer.language
        self.theme_mode = self.sanitizer.theme

        self.root.title(f"{tr(self.lang, 'window_title')} v{__version__}")
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        if icon_factory is not None:
            try:
                pil_img = icon_factory(64)
                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                self._tk_icon = tk.PhotoImage(data=buf.getvalue())
                self.root.iconphoto(True, self._tk_icon)
            except Exception:
                pass

        width, height = 940, 660
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        pos_x = max(20, (screen_w - width) // 2)
        pos_y = max(20, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        self.root.minsize(860, 600)

        self.font_title = ctk.CTkFont(family="Microsoft YaHei UI", size=20, weight="bold")
        self.font_h2 = ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold")
        self.font_h3 = ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold")
        self.font_body = ctk.CTkFont(family="Microsoft YaHei UI", size=12)
        self.font_small = ctk.CTkFont(family="Microsoft YaHei UI", size=11)
        self.font_stat_num = ctk.CTkFont(family="Microsoft YaHei UI", size=26, weight="bold")
        self.font_mono = ctk.CTkFont(family="Consolas", size=12)

        self._main_container: Optional[ctk.CTkFrame] = None
        self._build_layout()

    def _t(self, key: str) -> str:
        return tr(self.lang, key)

    def _cat_label(self, cat_key: str) -> str:
        mapping = {
            "ALL": self._t("cat_all"),
            "COMPANY": self._t("cat_company"),
            "CLIENT": self._t("cat_client"),
            "PROJECT": self._t("cat_project"),
            "CUSTOM_SECRET": self._t("cat_secret"),
        }
        return mapping.get(cat_key, cat_key)

    def _label_to_cat(self, label: str) -> str:
        for k in ["ALL"] + CATEGORY_KEYS:
            if self._cat_label(k) == label:
                return k
        return "COMPANY"

    def _build_layout(self) -> None:
        if self._main_container is not None:
            self._main_container.destroy()

        self.root.title(f"{self._t('window_title')} v{__version__}")
        self.status_var = tk.StringVar(value=f"{self._t('status_ready')} · v{__version__}")
        self._main_container = ctk.CTkFrame(
            self.root,
            fg_color=("#f1f5f9", "#0b0f19"),
            corner_radius=0,
        )
        self._main_container.pack(fill="both", expand=True)

        # --- 1. Top App Bar ---
        header = ctk.CTkFrame(
            self._main_container,
            fg_color=("#ffffff", "#111827"),
            corner_radius=0,
            height=68,
        )
        header.pack(fill="x", padx=0, pady=0)

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=22, pady=12)

        brand_box = ctk.CTkFrame(header_inner, fg_color="transparent")
        brand_box.pack(side="left")

        ctk.CTkLabel(
            brand_box,
            text=f"🛡️ {self._t('brand_title')} v{__version__}",
            font=self.font_title,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            brand_box,
            text=self._t("brand_subtitle"),
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(anchor="w")

        # Right side controls: Theme & Language switchers
        controls_box = ctk.CTkFrame(header_inner, fg_color="transparent")
        controls_box.pack(side="right")

        theme_btn_text = (
            self._t("btn_theme_light")
            if self.theme_mode == "dark"
            else self._t("btn_theme_dark")
        )
        ctk.CTkButton(
            controls_box,
            text=theme_btn_text,
            font=self.font_body,
            width=110,
            height=34,
            corner_radius=8,
            fg_color=("#e2e8f0", "#1e293b"),
            hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._toggle_theme,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            controls_box,
            text=self._t("btn_lang"),
            font=self.font_body,
            width=105,
            height=34,
            corner_radius=8,
            fg_color=("#e2e8f0", "#1e293b"),
            hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._toggle_language,
        ).pack(side="right")

        # --- 2. Navigation Bar (Segmented Pill Selector) ---
        nav_frame = ctk.CTkFrame(self._main_container, fg_color="transparent")
        nav_frame.pack(fill="x", padx=22, pady=(12, 8))

        self._nav_keys = ["home", "sandbox", "dict", "vault", "guide"]
        self._nav_labels = [
            self._t("nav_home"),
            self._t("nav_sandbox"),
            self._t("nav_dict"),
            self._t("nav_vault"),
            self._t("nav_guide"),
        ]
        self._label_to_nav_key = dict(zip(self._nav_labels, self._nav_keys))
        self._nav_key_to_label = dict(zip(self._nav_keys, self._nav_labels))

        self.nav_bar = ctk.CTkSegmentedButton(
            nav_frame,
            values=self._nav_labels,
            font=self.font_h3,
            height=38,
            corner_radius=10,
            selected_color=("#2563eb", "#2563eb"),
            selected_hover_color=("#1d4ed8", "#1d4ed8"),
            unselected_color=("#e2e8f0", "#1e293b"),
            unselected_hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._on_nav_selected,
        )
        self.nav_bar.pack(fill="x")

        # --- 3. Page Content Container ---
        self.page_container = ctk.CTkFrame(
            self._main_container,
            fg_color="transparent",
        )
        self.page_container.pack(fill="both", expand=True, padx=22, pady=4)

        self.pages: Dict[str, ctk.CTkFrame] = {}
        self._build_page_home()
        self._build_page_sandbox()
        self._build_page_dict()
        self._build_page_vault()
        self._build_page_guide()

        # --- 4. Bottom Status Bar ---
        footer = ctk.CTkFrame(
            self._main_container,
            fg_color=("#ffffff", "#111827"),
            corner_radius=0,
            height=46,
        )
        footer.pack(fill="x", side="bottom")

        ctk.CTkLabel(
            footer,
            textvariable=self.status_var,
            font=self.font_body,
            text_color=("#0284c7", "#38bdf8"),
        ).pack(side="left", padx=22, pady=8)

        ctk.CTkButton(
            footer,
            text=self._t("btn_exit_app"),
            font=self.font_small,
            width=125,
            height=30,
            corner_radius=8,
            fg_color=("#dc2626", "#991b1b"),
            hover_color=("#b91c1c", "#7f1d1d"),
            text_color="#ffffff",
            command=self._trigger_exit_app,
        ).pack(side="right", padx=(8, 22), pady=8)

        ctk.CTkButton(
            footer,
            text=self._t("btn_hide_tray"),
            font=self.font_small,
            width=120,
            height=30,
            corner_radius=8,
            fg_color=("#e2e8f0", "#1e293b"),
            hover_color=("#cbd5e1", "#334155"),
            text_color=("#0f172a", "#f8fafc"),
            command=self.hide,
        ).pack(side="right", padx=(0, 4), pady=8)

        # Select active page
        target_label = self._nav_key_to_label.get(self._active_page_key, self._nav_labels[0])
        self.nav_bar.set(target_label)
        self._show_page(self._active_page_key)

    # ---------------- Page 1: Home Dashboard ----------------

    def _build_page_home(self) -> None:
        page = ctk.CTkScrollableFrame(
            self.page_container,
            fg_color="transparent",
        )
        self.pages["home"] = page

        # Hero Card (Zero-Config Ready)
        hero = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#131c31"),
            corner_radius=14,
            border_width=1,
            border_color=("#10b981", "#059669"),
        )
        hero.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(
            hero,
            text=self._t("hero_badge"),
            font=self.font_h2,
            text_color=("#059669", "#34d399"),
        ).pack(anchor="w", padx=20, pady=(16, 6))

        ctk.CTkLabel(
            hero,
            text=self._t("hero_desc"),
            font=self.font_body,
            text_color=("#334155", "#cbd5e1"),
            justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 14))

        btn_row = ctk.CTkFrame(hero, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        hk = self.sanitizer.hotkeys
        san_disp = hk.get("sanitize", "alt+s").upper()
        res_disp = hk.get("restore", "alt+r").upper()

        self.btn_hero_san = ctk.CTkButton(
            btn_row,
            text=re.sub(r"\(Alt\s*\+\s*S\)", f"({san_disp})", self._t("btn_hero_sanitize")),
            font=self.font_h3,
            height=44,
            corner_radius=10,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            text_color="#ffffff",
            command=self._trigger_sanitize_clipboard,
        )
        self.btn_hero_san.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_hero_res = ctk.CTkButton(
            btn_row,
            text=re.sub(r"\(Alt\s*\+\s*R\)", f"({res_disp})", self._t("btn_hero_restore")),
            font=self.font_h3,
            height=44,
            corner_radius=10,
            fg_color=("#2563eb", "#2563eb"),
            hover_color=("#1d4ed8", "#1d4ed8"),
            text_color="#ffffff",
            command=self._trigger_restore_clipboard,
        )
        self.btn_hero_res.pack(side="left", fill="x", expand=True, padx=(8, 8))

        self.btn_hero_undo = ctk.CTkButton(
            btn_row,
            text=self._t("btn_hero_undo"),
            font=self.font_h3,
            width=155,
            height=44,
            corner_radius=10,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            text_color="#ffffff",
            command=self._trigger_undo_sanitize,
        )
        self.btn_hero_undo.pack(side="left", padx=(0, 0))

        # 3 Stat Cards Row
        stats_row = ctk.CTkFrame(page, fg_color="transparent")
        stats_row.pack(fill="x", pady=(0, 12))
        stats_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.lbl_stat_hits = self._create_stat_card(
            stats_row,
            col=0,
            title=self._t("stat_intercepted_title"),
            value=str(self.sanitizer.vault.total_intercepted_hits),
            unit=self._t("stat_intercepted_unit"),
            accent=("#059669", "#34d399"),
        )
        self.lbl_stat_vault = self._create_stat_card(
            stats_row,
            col=1,
            title=self._t("stat_vault_title"),
            value=str(self.sanitizer.vault.size),
            unit=self._t("stat_vault_unit"),
            accent=("#2563eb", "#60a5fa"),
        )
        self._create_stat_card(
            stats_row,
            col=2,
            title=self._t("stat_rules_title"),
            value=str(len(BUILTIN_RULES)),
            unit=self._t("stat_rules_unit"),
            accent=("#7c3aed", "#a78bfa"),
        )

        # Toggle Switches Card
        sw_card = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=14,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        sw_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            sw_card,
            text=self._t("switches_section_title"),
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w", padx=18, pady=(14, 6))

        self.var_auto_sanitize = tk.BooleanVar(value=self.sanitizer.auto_sanitize_clipboard)
        self.var_semantic_ip = tk.BooleanVar(value=self.sanitizer.semantic_ip_mode)
        self.var_startup = tk.BooleanVar(value=is_startup_enabled())

        self._create_switch_row(
            sw_card,
            title=self._t("sw_cruise_title"),
            desc=self._t("sw_cruise_desc"),
            variable=self.var_auto_sanitize,
            command=self._on_toggle_auto_sanitize,
        )
        self._create_switch_row(
            sw_card,
            title=self._t("sw_semantic_title"),
            desc=self._t("sw_semantic_desc"),
            variable=self.var_semantic_ip,
            command=self._on_toggle_semantic_ip,
        )
        self._create_switch_row(
            sw_card,
            title=self._t("sw_startup_title"),
            desc=self._t("sw_startup_desc"),
            variable=self.var_startup,
            command=self._on_toggle_startup,
        )

        # Custom Global Hotkeys Card
        hk_card = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=14,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        hk_card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            hk_card,
            text=self._t("hotkey_section_title"),
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w", padx=18, pady=(12, 2))

        ctk.CTkLabel(
            hk_card,
            text=self._t("hotkey_section_desc"),
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(anchor="w", padx=18, pady=(0, 8))

        hk_row = ctk.CTkFrame(hk_card, fg_color="transparent")
        hk_row.pack(fill="x", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            hk_row,
            text=self._t("lbl_hk_sanitize"),
            font=self.font_body,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(side="left")

        self.combo_hk_sanitize = ctk.CTkComboBox(
            hk_row,
            values=["alt+s", "ctrl+shift+s", "ctrl+alt+s", "alt+q", "f8", "ctrl+f8"],
            width=125,
            height=32,
            font=self.font_mono,
        )
        self.combo_hk_sanitize.set(hk.get("sanitize", "alt+s"))
        self.combo_hk_sanitize.pack(side="left", padx=(4, 6))

        self.btn_rec_san = ctk.CTkButton(
            hk_row,
            text=self._t("btn_hk_record"),
            font=self.font_small,
            width=92,
            height=32,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=lambda: self._start_hotkey_recording("sanitize"),
        )
        self.btn_rec_san.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(
            hk_row,
            text=self._t("lbl_hk_restore"),
            font=self.font_body,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(side="left")

        self.combo_hk_restore = ctk.CTkComboBox(
            hk_row,
            values=["alt+r", "ctrl+shift+r", "ctrl+alt+r", "alt+w", "f9", "ctrl+f9"],
            width=125,
            height=32,
            font=self.font_mono,
        )
        self.combo_hk_restore.set(hk.get("restore", "alt+r"))
        self.combo_hk_restore.pack(side="left", padx=(4, 6))

        self.btn_rec_res = ctk.CTkButton(
            hk_row,
            text=self._t("btn_hk_record"),
            font=self.font_small,
            width=92,
            height=32,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=lambda: self._start_hotkey_recording("restore"),
        )
        self.btn_rec_res.pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            hk_row,
            text=self._t("btn_hk_save"),
            font=self.font_small,
            width=118,
            height=32,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            text_color="#ffffff",
            command=self._save_and_apply_hotkeys,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            hk_row,
            text=self._t("btn_hk_reset"),
            font=self.font_small,
            width=80,
            height=32,
            corner_radius=8,
            fg_color=("#e2e8f0", "#334155"),
            hover_color=("#cbd5e1", "#475569"),
            text_color=("#0f172a", "#f8fafc"),
            command=self._reset_default_hotkeys,
        ).pack(side="left")

        # Workflow Banner
        wf_card = ctk.CTkFrame(
            page,
            fg_color=("#e0f2fe", "#0f172a"),
            corner_radius=12,
            border_width=1,
            border_color=("#bae6fd", "#1e3a8a"),
        )
        wf_card.pack(fill="x", pady=(0, 6))

        wf_text = (
            f"{self._t('workflow_title')}：{self._t('workflow_steps')}"
            .replace("Alt+S", san_disp)
            .replace("Alt+R", res_disp)
        )
        self.lbl_workflow = ctk.CTkLabel(
            wf_card,
            text=wf_text,
            font=self.font_body,
            text_color=("#0369a1", "#7dd3fc"),
        )
        self.lbl_workflow.pack(padx=16, pady=10)

    def _create_stat_card(
        self,
        parent: ctk.CTkFrame,
        col: int,
        title: str,
        value: str,
        unit: str,
        accent: tuple,
    ) -> ctk.CTkLabel:
        padx = (0, 6) if col == 0 else ((6, 6) if col == 1 else (6, 0))
        card = ctk.CTkFrame(
            parent,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        card.grid(row=0, column=col, sticky="ew", padx=padx)

        ctk.CTkLabel(
            card,
            text=title,
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(anchor="w", padx=16, pady=(10, 2))

        val_row = ctk.CTkFrame(card, fg_color="transparent")
        val_row.pack(anchor="w", padx=16, pady=(0, 10))

        num_lbl = ctk.CTkLabel(
            val_row,
            text=value,
            font=self.font_stat_num,
            text_color=accent,
        )
        num_lbl.pack(side="left")

        ctk.CTkLabel(
            val_row,
            text=f"  {unit}",
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(side="left", pady=(6, 0))

        return num_lbl

    def _create_switch_row(
        self,
        parent: ctk.CTkFrame,
        title: str,
        desc: str,
        variable: tk.BooleanVar,
        command: Callable[[], None],
    ) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=6)

        txt_box = ctk.CTkFrame(row, fg_color="transparent")
        txt_box.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            txt_box,
            text=title,
            font=self.font_body,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            txt_box,
            text=desc,
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(anchor="w")

        ctk.CTkSwitch(
            row,
            text="",
            variable=variable,
            onvalue=True,
            offvalue=False,
            progress_color=("#059669", "#10b981"),
            command=command,
            width=48,
        ).pack(side="right", padx=(12, 0))

    # ---------------- Page 2: Live Sandbox ----------------

    def _build_page_sandbox(self) -> None:
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["sandbox"] = page

        toolbar = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        toolbar.pack(fill="x", pady=(2, 8))

        tb_inner = ctk.CTkFrame(toolbar, fg_color="transparent")
        tb_inner.pack(fill="x", padx=12, pady=8)

        ctk.CTkButton(
            tb_inner,
            text=self._t("btn_load_sample"),
            font=self.font_body,
            height=34,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=self._load_sample_into_sandbox,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            tb_inner,
            text=self._t("btn_run_sanitize"),
            font=self.font_h3,
            height=34,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            command=self._run_sandbox_sanitize,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            tb_inner,
            text=self._t("btn_run_restore"),
            font=self.font_body,
            height=34,
            corner_radius=8,
            fg_color=("#2563eb", "#2563eb"),
            hover_color=("#1d4ed8", "#1d4ed8"),
            command=self._run_sandbox_restore,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            tb_inner,
            text=self._t("btn_copy_output"),
            font=self.font_body,
            height=34,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=self._copy_sandbox_output,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            tb_inner,
            text=self._t("btn_clear_sandbox"),
            font=self.font_body,
            width=80,
            height=34,
            corner_radius=8,
            fg_color=("#dc2626", "#991b1b"),
            hover_color=("#b91c1c", "#7f1d1d"),
            command=self._clear_sandbox,
        ).pack(side="right")

        # Category Breakdown Pill Bar
        self.sandbox_cat_bar = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=10,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
            height=36,
        )
        self.sandbox_cat_bar.pack(fill="x", pady=(0, 8))

        self.sandbox_cat_inner = ctk.CTkFrame(self.sandbox_cat_bar, fg_color="transparent")
        self.sandbox_cat_inner.pack(fill="x", padx=12, pady=5)

        ctk.CTkLabel(
            self.sandbox_cat_inner,
            text=self._t("sandbox_cat_empty"),
            font=self.font_small,
            text_color=("#64748b", "#94a3b8"),
        ).pack(side="left")

        panes = ctk.CTkFrame(page, fg_color="transparent")
        panes.pack(fill="both", expand=True)
        panes.grid_columnconfigure((0, 1), weight=1)
        panes.grid_rowconfigure(0, weight=1)

        left_card = ctk.CTkFrame(
            panes,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(
            left_card,
            text=self._t("sandbox_left_title"),
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w", padx=12, pady=(8, 4))

        self.sandbox_input = ctk.CTkTextbox(
            left_card,
            font=self.font_mono,
            fg_color=("#f8fafc", "#0f172a"),
            text_color=("#0f172a", "#e2e8f0"),
            corner_radius=8,
            wrap="word",
        )
        self.sandbox_input.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._sandbox_debounce_id: Optional[str] = None
        self.sandbox_input.bind("<KeyRelease>", self._on_sandbox_input_changed)

        right_card = ctk.CTkFrame(
            panes,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        right_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        ctk.CTkLabel(
            right_card,
            text=self._t("sandbox_right_title"),
            font=self.font_h3,
            text_color=("#059669", "#34d399"),
        ).pack(anchor="w", padx=12, pady=(8, 4))

        self.sandbox_output = ctk.CTkTextbox(
            right_card,
            font=self.font_mono,
            fg_color=("#f8fafc", "#0f172a"),
            text_color=("#0f172a", "#e2e8f0"),
            corner_radius=8,
            wrap="word",
        )
        self.sandbox_output.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._configure_sandbox_highlight_tag()
        self.sandbox_input.insert("1.0", SAMPLE_TEST_PAYLOAD.strip())

    def _configure_sandbox_highlight_tag(self) -> None:
        inner_text = getattr(self.sandbox_output, "_textbox", None)
        if inner_text is not None:
            if self.theme_mode == "dark":
                inner_text.tag_configure(
                    "placeholder_tag",
                    background="#064e3b",
                    foreground="#6ee7b7",
                )
            else:
                inner_text.tag_configure(
                    "placeholder_tag",
                    background="#d1fae5",
                    foreground="#065f46",
                )

    # ---------------- Page 3: Custom Words & Allowlist / Rules ----------------

    def _build_page_dict(self) -> None:
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["dict"] = page

        # Top Segmented Switcher: Custom Words vs Allowlist & Built-in Rules
        mode_bar = ctk.CTkFrame(page, fg_color="transparent")
        mode_bar.pack(fill="x", pady=(0, 6))

        self._dict_mode_labels = [
            self._t("dict_mode_words"),
            self._t("dict_mode_rules"),
        ]
        self.dict_mode_seg = ctk.CTkSegmentedButton(
            mode_bar,
            values=self._dict_mode_labels,
            font=self.font_h3,
            height=34,
            corner_radius=8,
            selected_color=("#059669", "#059669"),
            selected_hover_color=("#047857", "#047857"),
            command=self._on_dict_submode_selected,
        )
        self.dict_mode_seg.pack(fill="x")

        # Sub-container 1: Custom Words
        self.dict_words_pane = ctk.CTkFrame(page, fg_color="transparent")

        banner = ctk.CTkFrame(
            self.dict_words_pane,
            fg_color=("#eff6ff", "#172554"),
            corner_radius=12,
            border_width=1,
            border_color=("#bfdbfe", "#1e40af"),
        )
        banner.pack(fill="x", pady=(2, 8))

        ctk.CTkLabel(
            banner,
            text=self._t("dict_banner_title"),
            font=self.font_h3,
            text_color=("#1d4ed8", "#93c5fd"),
        ).pack(anchor="w", padx=14, pady=(8, 2))

        ctk.CTkLabel(
            banner,
            text=self._t("dict_banner_desc"),
            font=self.font_small,
            text_color=("#1e40af", "#bfdbfe"),
        ).pack(anchor="w", padx=14, pady=(0, 8))

        add_card = ctk.CTkFrame(
            self.dict_words_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        add_card.pack(fill="x", pady=(0, 8))

        add_row = ctk.CTkFrame(add_card, fg_color="transparent")
        add_row.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(
            add_row,
            text=self._t("lbl_add_cat"),
            font=self.font_body,
        ).pack(side="left")

        cat_values = [self._cat_label(k) for k in CATEGORY_KEYS]
        self.add_cat_combo = ctk.CTkComboBox(
            add_row,
            values=cat_values,
            font=self.font_body,
            width=210,
            state="readonly",
        )
        self.add_cat_combo.set(cat_values[0])
        self.add_cat_combo.pack(side="left", padx=(6, 10))

        self.entry_new_word = ctk.CTkEntry(
            add_row,
            placeholder_text=self._t("placeholder_add_word"),
            font=self.font_body,
            height=34,
        )
        self.entry_new_word.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_new_word.bind("<Return>", lambda _e: self._add_word())

        ctk.CTkButton(
            add_row,
            text=self._t("btn_add_word"),
            font=self.font_h3,
            width=110,
            height=34,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            command=self._add_word,
        ).pack(side="left")

        tools_row = ctk.CTkFrame(self.dict_words_pane, fg_color="transparent")
        tools_row.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            tools_row,
            text=self._t("lbl_filter_cat"),
            font=self.font_body,
        ).pack(side="left")

        filter_values = [self._cat_label("ALL")] + cat_values
        self.filter_cat_combo = ctk.CTkComboBox(
            tools_row,
            values=filter_values,
            font=self.font_body,
            width=210,
            state="readonly",
            command=lambda _v: self.refresh_dictionary_list(),
        )
        self.filter_cat_combo.set(filter_values[0])
        self.filter_cat_combo.pack(side="left", padx=(6, 10))

        ctk.CTkButton(
            tools_row,
            text=self._t("btn_clear_all_dict"),
            font=self.font_small,
            height=30,
            corner_radius=8,
            fg_color=("#dc2626", "#991b1b"),
            hover_color=("#b91c1c", "#7f1d1d"),
            command=self._clear_all_custom_words,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            tools_row,
            text=self._t("btn_export"),
            font=self.font_small,
            width=80,
            height=30,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=self._export_dictionary,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            tools_row,
            text=self._t("btn_import"),
            font=self.font_small,
            width=80,
            height=30,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=self._import_dictionary,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            tools_row,
            text=self._t("btn_json_editor"),
            font=self.font_small,
            height=30,
            corner_radius=8,
            fg_color=("#2563eb", "#2563eb"),
            hover_color=("#1d4ed8", "#1d4ed8"),
            command=self.open_in_app_json_modal,
        ).pack(side="right")

        self.dict_scroll = ctk.CTkScrollableFrame(
            self.dict_words_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        self.dict_scroll.pack(fill="both", expand=True)

        # Sub-container 2: Allowlist & Built-in Rule Toggles
        self.dict_rules_pane = ctk.CTkFrame(page, fg_color="transparent")
        self.dict_rules_pane.grid_columnconfigure((0, 1), weight=1)
        self.dict_rules_pane.grid_rowconfigure(0, weight=1)

        allow_card = ctk.CTkFrame(
            self.dict_rules_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        allow_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=2)

        ctk.CTkLabel(
            allow_card,
            text=self._t("allowlist_title"),
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w", padx=12, pady=(10, 6))

        allow_in_row = ctk.CTkFrame(allow_card, fg_color="transparent")
        allow_in_row.pack(fill="x", padx=12, pady=(0, 8))

        self.entry_allowlist = ctk.CTkEntry(
            allow_in_row,
            placeholder_text=self._t("placeholder_allowlist"),
            font=self.font_body,
            height=32,
        )
        self.entry_allowlist.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_allowlist.bind("<Return>", lambda _e: self._add_allowlist_from_gui())

        ctk.CTkButton(
            allow_in_row,
            text=self._t("btn_add_allowlist"),
            font=self.font_small,
            width=110,
            height=32,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            command=self._add_allowlist_from_gui,
        ).pack(side="left")

        self.allowlist_scroll = ctk.CTkScrollableFrame(
            allow_card,
            fg_color=("#f8fafc", "#0f172a"),
            corner_radius=8,
        )
        self.allowlist_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        rules_card = ctk.CTkFrame(
            self.dict_rules_pane,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        rules_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=2)

        ctk.CTkLabel(
            rules_card,
            text=self._t("rules_toggle_title"),
            font=self.font_h3,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(anchor="w", padx=12, pady=(10, 6))

        self.rules_toggle_scroll = ctk.CTkScrollableFrame(
            rules_card,
            fg_color=("#f8fafc", "#0f172a"),
            corner_radius=8,
        )
        self.rules_toggle_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        initial_dict_label = (
            self._dict_mode_labels[1]
            if self._dict_submode == "rules"
            else self._dict_mode_labels[0]
        )
        self.dict_mode_seg.set(initial_dict_label)
        self._show_dict_submode(self._dict_submode)

    # ---------------- Page 4: Session Vault ----------------

    def _build_page_vault(self) -> None:
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["vault"] = page

        top_bar = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        top_bar.pack(fill="x", pady=(2, 8))

        bar_inner = ctk.CTkFrame(top_bar, fg_color="transparent")
        bar_inner.pack(fill="x", padx=12, pady=8)

        self.vault_search_var = tk.StringVar()
        self.vault_search_var.trace_add("write", lambda *_a: self.refresh_vault_list())
        ctk.CTkEntry(
            bar_inner,
            textvariable=self.vault_search_var,
            placeholder_text=self._t("placeholder_search_vault"),
            font=self.font_body,
            width=220,
            height=32,
        ).pack(side="left", padx=(0, 10))

        self.var_reveal_vault = tk.BooleanVar(value=self._reveal_vault_originals)
        ctk.CTkSwitch(
            bar_inner,
            text=self._t("sw_reveal_vault"),
            font=self.font_small,
            variable=self.var_reveal_vault,
            onvalue=True,
            offvalue=False,
            progress_color=("#059669", "#10b981"),
            command=self._on_toggle_reveal_vault,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            bar_inner,
            text=self._t("btn_clear_vault"),
            font=self.font_small,
            height=32,
            corner_radius=8,
            fg_color=("#dc2626", "#991b1b"),
            hover_color=("#b91c1c", "#7f1d1d"),
            command=self._clear_vault_from_gui,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            bar_inner,
            text=self._t("btn_refresh_vault"),
            font=self.font_small,
            width=90,
            height=32,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=self.refresh_vault_list,
        ).pack(side="right")

        self.vault_scroll = ctk.CTkScrollableFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        self.vault_scroll.pack(fill="both", expand=True)

    # ---------------- Page 5: Quick Guide ----------------

    def _build_page_guide(self) -> None:
        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        self.pages["guide"] = page

        guide_card = ctk.CTkFrame(
            page,
            fg_color=("#ffffff", "#1e293b"),
            corner_radius=12,
            border_width=1,
            border_color=("#e2e8f0", "#334155"),
        )
        guide_card.pack(fill="both", expand=True, pady=2)

        guide_box = ctk.CTkTextbox(
            guide_card,
            font=self.font_body,
            fg_color="transparent",
            text_color=("#0f172a", "#e2e8f0"),
            wrap="word",
        )
        guide_box.pack(fill="both", expand=True, padx=16, pady=12)
        guide_box.insert("1.0", self._t("tutorial_body").strip())
        guide_box.configure(state="disabled")

    # ---------------- In-App JSON Editor Modal ----------------

    def open_in_app_json_modal(self) -> None:
        """Open a sleek built-in JSON editor modal window inside the app (never external IDE)."""
        if self._json_modal is not None and self._json_modal.winfo_exists():
            self._json_modal.lift()
            self._json_modal.focus_force()
            return

        modal = ctk.CTkToplevel(self.root)
        self._json_modal = modal
        modal.title(self._t("json_modal_title"))
        modal.geometry("720x520")
        modal.transient(self.root)
        modal.lift()
        modal.focus_force()

        ctk.CTkLabel(
            modal,
            text=self._t("json_modal_hint"),
            font=self.font_body,
        ).pack(anchor="w", padx=18, pady=(14, 6))

        editor = ctk.CTkTextbox(
            modal,
            font=self.font_mono,
            fg_color=("#f8fafc", "#0f172a"),
            text_color=("#0f172a", "#e2e8f0"),
            corner_radius=10,
        )
        editor.pack(fill="both", expand=True, padx=18, pady=6)

        cfg_path = self.sanitizer.ensure_config_exists()
        try:
            raw_json = cfg_path.read_text(encoding="utf-8")
        except Exception:
            raw_json = json.dumps(self.sanitizer.reload_config(), indent=2, ensure_ascii=False)
        editor.insert("1.0", raw_json)

        btn_bar = ctk.CTkFrame(modal, fg_color="transparent")
        btn_bar.pack(fill="x", padx=18, pady=(6, 14))

        def _save_json() -> None:
            content = editor.get("1.0", "end").strip()
            try:
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise ValueError("Root JSON must be an object {}")
                self.sanitizer.save_config(parsed)
                self.refresh_all()
                self.status_var.set(self._t("msg_json_saved"))
                messagebox.showinfo("OK", self._t("msg_json_saved"), parent=modal)
                modal.destroy()
            except Exception as exc:
                messagebox.showerror(
                    "JSON Error",
                    f"{self._t('msg_json_err')}{exc}",
                    parent=modal,
                )

        def _reveal_in_explorer() -> None:
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", f"/select,{cfg_path}"])

        ctk.CTkButton(
            btn_bar,
            text=self._t("btn_save_json"),
            font=self.font_h3,
            height=36,
            corner_radius=8,
            fg_color=("#059669", "#059669"),
            hover_color=("#047857", "#047857"),
            command=_save_json,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_bar,
            text=self._t("btn_open_folder"),
            font=self.font_body,
            height=36,
            corner_radius=8,
            fg_color=("#475569", "#334155"),
            hover_color=("#334155", "#475569"),
            command=_reveal_in_explorer,
        ).pack(side="left")

        ctk.CTkButton(
            btn_bar,
            text=self._t("btn_close"),
            font=self.font_body,
            width=90,
            height=36,
            corner_radius=8,
            fg_color=("#64748b", "#334155"),
            command=modal.destroy,
        ).pack(side="right")

    # ---------------- Navigation & Refresh ----------------

    def _on_nav_selected(self, selected_label: str) -> None:
        page_key = self._label_to_nav_key.get(selected_label, "home")
        self._show_page(page_key)

    def _show_page(self, page_key: str) -> None:
        self._active_page_key = page_key
        for k, frame in self.pages.items():
            frame.pack_forget()
        target = self.pages.get(page_key, self.pages["home"])
        target.pack(fill="both", expand=True)
        self.refresh_all()

    def _toggle_language(self) -> None:
        self.lang = "en" if self.lang == "zh" else "zh"
        self.sanitizer.set_language(self.lang)
        if self.on_language_changed:
            self.on_language_changed()
        self._build_layout()

    def _toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self.sanitizer.set_theme(self.theme_mode)
        ctk.set_appearance_mode("Light" if self.theme_mode == "light" else "Dark")
        self._configure_sandbox_highlight_tag()
        self._build_layout()

    def _on_dict_submode_selected(self, label: str) -> None:
        mode = "rules" if label == self._dict_mode_labels[1] else "words"
        self._show_dict_submode(mode)

    def _show_dict_submode(self, mode: str) -> None:
        self._dict_submode = mode
        self.dict_words_pane.pack_forget()
        self.dict_rules_pane.pack_forget()
        if mode == "rules":
            self.dict_rules_pane.pack(fill="both", expand=True)
            self.refresh_allowlist_and_rules_list()
        else:
            self.dict_words_pane.pack(fill="both", expand=True)
            self.refresh_dictionary_list()

    def refresh_all(self) -> None:
        if hasattr(self, "var_startup"):
            self.var_startup.set(is_startup_enabled())
        if hasattr(self, "var_auto_sanitize"):
            self.var_auto_sanitize.set(self.sanitizer.auto_sanitize_clipboard)
        if hasattr(self, "var_semantic_ip"):
            self.var_semantic_ip.set(self.sanitizer.semantic_ip_mode)
        if hasattr(self, "lbl_stat_hits"):
            self.lbl_stat_hits.configure(text=str(self.sanitizer.vault.total_intercepted_hits))
        if hasattr(self, "lbl_stat_vault"):
            self.lbl_stat_vault.configure(text=str(self.sanitizer.vault.size))

        if self._active_page_key == "dict":
            if self._dict_submode == "rules":
                self.refresh_allowlist_and_rules_list()
            else:
                self.refresh_dictionary_list()
        elif self._active_page_key == "vault":
            self.refresh_vault_list()

    def refresh_allowlist_and_rules_list(self) -> None:
        if hasattr(self, "allowlist_scroll"):
            for child in self.allowlist_scroll.winfo_children():
                child.destroy()
            for idx, item in enumerate(self.sanitizer.get_allowlist(), start=1):
                row = ctk.CTkFrame(
                    self.allowlist_scroll,
                    fg_color=("#ffffff", "#1e293b"),
                    corner_radius=6,
                    height=32,
                )
                row.pack(fill="x", padx=4, pady=2)
                ctk.CTkLabel(
                    row,
                    text=f"#{idx}  {item}",
                    font=self.font_mono,
                    text_color=("#0f172a", "#f8fafc"),
                ).pack(side="left", padx=10, pady=4)
                ctk.CTkButton(
                    row,
                    text="✕",
                    font=self.font_small,
                    width=28,
                    height=24,
                    corner_radius=6,
                    fg_color=("#fee2e2", "#7f1d1d"),
                    hover_color=("#fecaca", "#991b1b"),
                    text_color=("#991b1b", "#fecaca"),
                    command=lambda val=item: self._remove_allowlist_from_gui(val),
                ).pack(side="right", padx=6, pady=4)

        if hasattr(self, "rules_toggle_scroll"):
            for child in self.rules_toggle_scroll.winfo_children():
                child.destroy()
            disabled_set = set(self.sanitizer.get_disabled_rules())
            for rule in BUILTIN_RULES:
                row = ctk.CTkFrame(
                    self.rules_toggle_scroll,
                    fg_color=("#ffffff", "#1e293b"),
                    corner_radius=6,
                )
                row.pack(fill="x", padx=4, pady=2)
                var_chk = tk.BooleanVar(
                    value=(rule.enabled_by_default and rule.name not in disabled_set)
                )
                chk = ctk.CTkCheckBox(
                    row,
                    text=f"[{rule.category}] {rule.name}",
                    font=self.font_mono,
                    variable=var_chk,
                    onvalue=True,
                    offvalue=False,
                    checkbox_width=18,
                    checkbox_height=18,
                    command=lambda rname=rule.name, v=var_chk: self._on_toggle_rule_checkbox(
                        rname, bool(v.get())
                    ),
                )
                chk.pack(anchor="w", padx=10, pady=5)

    def _add_allowlist_from_gui(self) -> None:
        raw = self.entry_allowlist.get().strip()
        if not raw:
            return
        candidates = [w.strip() for w in re.split(r"[,，;；\r\n]+", raw) if w.strip()]
        for c in candidates:
            self.sanitizer.add_allowlist_item(c)
        self.entry_allowlist.delete(0, "end")
        self.refresh_allowlist_and_rules_list()

    def _remove_allowlist_from_gui(self, item: str) -> None:
        if self.sanitizer.remove_allowlist_item(item):
            self.refresh_allowlist_and_rules_list()

    def _on_toggle_rule_checkbox(self, rule_name: str, enabled: bool) -> None:
        self.sanitizer.set_rule_enabled(rule_name, enabled)

    def refresh_dictionary_list(self) -> None:
        for child in self.dict_scroll.winfo_children():
            child.destroy()

        filter_cat = self._label_to_cat(self.filter_cat_combo.get())
        custom_dict = self.sanitizer.get_custom_dictionary()

        rows: List[tuple] = []
        if filter_cat == "ALL":
            for ck in CATEGORY_KEYS:
                for w in custom_dict.get(ck, []):
                    rows.append((ck, w))
        else:
            for w in custom_dict.get(filter_cat, []):
                rows.append((filter_cat, w))

        rows.sort(key=lambda item: len(item[1]), reverse=True)

        for idx, (cat_key, word) in enumerate(rows, start=1):
            row_card = ctk.CTkFrame(
                self.dict_scroll,
                fg_color=("#f8fafc", "#0f172a"),
                corner_radius=8,
                height=38,
            )
            row_card.pack(fill="x", padx=4, pady=3)

            ctk.CTkLabel(
                row_card,
                text=f"#{idx}",
                font=self.font_small,
                width=36,
                text_color=("#64748b", "#94a3b8"),
            ).pack(side="left", padx=(8, 4), pady=6)

            badge_color = CATEGORY_BADGE_COLORS.get(cat_key, ("#e2e8f0", "#334155"))
            ctk.CTkLabel(
                row_card,
                text=f" {cat_key} ",
                font=self.font_small,
                fg_color=badge_color,
                text_color=("#0f172a", "#f8fafc"),
                corner_radius=6,
                width=115,
            ).pack(side="left", padx=6, pady=6)

            ctk.CTkLabel(
                row_card,
                text=word,
                font=self.font_body,
                text_color=("#0f172a", "#f8fafc"),
            ).pack(side="left", padx=10, pady=6)

            ctk.CTkButton(
                row_card,
                text="✕",
                font=self.font_small,
                width=30,
                height=26,
                corner_radius=6,
                fg_color=("#fee2e2", "#7f1d1d"),
                hover_color=("#fecaca", "#991b1b"),
                text_color=("#991b1b", "#fecaca"),
                command=lambda c=cat_key, w=word: self._delete_single_word(c, w),
            ).pack(side="right", padx=8, pady=5)

    @staticmethod
    def _mask_secret_preview(value: str) -> str:
        """Mask the middle of a sensitive string (e.g. `sk-proj-***MNO678`) to prevent screen-share leaks."""
        s = value.replace("\n", " ").strip()
        n = len(s)
        if n <= 4:
            return "*" * n
        if n <= 10:
            return f"{s[:2]}***{s[-2:]}"
        return f"{s[:6]}***{s[-4:]}"

    def _on_toggle_reveal_vault(self) -> None:
        self._reveal_vault_originals = bool(self.var_reveal_vault.get())
        self.refresh_vault_list()

    def refresh_vault_list(self) -> None:
        for child in self.vault_scroll.winfo_children():
            child.destroy()

        items = self.sanitizer.vault.snapshot_placeholders()
        keyword = self.vault_search_var.get().strip().lower() if hasattr(self, "vault_search_var") else ""

        filtered = [
            (ph, orig, cat)
            for ph, orig, cat in items
            if not keyword
            or keyword in ph.lower()
            or keyword in orig.lower()
            or keyword in cat.lower()
        ]

        if not filtered:
            ctk.CTkLabel(
                self.vault_scroll,
                text=self._t("vault_empty"),
                font=self.font_body,
                text_color=("#64748b", "#94a3b8"),
            ).pack(pady=40)
            return

        reveal = bool(self._reveal_vault_originals)
        for ph, orig, cat in filtered:
            row_card = ctk.CTkFrame(
                self.vault_scroll,
                fg_color=("#f8fafc", "#0f172a"),
                corner_radius=8,
            )
            row_card.pack(fill="x", padx=4, pady=3)

            ctk.CTkLabel(
                row_card,
                text=f" {ph} ",
                font=self.font_mono,
                fg_color=("#d1fae5", "#064e3b"),
                text_color=("#065f46", "#6ee7b7"),
                corner_radius=6,
                width=180,
            ).pack(side="left", padx=(10, 6), pady=7)

            ctk.CTkLabel(
                row_card,
                text=cat,
                font=self.font_small,
                width=100,
                text_color=("#64748b", "#94a3b8"),
            ).pack(side="left", padx=6, pady=7)

            ctk.CTkLabel(
                row_card,
                text="⟷",
                font=self.font_body,
                text_color=("#64748b", "#94a3b8"),
            ).pack(side="left", padx=6)

            if reveal:
                display_orig = orig if len(orig) <= 56 else orig[:53] + "..."
                display_orig = display_orig.replace("\n", " ")
            else:
                display_orig = self._mask_secret_preview(orig)

            ctk.CTkLabel(
                row_card,
                text=display_orig,
                font=self.font_mono,
                text_color=("#0f172a", "#f8fafc"),
            ).pack(side="left", padx=8, pady=7)

            ctk.CTkButton(
                row_card,
                text=self._t("btn_copy_ph"),
                font=self.font_small,
                width=80,
                height=26,
                corner_radius=6,
                fg_color=("#e2e8f0", "#334155"),
                hover_color=("#cbd5e1", "#475569"),
                text_color=("#0f172a", "#f8fafc"),
                command=lambda p=ph: self._copy_text(p),
            ).pack(side="right", padx=8, pady=5)

    # ---------------- Actions ----------------

    def _add_word(self) -> None:
        raw_input = self.entry_new_word.get().strip()
        if not raw_input:
            return
        cat_key = self._label_to_cat(self.add_cat_combo.get())
        candidates = [w.strip() for w in re.split(r"[,，;；\r\n]+", raw_input) if w.strip()]
        added = 0
        for w in candidates:
            if self.sanitizer.add_custom_word(cat_key, w):
                added += 1
        self.entry_new_word.delete(0, "end")
        self.refresh_dictionary_list()
        if added > 0:
            self.status_var.set(f"✅ [{cat_key}] +{added}")

    def _delete_single_word(self, cat_key: str, word: str) -> None:
        if self.sanitizer.remove_custom_word(cat_key, word):
            self.refresh_dictionary_list()
            self.status_var.set(f"🗑️ [{cat_key}] - {word}")

    def _clear_all_custom_words(self) -> None:
        self.sanitizer.clear_custom_dictionary()
        self.refresh_dictionary_list()
        self.status_var.set("🧹 OK")

    def _export_dictionary(self) -> None:
        target = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".json",
            initialfile="ai-privacy-sanitizer-backup.json",
            filetypes=[("JSON", "*.json")],
        )
        if target:
            self.sanitizer.export_config(Path(target))
            self.status_var.set(f"📤 {target}")

    def _import_dictionary(self) -> None:
        source = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("JSON", "*.json")],
        )
        if source:
            try:
                self.sanitizer.import_config(Path(source))
                self.refresh_all()
                self.status_var.set(f"📥 {source}")
            except Exception as exc:
                messagebox.showerror("Error", str(exc), parent=self.root)

    def _on_toggle_startup(self) -> None:
        desired = bool(self.var_startup.get())
        if not set_startup_enabled(desired):
            self.var_startup.set(is_startup_enabled())

    def _on_toggle_auto_sanitize(self) -> None:
        self.sanitizer.set_auto_sanitize_clipboard(bool(self.var_auto_sanitize.get()))

    def _on_toggle_semantic_ip(self) -> None:
        self.sanitizer.set_semantic_ip_mode(bool(self.var_semantic_ip.get()))

    def _start_hotkey_recording(self, target: str) -> None:
        self._recording_target = target
        if target == "sanitize":
            self.btn_rec_san.configure(text=self._t("btn_hk_recording"))
        else:
            self.btn_rec_res.configure(text=self._t("btn_hk_recording"))
        self.root.bind("<KeyPress>", self._on_hotkey_keypress)
        self.root.focus_force()

    def _on_hotkey_keypress(self, event: tk.Event) -> str:
        if not self._recording_target:
            return "break"
        keysym = str(getattr(event, "keysym", "") or "")
        ignore_Pure_mods = {
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
            "Win_L",
            "Win_R",
            "Super_L",
            "Super_R",
            "Caps_Lock",
        }
        if keysym in ignore_Pure_mods:
            return "break"

        state = int(getattr(event, "state", 0) or 0)
        parts: List[str] = []
        if state & 0x0004:
            parts.append("ctrl")
        if state & 0x20000 or state & 0x0008:
            parts.append("alt")
        if state & 0x0001:
            parts.append("shift")

        key_lower = keysym.lower()
        if len(key_lower) == 1 and key_lower.isalnum():
            parts.append(key_lower)
        elif key_lower.startswith("f") and key_lower[1:].isdigit():
            parts.append(key_lower)
        elif key_lower in {"space", "tab", "return", "escape", "insert", "delete", "home", "end", "prior", "next"}:
            mapped = {"return": "enter", "escape": "esc", "prior": "page up", "next": "page down"}.get(key_lower, key_lower)
            parts.append(mapped)
        else:
            char_code = getattr(event, "keycode", 0)
            if 65 <= char_code <= 90:
                parts.append(chr(char_code).lower())
            elif 48 <= char_code <= 57:
                parts.append(chr(char_code))
            else:
                parts.append(key_lower)

        combo_str = "+".join(parts)
        target = self._recording_target
        self._recording_target = None
        try:
            self.root.unbind("<KeyPress>")
        except Exception:
            pass

        if target == "sanitize":
            self.combo_hk_sanitize.set(combo_str)
            self.btn_rec_san.configure(text=self._t("btn_hk_record"))
        else:
            self.combo_hk_restore.set(combo_str)
            self.btn_rec_res.configure(text=self._t("btn_hk_record"))
        return "break"

    def _save_and_apply_hotkeys(self) -> None:
        san_val = self.combo_hk_sanitize.get().strip().lower()
        res_val = self.combo_hk_restore.get().strip().lower()
        try:
            updated = self.sanitizer.set_hotkeys(san_val, res_val)
            if self.on_reload_hotkeys:
                self.on_reload_hotkeys()
            self._refresh_hotkey_labels()
            msg = (
                self._t("msg_hk_saved")
                .replace("{san}", updated["sanitize"].upper())
                .replace("{res}", updated["restore"].upper())
            )
            self.status_var.set(msg)
        except Exception:
            self.status_var.set(self._t("msg_hk_err"))
            messagebox.showwarning("Hotkey", self._t("msg_hk_err"), parent=self.root)

    def _reset_default_hotkeys(self) -> None:
        self.combo_hk_sanitize.set("alt+s")
        self.combo_hk_restore.set("alt+r")
        self._save_and_apply_hotkeys()

    def _refresh_hotkey_labels(self) -> None:
        hk = self.sanitizer.hotkeys
        san_disp = hk.get("sanitize", "alt+s").upper()
        res_disp = hk.get("restore", "alt+r").upper()
        if hasattr(self, "btn_hero_san"):
            self.btn_hero_san.configure(
                text=re.sub(r"\(Alt\s*\+\s*S\)", f"({san_disp})", self._t("btn_hero_sanitize"))
            )
        if hasattr(self, "btn_hero_res"):
            self.btn_hero_res.configure(
                text=re.sub(r"\(Alt\s*\+\s*R\)", f"({res_disp})", self._t("btn_hero_restore"))
            )
        if hasattr(self, "lbl_workflow"):
            wf_text = (
                f"{self._t('workflow_title')}：{self._t('workflow_steps')}"
                .replace("Alt+S", san_disp)
                .replace("Alt+R", res_disp)
            )
            self.lbl_workflow.configure(text=wf_text)

    def _highlight_placeholders_in_output(self) -> None:
        inner_text = getattr(self.sandbox_output, "_textbox", None)
        if inner_text is None:
            return
        inner_text.tag_remove("placeholder_tag", "1.0", "end")
        for ph, _, _ in self.sanitizer.vault.snapshot_placeholders():
            start_idx = "1.0"
            while True:
                pos = inner_text.search(ph, start_idx, stopindex="end", exact=True)
                if not pos:
                    break
                end_pos = f"{pos}+{len(ph)}c"
                inner_text.tag_add("placeholder_tag", pos, end_pos)
                start_idx = end_pos

    def _on_sandbox_input_changed(self, _event=None) -> None:
        if self._sandbox_debounce_id is not None:
            try:
                self.root.after_cancel(self._sandbox_debounce_id)
            except Exception:
                pass
        self._sandbox_debounce_id = self.root.after(260, self._run_sandbox_sanitize)

    def _load_sample_into_sandbox(self) -> None:
        self.sandbox_input.delete("1.0", "end")
        self.sandbox_input.insert("1.0", SAMPLE_TEST_PAYLOAD.strip())
        self._run_sandbox_sanitize()

    def _render_sandbox_category_pills(self, category_counts: Dict[str, int]) -> None:
        if not hasattr(self, "sandbox_cat_inner"):
            return
        for child in self.sandbox_cat_inner.winfo_children():
            child.destroy()

        if not category_counts:
            ctk.CTkLabel(
                self.sandbox_cat_inner,
                text=self._t("sandbox_cat_empty"),
                font=self.font_small,
                text_color=("#64748b", "#94a3b8"),
            ).pack(side="left")
            return

        ctk.CTkLabel(
            self.sandbox_cat_inner,
            text=self._t("sandbox_cat_prefix"),
            font=self.font_small,
            text_color=("#0f172a", "#f8fafc"),
        ).pack(side="left", padx=(0, 6))

        for cat, cnt in sorted(category_counts.items()):
            ctk.CTkLabel(
                self.sandbox_cat_inner,
                text=f" {cat}: {cnt} ",
                font=self.font_small,
                fg_color=("#d1fae5", "#064e3b"),
                text_color=("#065f46", "#6ee7b7"),
                corner_radius=6,
            ).pack(side="left", padx=3, pady=2)

    def _run_sandbox_sanitize(self) -> None:
        raw = self.sandbox_input.get("1.0", "end").rstrip("\n")
        res = self.sanitizer.sanitize(raw)
        self.sandbox_output.delete("1.0", "end")
        self.sandbox_output.insert("1.0", res.sanitized_text)
        self._highlight_placeholders_in_output()
        self._render_sandbox_category_pills(res.category_counts)
        self.refresh_all()
        self.status_var.set(res.format_summary(self.lang))

    def _run_sandbox_restore(self) -> None:
        sanitized = self.sandbox_output.get("1.0", "end").rstrip("\n")
        if not sanitized.strip():
            sanitized = self.sandbox_input.get("1.0", "end").rstrip("\n")
        res = self.sanitizer.restore(sanitized)
        self.sandbox_output.delete("1.0", "end")
        self.sandbox_output.insert("1.0", res.restored_text)
        self.status_var.set(res.format_summary(self.lang))

    def _copy_sandbox_output(self) -> None:
        out = self.sandbox_output.get("1.0", "end").strip()
        if out:
            self._copy_text(out)

    def _clear_sandbox(self) -> None:
        self.sandbox_input.delete("1.0", "end")
        self.sandbox_output.delete("1.0", "end")
        self._render_sandbox_category_pills({})

    def _copy_text(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f"📋 Copied: {text[:36]}")

    def _clear_vault_from_gui(self) -> None:
        self.sanitizer.clear_session()
        self.refresh_all()
        self.status_var.set("🧹 Vault cleared")

    def _trigger_sanitize_clipboard(self) -> None:
        if self.on_sanitize_clipboard:
            self.on_sanitize_clipboard()
        self.refresh_all()

    def _trigger_restore_clipboard(self) -> None:
        if self.on_restore_clipboard:
            self.on_restore_clipboard()
        self.refresh_all()

    def _trigger_undo_sanitize(self) -> None:
        if self.on_undo_sanitize:
            self.on_undo_sanitize()
        self.refresh_all()

    def _trigger_exit_app(self) -> None:
        if self.on_exit_app:
            self.on_exit_app()
        else:
            self.root.quit()
            self.root.destroy()

    def present(self) -> None:
        self.refresh_all()
        self.root.deiconify()
        try:
            self.root.state("normal")
        except Exception:
            pass
        self.root.lift()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(180, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()
