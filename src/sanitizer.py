"""Core two-layer privacy sanitization engine and in-memory bidirectional session vault."""

import copy
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
import re
import secrets
import sys
import threading
from typing import Any, Dict, List, Optional, Pattern, Tuple

from src.rules import BUILTIN_RULES, RULE_PRESETS, SanitizeRule
from src.secure_io import atomic_write_private, validate_private_path
from src.vault_crypto import (
    decrypt_vault_payload,
    encrypt_vault_payload,
    is_encrypted_vault_payload,
)

MAX_SANITIZE_CHARS = 1_500_000
VALID_IDLE_WIPE_MINUTES = (0, 5, 10, 15, 30, 60)
_MODIFIER_ALIASES: Dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "win": "win",
    "windows": "win",
    "super": "win",
    "meta": "win",
    "cmd": "win",
    "command": "win",
}
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")
_VALID_MODIFIERS = frozenset(_MODIFIER_ALIASES.keys())
_VALID_FUNCTION_KEY = re.compile(r"^f([1-9]|1[0-9]|2[0-4])$")
_KEY_ALIASES: Dict[str, str] = {
    "return": "enter",
    "page_up": "pageup",
    "prior": "pageup",
    "page_down": "pagedown",
    "next": "pagedown",
    "caps_lock": "capslock",
    "num_lock": "numlock",
    "scroll_lock": "scrolllock",
    "print_screen": "printscreen",
    "grave": "`",
    "backquote": "`",
    "minus": "-",
    "equal": "=",
    "equals": "=",
    "plus": "=",
    "bracketleft": "[",
    "bracketright": "]",
    "backslash": "\\",
    "semicolon": ";",
    "apostrophe": "'",
    "quote": "'",
    "comma": ",",
    "period": ".",
    "dot": ".",
    "slash": "/",
    **{f"numpad{d}": f"num{d}" for d in range(10)},
    "numpad_add": "num_add",
    "numpad_subtract": "num_sub",
    "numpad_multiply": "num_mul",
    "numpad_divide": "num_div",
    "numpad_decimal": "num_dec",
}
_VALID_NAMED_KEYS = frozenset({
    "space", "tab", "enter", "backspace", "insert", "delete",
    "home", "end", "pageup", "pagedown",
    "left", "up", "right", "down",
    "capslock", "numlock", "scrolllock", "pause", "printscreen",
    *(f"num{d}" for d in range(10)),
    "num_add", "num_sub", "num_mul", "num_div", "num_dec",
})
_VALID_PUNCT_KEYS = frozenset("`-=[]\\;',./")

AI_PROMPT_HINTS: Dict[str, str] = {
    "zh": "# [Sanitizer: 请在回复中原样保留脱敏占位符，切勿修改格式]",
    "en": "# [Sanitizer: Keep redacted placeholders verbatim in your reply]",
}


class InputTooLargeError(ValueError):
    """Input was rejected without producing a sanitized result."""

    def __init__(self) -> None:
        super().__init__(f"Input exceeds the {MAX_SANITIZE_CHARS:,}-character limit; no output produced")


class HotkeyRollbackError(RuntimeError):
    """Settings were preserved, but restoration of the active hotkeys failed."""


def _placeholder_pattern(placeholder: str) -> str:
    """Use identical token boundaries when protecting and restoring known placeholders."""
    escaped = re.escape(placeholder)
    if placeholder[0] in "[<{":
        return escaped
    if re.fullmatch(r"[0-9.]+", placeholder):
        return r"(?<![\w.])" + escaped + r"(?!\w|\.\w)"
    if "@" in placeholder:
        return r"(?<![\w.!#$%&'*+/=?^`{|}~@-])" + escaped + r"(?![\w@-]|\.\w)"
    return r"(?<![\w.-])" + escaped + r"(?![\w.-])"


def _restore_identity(placeholder: str) -> str:
    core = placeholder[1:-1]
    if placeholder[0] in "[<{" and re.fullmatch(r"[A-Za-z0-9_]+_[0-9]+", core):
        return "bracket:" + core.lower()
    return "exact:" + placeholder


def get_runtime_dir() -> Path:
    """Return directory containing executable (when frozen as .exe) or project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = get_runtime_dir()


def get_default_config_path() -> Path:
    """Keep packaged-app settings outside executable folders and sync staging."""
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "Sanitizer" / "config.json"
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AI-Privacy-Sanitizer" / "config.json"
    return PROJECT_ROOT / "config.json"


DEFAULT_CONFIG_PATH = get_default_config_path()
EXAMPLE_CONFIG_PATH = (
    Path(sys._MEIPASS) / "config.example.json"
    if getattr(sys, "frozen", False) and sys.platform == "darwin" and hasattr(sys, "_MEIPASS")
    else PROJECT_ROOT / "config.example.json"
)

DEFAULT_CONFIG_TEMPLATE: Dict[str, Any] = {
    "language": "zh",
    "theme": "dark",
    "semantic_ip_mode": False,
    "auto_sanitize_clipboard": False,
    "ai_prompt_hint": False,
    "custom_word_whole_word": True,
    "idle_wipe_minutes": 30,
    "hud_enabled": True,
    "clipboard_privacy_guard": True,
    "hotkeys": {
        "sanitize": "alt+s",
        "restore": "alt+r",
    },
    "allowlist": [
        "127.0.0.1",
        "0.0.0.0",
        "localhost",
        "example.com",
    ],
    "disabled_rules": [],
    "custom_dictionary": {
        "COMPANY": [
            "Acme Global Technologies Sdn Bhd",
            "Acme Global",
            "南洋星辰数码私人有限公司",
            "星辰数码",
        ],
        "CLIENT": [
            "MegaCorp Bank Berhad",
            "MegaCorp",
            "太平洋远航物流集团",
        ],
        "PROJECT": [
            "Project-Hyperion-V2",
            "Project-Hyperion",
            "KL-Core-Banking-V3",
        ],
        "CUSTOM_SECRET": [
            "INTERNAL-DEPLOY-PASSPHRASE-9981",
            "prod-master-db-01.kl-dc.internal.local",
        ],
    },
}


@dataclass
class SanitizeResult:
    """Result returned by a sanitization operation."""

    sanitized_text: str
    total_count: int = 0
    category_counts: Dict[str, int] = field(default_factory=dict)

    def format_summary(self, lang: str = "zh") -> str:
        """Format a human-readable notification message in Simplified Chinese or English."""
        if lang == "en":
            if self.total_count == 0:
                return "ℹ️ No sensitive data detected; clipboard unchanged"
            details = ", ".join(
                f"{cat}: {cnt}" for cat, cnt in sorted(self.category_counts.items())
            )
            return f"✅ Sanitized: {self.total_count} sensitive items masked ({details})"
        if self.total_count == 0:
            return "ℹ️ 未检测到敏感信息，剪贴板内容保持不变"
        details = ", ".join(
            f"{cat}: {cnt}" for cat, cnt in sorted(self.category_counts.items())
        )
        return f"✅ 已脱敏：共拦截 {self.total_count} 处敏感信息（{details}）"


@dataclass
class RestoreResult:
    """Result returned by a restoration operation."""

    restored_text: str
    restored_count: int = 0

    def format_summary(self, lang: str = "zh") -> str:
        """Format a human-readable restoration notification message in Simplified Chinese or English."""
        if lang == "en":
            if self.restored_count == 0:
                return "ℹ️ No placeholders found to restore"
            return f"🔄 Restored: {self.restored_count} original values recovered"
        if self.restored_count == 0:
            return "ℹ️ 未发现可还原的占位符"
        return f"🔄 已还原：已恢复 {self.restored_count} 处真实数据"


class SessionVault:
    """Thread-safe bidirectional in-memory mapping between original values and placeholders."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._original_to_placeholder: Dict[str, str] = {}
        self._placeholder_to_original: Dict[str, str] = {}
        self._original_to_category: Dict[str, str] = {}
        self._category_counters: Dict[str, int] = {}
        self._total_intercepted_hits: int = 0

    def record_hits(self, hits: int) -> None:
        with self._lock:
            self._total_intercepted_hits += max(0, hits)

    @property
    def total_intercepted_hits(self) -> int:
        with self._lock:
            return self._total_intercepted_hits

    def get_or_create_placeholder(
        self,
        original: str,
        category: str,
        template: str = "[{category}_{index}]",
        semantic_ip_mode: bool = False,
    ) -> str:
        """Return existing placeholder for `original` or allocate a new one."""
        with self._lock:
            if original in self._original_to_placeholder:
                return self._original_to_placeholder[original]

            idx = self._category_counters.get(category, 0) + 1
            self._category_counters[category] = idx

            placeholder = self._build_placeholder(
                category=category,
                index=idx,
                template=template,
                semantic_ip_mode=semantic_ip_mode,
            )
            existing_identities = {
                _restore_identity(existing_ph) for existing_ph in self._placeholder_to_original
            }

            while (
                placeholder in self._placeholder_to_original
                or _restore_identity(placeholder) in existing_identities
                or placeholder == original
            ):
                idx += 1
                self._category_counters[category] = idx
                next_placeholder = self._build_placeholder(
                    category=category,
                    index=idx,
                    template=template,
                    semantic_ip_mode=semantic_ip_mode,
                )
                if next_placeholder == placeholder:
                    raise ValueError("Placeholder template cannot allocate distinct values")
                placeholder = next_placeholder

            self._original_to_placeholder[original] = placeholder
            self._placeholder_to_original[placeholder] = original
            self._original_to_category[original] = category
            return placeholder

    @staticmethod
    def _build_placeholder(
        category: str,
        index: int,
        template: str,
        semantic_ip_mode: bool,
    ) -> str:
        if semantic_ip_mode:
            if category == "PRIVATE_IP" and index <= 150:
                octet = 100 + ((index - 1) % 150) + 1
                return f"192.0.2.{octet}"
            if category == "PUBLIC_IP" and index <= 150:
                octet = 100 + ((index - 1) % 150) + 1
                return f"203.0.113.{octet}"
            if category == "EMAIL":
                return f"user{index}@example.com"
            if category == "USER_PATH":
                return f"dev_user_{index}"
        return template.format(category=category, index=index)

    def remove_mapping(self, placeholder: str) -> bool:
        """Remove a single placeholder <-> original mapping from the session vault."""
        with self._lock:
            orig = self._placeholder_to_original.pop(placeholder, None)
            if orig is None:
                return False
            self._original_to_placeholder.pop(orig, None)
            self._original_to_category.pop(orig, None)
            return True

    def lookup_original(self, placeholder: str) -> Optional[str]:
        with self._lock:
            return self._placeholder_to_original.get(placeholder)

    def lookup_category(self, placeholder: str) -> str:
        with self._lock:
            orig = self._placeholder_to_original.get(placeholder)
            if orig is None:
                return "UNKNOWN"
            return self._original_to_category.get(orig, "UNKNOWN")

    def merge_from(self, other: "SessionVault") -> int:
        """Merge mappings from another SessionVault (e.g., isolated sandbox) into this vault."""
        merged = 0
        payload = other.export_dict()
        with self._lock:
            used_identities = {_restore_identity(p) for p in self._placeholder_to_original}
            for orig, ph in payload["original_to_placeholder"].items():
                cat = payload["original_to_category"].get(orig, "CUSTOM_SECRET")
                if orig in self._original_to_placeholder:
                    continue
                if ph in self._placeholder_to_original or _restore_identity(ph) in used_identities:
                    if ph.startswith("<") and ph.endswith(">"):
                        tpl = "<{category}_{index}>"
                    elif ph.startswith("{") and ph.endswith("}"):
                        tpl = "{{{category}_{index}}}"
                    else:
                        tpl = "[{category}_{index}]"
                    new_ph = self.get_or_create_placeholder(orig, cat, template=tpl)
                    used_identities.add(_restore_identity(new_ph))
                else:
                    self._original_to_placeholder[orig] = ph
                    self._placeholder_to_original[ph] = orig
                    self._original_to_category[orig] = cat
                    used_identities.add(_restore_identity(ph))
                    try:
                        idx = self._loaded_placeholder_index(ph, cat)
                        self._category_counters[cat] = max(self._category_counters.get(cat, 0), idx)
                    except ValueError:
                        pass
                merged += 1
        return merged

    def clear(self) -> int:
        """Clear all session mappings and return the number of cleared entries."""
        with self._lock:
            count = len(self._original_to_placeholder)
            self._original_to_placeholder.clear()
            self._placeholder_to_original.clear()
            self._original_to_category.clear()
            self._category_counters.clear()
            self._total_intercepted_hits = 0
            return count

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._original_to_placeholder)

    def snapshot_placeholders(self) -> List[Tuple[str, str, str]]:
        """Return list of (placeholder, original, category) sorted by placeholder length desc."""
        with self._lock:
            items = [
                (
                    ph,
                    orig,
                    self._original_to_category.get(orig, "UNKNOWN"),
                )
                for ph, orig in self._placeholder_to_original.items()
            ]
        items.sort(key=lambda item: len(item[0]), reverse=True)
        return items

    def export_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "original_to_placeholder": dict(self._original_to_placeholder),
                "placeholder_to_original": dict(self._placeholder_to_original),
                "original_to_category": dict(self._original_to_category),
                "category_counters": dict(self._category_counters),
                "total_intercepted_hits": self._total_intercepted_hits,
            }

    def save_to_file(self, path: Path, passphrase: Optional[str] = None) -> None:
        """Export current session mappings atomically to JSON (plaintext or AES-256-GCM encrypted)."""
        target = Path(path)
        payload = self.export_dict()
        if passphrase is not None:
            payload = encrypt_vault_payload(payload, passphrase)
        serialized = json.dumps(payload, indent=2, ensure_ascii=False)
        atomic_write_private(target, serialized)

    @staticmethod
    def _loaded_placeholder_index(placeholder: str, category: str) -> int:
        """Accept only placeholders produced by the built-in engine or custom categories."""
        templates = {"[{category}_{index}]"}
        templates.update(rule.placeholder_template for rule in BUILTIN_RULES if rule.category == category)
        marker = "\x00APS_INDEX\x00"
        while marker in category:
            marker += "\x00"
        for template in templates:
            pattern = re.escape(template.format(category=category, index=marker))
            match = re.fullmatch(pattern.replace(re.escape(marker), r"([1-9][0-9]*)"), placeholder)
            if match:
                return int(match.group(1))
        semantic = {
            "PRIVATE_IP": r"192\.0\.2\.(1[0-9]{2}|2[0-4][0-9]|250)",
            "PUBLIC_IP": r"203\.0\.113\.(1[0-9]{2}|2[0-4][0-9]|250)",
            "EMAIL": r"user([1-9][0-9]*)@example\.com",
            "USER_PATH": r"dev_user_([1-9][0-9]*)",
        }
        if category in semantic:
            match = re.fullmatch(semantic[category], placeholder)
            if match:
                value = int(match.group(1))
                if category not in ("PRIVATE_IP", "PUBLIC_IP"):
                    return value
                if 101 <= value <= 250:
                    return value - 100
        raise ValueError("Invalid vault mapping")

    @staticmethod
    def _loaded_counter(value: Any) -> int:
        # Preserve old JSON files that represented nonnegative counters as decimal strings.
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
            value = int(value)
        if type(value) is not int or value < 0:
            raise ValueError("Invalid vault counter")
        return value

    def load_from_file(self, path: Path, passphrase: Optional[str] = None) -> None:
        """Validate the entire imported state (plaintext or encrypted) before merging into the live vault."""
        source = validate_private_path(path)
        if not source.exists():
            return
        raw = json.loads(source.read_text(encoding="utf-8"))
        if is_encrypted_vault_payload(raw):
            if passphrase is None:
                raise ValueError("Encrypted vault requires a passphrase")
            raw = decrypt_vault_payload(raw, passphrase)
        if not isinstance(raw, dict):
            raise ValueError("Invalid vault format")
        fields = ("original_to_placeholder", "placeholder_to_original", "original_to_category", "category_counters")
        maps = [raw.get(field, {}) for field in fields]
        if any(not isinstance(mapping, dict) for mapping in maps):
            raise ValueError("Invalid vault format")
        orig_to_ph, ph_to_orig, orig_to_cat, raw_counters = maps
        if any(
            not isinstance(key, str) or not key or not isinstance(value, str) or not value
            for mapping in maps[:3] for key, value in mapping.items()
        ):
            raise ValueError("Invalid vault mapping")
        if set(orig_to_cat) != set(orig_to_ph) or len(orig_to_ph) != len(ph_to_orig):
            raise ValueError("Invalid vault mapping")
        counters = {}
        for category, value in raw_counters.items():
            if not isinstance(category, str) or not category:
                raise ValueError("Invalid vault counter")
            counters[category] = self._loaded_counter(value)
        for original, placeholder in orig_to_ph.items():
            if original == placeholder or ph_to_orig.get(placeholder) != original:
                raise ValueError("Invalid vault mapping")
            category = orig_to_cat[original]
            index = self._loaded_placeholder_index(placeholder, category)
            counters[category] = max(counters.get(category, 0), index)
        hits = self._loaded_counter(raw.get("total_intercepted_hits", 0))
        with self._lock:
            identities = {
                _restore_identity(placeholder): original
                for placeholder, original in self._placeholder_to_original.items()
            }
            for original, placeholder in orig_to_ph.items():
                identity = _restore_identity(placeholder)
                if identity in identities and identities[identity] != original:
                    raise ValueError("Ambiguous vault restoration aliases")
                identities[identity] = original
                if (
                    original in self._original_to_placeholder
                    and self._original_to_placeholder[original] != placeholder
                    or placeholder in self._placeholder_to_original
                    and self._placeholder_to_original[placeholder] != original
                    or original in self._original_to_category
                    and self._original_to_category[original] != orig_to_cat[original]
                ):
                    raise ValueError("Vault conflicts with current session")
            self._original_to_placeholder.update(orig_to_ph)
            self._placeholder_to_original.update(ph_to_orig)
            self._original_to_category.update(orig_to_cat)
            for category, value in counters.items():
                self._category_counters[category] = max(self._category_counters.get(category, 0), value)
            self._total_intercepted_hits += hits


class PrivacySanitizer:
    """Two-layer privacy sanitization and restoration engine."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        example_config_path: Optional[Path] = None,
        rules: Optional[List[SanitizeRule]] = None,
    ) -> None:
        self._explicit_config_path = config_path is not None
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.example_config_path = (
            Path(example_config_path) if example_config_path else EXAMPLE_CONFIG_PATH
        )
        self.rules = rules if rules is not None else BUILTIN_RULES
        self.vault = SessionVault()
        self._config_lock = threading.RLock()
        self._config_mtime: float = -1.0
        self._config_data: Dict[str, Any] = {}
        self._persisted_config: Dict[str, Any] = {}
        self.ensure_config_exists()
        self.reload_config(force=True)

    def ensure_config_exists(self) -> Path:
        """Ensure `config.json` exists locally; fall back to user AppData if runtime dir is read-only."""
        validate_private_path(self.config_path)
        if not self.config_path.exists():
            if not self._explicit_config_path and getattr(sys, "frozen", False) and sys.platform == "win32":
                legacy = PROJECT_ROOT / "config.json"
                if legacy != self.config_path and legacy.exists():
                    # Never relax the link checks for a sync client's staging
                    # links. Migrate once into a local, private, independent file;
                    # retain the original and all its settings unchanged.
                    validate_private_path(legacy)
                    raw = legacy.read_text(encoding="utf-8")
                    if not isinstance(json.loads(raw), dict):
                        raise ValueError("Legacy configuration must be a JSON object")
                    try:
                        atomic_write_private(self.config_path, raw, overwrite=False)
                    except FileExistsError:
                        # Another instance may have completed migration first.
                        validate_private_path(self.config_path)
                    return self.config_path
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                template = (
                    self.example_config_path.read_text(encoding="utf-8")
                    if self.example_config_path.exists()
                    else json.dumps(DEFAULT_CONFIG_TEMPLATE, indent=2, ensure_ascii=False)
                )
                atomic_write_private(self.config_path, template, overwrite=False)
            except PermissionError:
                if self._explicit_config_path or (getattr(sys, "frozen", False) and sys.platform == "win32"):
                    raise
                fallback_root = Path(os.environ.get("APPDATA") or Path.home()) / "AI-Privacy-Sanitizer"
                fallback_root.mkdir(parents=True, exist_ok=True)
                self.config_path = fallback_root / "config.json"
                if not self.config_path.exists():
                    atomic_write_private(
                        self.config_path,
                        json.dumps(DEFAULT_CONFIG_TEMPLATE, indent=2, ensure_ascii=False),
                        overwrite=False,
                    )
        return self.config_path

    def reload_config(self, force: bool = False) -> Dict[str, Any]:
        """Reload `config.json` if modified since last read or if forced."""
        with self._config_lock:
            self.ensure_config_exists()
            try:
                mtime = self.config_path.stat().st_mtime
                if force or mtime != self._config_mtime:
                    raw = self.config_path.read_text(encoding="utf-8")
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        self._config_data = loaded
                        self._persisted_config = copy.deepcopy(loaded)
                        self._config_mtime = mtime
            except Exception:
                if not self._config_data:
                    self._config_data = copy.deepcopy(DEFAULT_CONFIG_TEMPLATE)
                    self._persisted_config = copy.deepcopy(self._config_data)
            return self._config_data

    @classmethod
    def validate_config_dict(cls, candidate: Any) -> Dict[str, Any]:
        """Validate known config keys and types while preserving unknown future keys."""
        if not isinstance(candidate, dict):
            raise ValueError("Configuration root must be a JSON object")
        validated = copy.deepcopy(candidate)
        if "language" in validated and str(validated["language"]).lower() not in ("zh", "en"):
            raise ValueError("Invalid language value")
        if "theme" in validated and str(validated["theme"]).lower() not in ("dark", "light"):
            raise ValueError("Invalid theme value")
        for bool_key in (
            "semantic_ip_mode",
            "auto_sanitize_clipboard",
            "ai_prompt_hint",
            "custom_word_whole_word",
            "hud_enabled",
            "clipboard_privacy_guard",
        ):
            if bool_key in validated and not isinstance(validated[bool_key], bool):
                raise ValueError(f"Invalid boolean setting: {bool_key}")
        if "idle_wipe_minutes" in validated:
            val = validated["idle_wipe_minutes"]
            if type(val) is not int or val < 0 or val > 1440:
                raise ValueError("Invalid idle_wipe_minutes setting")
        if "hotkeys" in validated:
            hk = validated["hotkeys"]
            if not isinstance(hk, dict):
                raise ValueError("Invalid hotkeys section")
            san = str(hk.get("sanitize", "alt+s"))
            res = str(hk.get("restore", "alt+r"))
            validated["hotkeys"] = cls.normalize_hotkeys(san, res)
        if "allowlist" in validated:
            if not isinstance(validated["allowlist"], list) or any(
                not isinstance(x, str) for x in validated["allowlist"]
            ):
                raise ValueError("Invalid allowlist section")
        if "disabled_rules" in validated:
            if not isinstance(validated["disabled_rules"], list) or any(
                not isinstance(x, str) for x in validated["disabled_rules"]
            ):
                raise ValueError("Invalid disabled_rules section")
        if "custom_dictionary" in validated:
            cd = validated["custom_dictionary"]
            if not isinstance(cd, dict):
                raise ValueError("Invalid custom_dictionary section")
            for cat, words in cd.items():
                if not isinstance(cat, str) or not isinstance(words, list) or any(
                    not isinstance(w, str) for w in words
                ):
                    raise ValueError("Invalid custom_dictionary entries")
        return validated

    def save_config(self, new_config: Optional[Dict[str, Any]] = None) -> None:
        """Persist current or provided configuration dictionary to `config.json` atomically."""
        with self._config_lock:
            candidate = self._config_data if new_config is None else self.validate_config_dict(new_config)
            try:
                serialized = json.dumps(candidate, indent=2, ensure_ascii=False)
                atomic_write_private(self.config_path, serialized)
            except (OSError, TypeError, ValueError):
                self._config_data = copy.deepcopy(self._persisted_config)
                raise
            self._config_data = candidate
            self._persisted_config = copy.deepcopy(candidate)
            try:
                self._config_mtime = self.config_path.stat().st_mtime
            except Exception:
                pass

    @property
    def language(self) -> str:
        self.reload_config()
        lang = str(self._config_data.get("language", "zh")).lower()
        return "en" if lang == "en" else "zh"

    def set_language(self, lang: str) -> None:
        with self._config_lock:
            self.reload_config()
            self._config_data["language"] = "en" if str(lang).lower() == "en" else "zh"
            self.save_config()

    @property
    def theme(self) -> str:
        self.reload_config()
        t = str(self._config_data.get("theme", "dark")).lower()
        return "light" if t == "light" else "dark"

    def set_theme(self, theme_mode: str) -> None:
        with self._config_lock:
            self.reload_config()
            self._config_data["theme"] = (
                "light" if str(theme_mode).lower() == "light" else "dark"
            )
            self.save_config()

    @property
    def semantic_ip_mode(self) -> bool:
        self.reload_config()
        return bool(self._config_data.get("semantic_ip_mode", False))

    def set_semantic_ip_mode(self, enabled: bool) -> None:
        with self._config_lock:
            self.reload_config()
            self._config_data["semantic_ip_mode"] = bool(enabled)
            self.save_config()

    @property
    def auto_sanitize_clipboard(self) -> bool:
        self.reload_config()
        return bool(self._config_data.get("auto_sanitize_clipboard", False))

    def set_auto_sanitize_clipboard(self, enabled: bool) -> None:
        with self._config_lock:
            self.reload_config()
            self._config_data["auto_sanitize_clipboard"] = bool(enabled)
            self.save_config()

    @property
    def ai_prompt_hint(self) -> bool:
        self.reload_config()
        return bool(self._config_data.get("ai_prompt_hint", False))

    def set_ai_prompt_hint(self, enabled: bool) -> None:
        with self._config_lock:
            self.reload_config()
            self._config_data["ai_prompt_hint"] = bool(enabled)
            self.save_config()

    @property
    def custom_word_whole_word(self) -> bool:
        self.reload_config()
        return bool(self._config_data.get("custom_word_whole_word", True))

    def set_custom_word_whole_word(self, enabled: bool) -> None:
        with self._config_lock:
            self.reload_config()
            self._config_data["custom_word_whole_word"] = bool(enabled)
            self.save_config()

    @property
    def idle_wipe_minutes(self) -> int:
        self.reload_config()
        raw = self._config_data.get("idle_wipe_minutes", 30)
        if type(raw) is int and 0 <= raw <= 1440:
            return raw
        return 30

    def set_idle_wipe_minutes(self, minutes: int) -> None:
        if type(minutes) is not int or minutes < 0 or minutes > 1440:
            raise ValueError("Invalid idle wipe timeout")
        with self._config_lock:
            self.reload_config()
            self._config_data["idle_wipe_minutes"] = minutes
            self.save_config()

    @property
    def hud_enabled(self) -> bool:
        self.reload_config()
        return bool(self._config_data.get("hud_enabled", True))

    def set_hud_enabled(self, enabled: bool) -> None:
        with self._config_lock:
            self.reload_config()
            self._config_data["hud_enabled"] = bool(enabled)
            self.save_config()

    @property
    def clipboard_privacy_guard(self) -> bool:
        self.reload_config()
        return bool(self._config_data.get("clipboard_privacy_guard", True))

    def set_clipboard_privacy_guard(self, enabled: bool) -> None:
        with self._config_lock:
            self.reload_config()
            self._config_data["clipboard_privacy_guard"] = bool(enabled)
            self.save_config()

    @property
    def hotkeys(self) -> Dict[str, str]:
        self.reload_config()
        hk = self._config_data.get("hotkeys", {})
        if not isinstance(hk, dict):
            hk = {}
        san = str(hk.get("sanitize", "alt+s")).strip().lower() or "alt+s"
        res = str(hk.get("restore", "alt+r")).strip().lower() or "alt+r"
        return {
            "sanitize": san,
            "restore": res,
        }

    @staticmethod
    def _validate_single_hotkey(chord: str) -> str:
        cleaned = re.sub(r"\s+", "", str(chord or "").strip().lower())
        if not cleaned or any(ord(ch) < 32 or ord(ch) > 126 for ch in cleaned):
            raise ValueError("Invalid hotkey format")
        parts = cleaned.split("+")
        if any(not p for p in parts):
            raise ValueError("Invalid hotkey format")
        raw_key = parts[-1]
        key = _KEY_ALIASES.get(raw_key, raw_key)
        mods = parts[:-1]
        if not mods:
            # Bare single keys (like 'a', 'space', 'esc') hijack typing across the OS.
            # Only allow standalone function keys F1-F24 without modifiers.
            if not _VALID_FUNCTION_KEY.fullmatch(key):
                raise ValueError("Hotkey requires a modifier key (Ctrl/Alt/Shift/Win) or F1-F24")
            return key
        seen_mods = set()
        for mod in mods:
            canonical = _MODIFIER_ALIASES.get(mod)
            if canonical is None:
                raise ValueError("Unsupported hotkey modifier")
            if canonical in seen_mods:
                raise ValueError("Duplicate hotkey modifier")
            seen_mods.add(canonical)
        if key in _MODIFIER_ALIASES:
            raise ValueError("Hotkey must include a non-modifier key")
        is_single_valid = len(key) == 1 and (key.isalnum() or key in _VALID_PUNCT_KEYS)
        if not (is_single_valid or _VALID_FUNCTION_KEY.fullmatch(key) or key in _VALID_NAMED_KEYS):
            raise ValueError("Unsupported hotkey key")
        ordered_mods = [m for m in _MODIFIER_ORDER if m in seen_mods]
        return "+".join(ordered_mods + [key])

    @classmethod
    def normalize_hotkeys(cls, sanitize_hotkey: str, restore_hotkey: str) -> Dict[str, str]:
        """Validate a candidate without changing settings or writing to disk."""
        san_clean = cls._validate_single_hotkey(sanitize_hotkey)
        res_clean = cls._validate_single_hotkey(restore_hotkey)
        if san_clean == res_clean:
            raise ValueError("Sanitize and Restore hotkeys must be different")
        return {"sanitize": san_clean, "restore": res_clean}

    def set_hotkeys(self, sanitize_hotkey: str, restore_hotkey: str) -> Dict[str, str]:
        """Validate, normalize, and persist global hotkeys for sanitize and restore."""
        candidate = self.normalize_hotkeys(sanitize_hotkey, restore_hotkey)
        with self._config_lock:
            self.reload_config()
            self._config_data["hotkeys"] = candidate
            self.save_config()
            return self.hotkeys

    def get_custom_dictionary(self) -> Dict[str, List[str]]:
        """Return a normalized copy of `custom_dictionary`."""
        self.reload_config()
        raw_dict = self._config_data.get("custom_dictionary", {})
        result: Dict[str, List[str]] = {
            "COMPANY": [],
            "CLIENT": [],
            "PROJECT": [],
            "CUSTOM_SECRET": [],
        }
        if isinstance(raw_dict, dict):
            for cat, words in raw_dict.items():
                cat_key = str(cat).strip().upper()
                if cat_key not in result:
                    result[cat_key] = []
                if isinstance(words, list):
                    for w in words:
                        if isinstance(w, str) and w.strip():
                            cleaned = w.strip()
                            if cleaned not in result[cat_key]:
                                result[cat_key].append(cleaned)
        return result

    def add_custom_word(self, category: str, word: str) -> bool:
        """Add a word to `custom_dictionary[category]` and save `config.json`."""
        cleaned = word.strip()
        cat_key = category.strip().upper()
        if not cleaned or not cat_key:
            return False
        with self._config_lock:
            current = self.get_custom_dictionary()
            if cat_key not in current:
                current[cat_key] = []
            if cleaned in current[cat_key]:
                return False
            current[cat_key].append(cleaned)
            self._config_data["custom_dictionary"] = current
            self.save_config()
            return True

    def remove_custom_word(self, category: str, word: str) -> bool:
        """Remove a word from `custom_dictionary[category]` and save `config.json`."""
        cleaned = word.strip()
        cat_key = category.strip().upper()
        with self._config_lock:
            current = self.get_custom_dictionary()
            if cat_key not in current or cleaned not in current[cat_key]:
                return False
            current[cat_key].remove(cleaned)
            self._config_data["custom_dictionary"] = current
            self.save_config()
            return True

    def clear_custom_dictionary(self) -> None:
        """Clear all custom dictionary entries."""
        with self._config_lock:
            self.reload_config()
            self._config_data["custom_dictionary"] = {
                "COMPANY": [],
                "CLIENT": [],
                "PROJECT": [],
                "CUSTOM_SECRET": [],
            }
            self.save_config()

    def get_allowlist(self) -> List[str]:
        """Return a normalized list of allowlisted values (never sanitized)."""
        self.reload_config()
        raw_list = self._config_data.get(
            "allowlist", DEFAULT_CONFIG_TEMPLATE["allowlist"]
        )
        result: List[str] = []
        if isinstance(raw_list, list):
            for item in raw_list:
                if isinstance(item, str) and item.strip():
                    cleaned = item.strip()
                    if cleaned not in result:
                        result.append(cleaned)
        return result

    def add_allowlist_item(self, item: str) -> bool:
        """Add an item to `allowlist` and persist to `config.json`."""
        cleaned = str(item or "").strip()
        if not cleaned:
            return False
        with self._config_lock:
            current = self.get_allowlist()
            if any(cleaned.lower() == existing.lower() for existing in current):
                return False
            current.append(cleaned)
            self._config_data["allowlist"] = current
            self.save_config()
            return True

    def remove_allowlist_item(self, item: str) -> bool:
        """Remove an item from `allowlist` (case-insensitive) and persist to `config.json`."""
        cleaned = str(item or "").strip().lower()
        if not cleaned:
            return False
        with self._config_lock:
            current = self.get_allowlist()
            new_list = [x for x in current if x.lower() != cleaned]
            if len(new_list) == len(current):
                return False
            self._config_data["allowlist"] = new_list
            self.save_config()
            return True

    def get_disabled_rules(self) -> List[str]:
        """Return list of disabled rule names."""
        self.reload_config()
        raw = self._config_data.get("disabled_rules", [])
        if not isinstance(raw, list):
            return []
        return [str(r).strip() for r in raw if isinstance(r, str) and r.strip()]

    def active_rule_counts(self) -> Tuple[int, int]:
        """Return (active_count, total_count) for built-in rules."""
        disabled = set(self.get_disabled_rules())
        total = len(self.rules)
        active = sum(1 for r in self.rules if r.enabled_by_default and r.name not in disabled)
        return active, total

    def set_rule_enabled(self, rule_name: str, enabled: bool) -> None:
        """Enable or disable a built-in rule by `rule_name` and save to `config.json`."""
        cleaned = str(rule_name or "").strip()
        if not cleaned:
            return
        with self._config_lock:
            disabled = self.get_disabled_rules()
            if enabled:
                disabled = [r for r in disabled if r != cleaned]
            else:
                if cleaned not in disabled:
                    disabled.append(cleaned)
            self._config_data["disabled_rules"] = disabled
            self.save_config()

    def apply_rule_preset(self, preset_name: str) -> Tuple[int, int]:
        """Apply a built-in rule preset ('dev', 'hr', or 'strict') and persist disabled_rules."""
        if preset_name not in RULE_PRESETS:
            raise ValueError(f"Unknown rule preset: {preset_name}")
        enabled_set = set(RULE_PRESETS[preset_name])
        disabled = [r.name for r in self.rules if r.name not in enabled_set]
        with self._config_lock:
            self.reload_config()
            self._config_data["disabled_rules"] = disabled
            self.save_config()
        return self.active_rule_counts()

    def export_config(self, target_path: Path) -> None:
        """Export current `config.json` to `target_path`."""
        self.reload_config()
        atomic_write_private(
            target_path, json.dumps(self._config_data, indent=2, ensure_ascii=False)
        )

    def import_config(self, source_path: Path, *, dictionary_only: bool = False) -> Dict[str, Any]:
        """Validate and import configuration (or custom dictionary/allowlist only) from `source_path`."""
        source = validate_private_path(Path(source_path))
        raw = source.read_text(encoding="utf-8")
        imported = json.loads(raw)
        if not isinstance(imported, dict) or "custom_dictionary" not in imported:
            raise ValueError("Invalid config format: missing 'custom_dictionary'")
        validated = self.validate_config_dict(imported)
        with self._config_lock:
            if dictionary_only:
                self.reload_config()
                merged = copy.deepcopy(self._config_data)
                merged["custom_dictionary"] = validated["custom_dictionary"]
                if "allowlist" in validated:
                    merged["allowlist"] = validated["allowlist"]
                self.save_config(merged)
            else:
                self.save_config(validated)
            return self._config_data

    def _get_sorted_custom_terms(self) -> List[Tuple[str, str]]:
        """Return list of (term, category) sorted by term length descending (longest match first)."""
        custom_dict = self.get_custom_dictionary()
        terms: List[Tuple[str, str]] = []
        for cat_upper, word_list in custom_dict.items():
            for word in word_list:
                terms.append((word, cat_upper))
        terms.sort(key=lambda item: len(item[0]), reverse=True)
        return terms

    @staticmethod
    def _compile_custom_term_pattern(term: str, whole_word: bool) -> Pattern[str]:
        escaped = re.escape(term)
        if whole_word and term:
            prefix = r"(?<![A-Za-z0-9_])" if (term[0].isascii() and term[0].isalnum()) else ""
            suffix = r"(?![A-Za-z0-9_])" if (term[-1].isascii() and term[-1].isalnum()) else ""
            return re.compile(prefix + escaped + suffix, re.IGNORECASE)
        return re.compile(escaped, re.IGNORECASE)

    def sanitize(
        self,
        text: str,
        *,
        vault: Optional[SessionVault] = None,
        include_ai_hint: Optional[bool] = None,
    ) -> SanitizeResult:
        """Sanitize text using Layer 1 (Custom Dictionary) followed by Layer 2 (Regex Rules)."""
        if len(text) > MAX_SANITIZE_CHARS:
            raise InputTooLargeError()
        if not text:
            return SanitizeResult(sanitized_text=text, total_count=0, category_counts={})

        active_vault = self.vault if vault is None else vault
        semantic_ip = self.semantic_ip_mode
        whole_word = self.custom_word_whole_word
        use_ai_hint = self.ai_prompt_hint if include_ai_hint is None else bool(include_ai_hint)
        allowlist_lower = {w.lower() for w in self.get_allowlist()}
        disabled_set = set(self.get_disabled_rules())
        category_counts: Dict[str, int] = {}
        total_count = 0

        sentinel_to_placeholder: Dict[str, str] = {}
        placeholder_to_sentinel: Dict[str, str] = {}
        sentinel_seq = 0
        san_prefix = f"\x00\x01__SAN_{secrets.token_hex(6)}_"
        while san_prefix in text:
            san_prefix += "\x00"
        sentinel_pattern = re.compile(re.escape(san_prefix) + r"\d+__\x01\x00")
        cached_starts: List[int] = []
        cached_ends: List[int] = []
        spans_dirty = False

        def unprotect(value: str) -> str:
            if not sentinel_to_placeholder or san_prefix not in value:
                return value
            return sentinel_pattern.sub(
                lambda match: sentinel_to_placeholder.get(match.group(0), match.group(0)), value
            )

        def protected_sub(pattern: re.Pattern, replacer) -> str:
            nonlocal cached_starts, cached_ends, spans_dirty
            # Fast path: when no sentinels exist in working_text yet, skip span scanning entirely.
            if not sentinel_to_placeholder:
                new_text, count = pattern.subn(replacer, working_text)
                if count and sentinel_to_placeholder:
                    spans_dirty = True
                return new_text

            if spans_dirty:
                spans = [match.span() for match in sentinel_pattern.finditer(working_text)]
                cached_starts = [start for start, _ in spans]
                cached_ends = [end for _, end in spans]
                spans_dirty = False

            starts = cached_starts
            ends = cached_ends
            mutated = False

            def guarded(match: re.Match) -> str:
                nonlocal mutated
                first = bisect_right(ends, match.start())
                last = bisect_left(starts, match.end()) - 1
                if first <= last and (
                    match.start() > starts[first] or match.end() < ends[last]
                ):
                    return match.group(0)
                replaced = replacer(match)
                if replaced != match.group(0):
                    mutated = True
                return replaced

            new_text = pattern.sub(guarded, working_text)
            if mutated:
                spans_dirty = True
            return new_text

        def allocate_sentinel(placeholder: str) -> str:
            nonlocal sentinel_seq
            if placeholder in placeholder_to_sentinel:
                return placeholder_to_sentinel[placeholder]
            sentinel_seq += 1
            sentinel = f"{san_prefix}{sentinel_seq}__\x01\x00"
            sentinel_to_placeholder[sentinel] = placeholder
            placeholder_to_sentinel[placeholder] = sentinel
            return sentinel

        def record_hit(category: str) -> None:
            nonlocal total_count
            total_count += 1
            category_counts[category] = category_counts.get(category, 0) + 1

        working_text = text

        # Protect any already-existing placeholders in the input text (idempotency)
        for existing_ph, _, _ in active_vault.snapshot_placeholders():
            if existing_ph in working_text:
                working_text, changed = re.subn(
                    _placeholder_pattern(existing_ph),
                    lambda _match, ph=existing_ph: allocate_sentinel(ph), working_text,
                )
                if changed:
                    spans_dirty = True

        # --- Layer 1: Custom High-Risk Dictionary (Sorted Longest to Shortest, Case-Insensitive) ---
        for term, category in self._get_sorted_custom_terms():
            if term.lower() in allowlist_lower:
                continue
            pattern = self._compile_custom_term_pattern(term, whole_word=whole_word)
            if not pattern.search(working_text):
                continue

            def _dict_replacer(match: re.Match, cat: str = category) -> str:
                matched_val = match.group(0)
                if matched_val in sentinel_to_placeholder:
                    return matched_val
                matched_val = unprotect(matched_val)
                if matched_val.lower() in allowlist_lower:
                    return matched_val
                ph = active_vault.get_or_create_placeholder(
                    original=matched_val,
                    category=cat,
                    template="[{category}_{index}]",
                    semantic_ip_mode=semantic_ip,
                )
                record_hit(cat)
                return allocate_sentinel(ph)

            working_text = protected_sub(pattern, _dict_replacer)

        # --- Layer 2: Built-in High-Strength Regex Engine ---
        working_lower: Optional[str] = None
        working_is_ascii: Optional[bool] = None
        working_has_quote: Optional[bool] = None

        for rule in self.rules:
            if not rule.enabled_by_default or rule.name in disabled_set:
                continue
            if rule.require_non_ascii:
                if working_is_ascii is None:
                    working_is_ascii = working_text.isascii()
                if working_is_ascii:
                    continue
            if rule.require_quote:
                if working_has_quote is None:
                    working_has_quote = ('"' in working_text) or ("'" in working_text) or ("`" in working_text)
                if not working_has_quote:
                    continue
            if rule.fast_tokens:
                if working_lower is None:
                    working_lower = working_text.lower()
                if not any(tok in working_lower for tok in rule.fast_tokens):
                    continue

            before_text = working_text

            def _rule_replacer(match: re.Match, current_rule: SanitizeRule = rule) -> str:
                full_match = match.group(0)
                if full_match in sentinel_to_placeholder:
                    return full_match

                if current_rule.target_group:
                    secret_val = match.group(current_rule.target_group)
                    if not secret_val or secret_val in sentinel_to_placeholder:
                        return full_match
                    secret_val = unprotect(secret_val)
                    if (
                        secret_val.lower() in allowlist_lower
                        or full_match.lower() in allowlist_lower
                    ):
                        return full_match
                    if current_rule.validator is not None and not current_rule.validator(
                        secret_val
                    ):
                        return full_match
                    ph = active_vault.get_or_create_placeholder(
                        original=secret_val,
                        category=current_rule.category,
                        template=current_rule.placeholder_template,
                        semantic_ip_mode=semantic_ip,
                    )
                    record_hit(current_rule.category)
                    sentinel = allocate_sentinel(ph)
                    rel_start = match.start(current_rule.target_group) - match.start(0)
                    rel_end = match.end(current_rule.target_group) - match.start(0)
                    return full_match[:rel_start] + sentinel + full_match[rel_end:]

                original_match = unprotect(full_match)
                if original_match.lower() in allowlist_lower:
                    return full_match
                if current_rule.validator is not None and not current_rule.validator(
                    original_match
                ):
                    return full_match

                ph = active_vault.get_or_create_placeholder(
                    original=original_match,
                    category=current_rule.category,
                    template=current_rule.placeholder_template,
                    semantic_ip_mode=semantic_ip,
                )
                record_hit(current_rule.category)
                return allocate_sentinel(ph)

            working_text = protected_sub(rule.pattern, _rule_replacer)
            if working_text is not before_text:
                working_lower = None
                working_is_ascii = None
                working_has_quote = None

        if sentinel_to_placeholder:
            working_text = sentinel_pattern.sub(
                lambda match: sentinel_to_placeholder.get(match.group(0), match.group(0)),
                working_text,
            )

        if total_count > 0:
            active_vault.record_hits(total_count)
            if use_ai_hint:
                hint_line = AI_PROMPT_HINTS.get(self.language, AI_PROMPT_HINTS["zh"])
                if not any(working_text.startswith(h) for h in AI_PROMPT_HINTS.values()):
                    working_text = f"{hint_line}\n{working_text}"

        return SanitizeResult(
            sanitized_text=working_text,
            total_count=total_count,
            category_counts=category_counts,
        )

    def restore(self, text: str, *, vault: Optional[SessionVault] = None) -> RestoreResult:
        """Restore all placeholders in `text` back to their original sensitive values (2-stage exact + fuzzy)."""
        if len(text) > MAX_SANITIZE_CHARS:
            raise InputTooLargeError()
        if not text:
            return RestoreResult(restored_text=text, restored_count=0)

        active_vault = self.vault if vault is None else vault
        working_text = text
        # Strip optional AI prompt hint header if present so roundtrips remain lossless.
        for hint_line in AI_PROMPT_HINTS.values():
            if working_text.startswith(hint_line + "\r\n"):
                working_text = working_text[len(hint_line) + 2:]
                break
            if working_text.startswith(hint_line + "\n"):
                working_text = working_text[len(hint_line) + 1:]
                break

        placeholders = active_vault.snapshot_placeholders()
        if not placeholders:
            return RestoreResult(restored_text=working_text, restored_count=0)

        restored_count = 0
        sentinel_to_original: Dict[str, str] = {}
        res_prefix = f"\x00\x02__RES_{secrets.token_hex(6)}_"
        while res_prefix in working_text:
            res_prefix += "\x00"

        # Stage 1: Exact Replacement (Longest placeholder first + sentinel protection)
        for idx, (ph, orig, _) in enumerate(placeholders, start=1):
            if ph not in working_text:
                continue
            sentinel = f"{res_prefix}{idx}__\x02\x00"
            working_text, occurrences = re.subn(
                _placeholder_pattern(ph), lambda _match: sentinel, working_text
            )
            if occurrences:
                sentinel_to_original[sentinel] = orig
                restored_count += occurrences

        # Stage 2: Fuzzy & Case-Insensitive Replacement for AI-mutated bracketed placeholders only
        for idx, (ph, orig, _) in enumerate(placeholders, start=1):
            sentinel = f"{res_prefix}{idx}__\x02\x00"
            core = ph[1:-1] if len(ph) > 2 and ph[0] in "[<{" and ph[-1] in "]}>" else ""
            if not (core and re.match(r"^[A-Za-z0-9_]+_\d+$", core)):
                continue
            esc_core = re.escape(core)
            fuzzy_rx = re.compile(
                r"(?i)(?:&lt;\s*"
                + esc_core
                + r"\s*&gt;|\[\s*"
                + esc_core
                + r"\s*\]|<\s*"
                + esc_core
                + r"\s*>|\{\s*"
                + esc_core
                + r"\s*\}|`\s*"
                + esc_core
                + r"\s*`)"
            )

            def _fuzzy_sub(match: re.Match, s_tok: str = sentinel, o_val: str = orig) -> str:
                nonlocal restored_count
                matched = match.group(0)
                if res_prefix in matched:
                    return matched
                sentinel_to_original[s_tok] = o_val
                restored_count += 1
                return s_tok

            working_text = fuzzy_rx.sub(_fuzzy_sub, working_text)

        if sentinel_to_original:
            res_pattern = re.compile(re.escape(res_prefix) + r"\d+__\x02\x00")
            working_text = res_pattern.sub(
                lambda match: sentinel_to_original.get(match.group(0), match.group(0)),
                working_text,
            )

        return RestoreResult(
            restored_text=working_text,
            restored_count=restored_count,
        )

    def clear_session(self) -> int:
        """Clear all in-memory mappings and return cleared entry count."""
        return self.vault.clear()
