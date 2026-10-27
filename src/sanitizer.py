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
from typing import Any, Dict, List, Optional, Tuple

from src.rules import BUILTIN_RULES, SanitizeRule
from src.secure_io import atomic_write_private, validate_private_path

MAX_SANITIZE_CHARS = 1_500_000


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

            while placeholder in self._placeholder_to_original or placeholder == original:
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

    def save_to_file(self, path: Path) -> None:
        """Export current session mappings atomically to a JSON file with restricted permissions."""
        target = Path(path)
        with self._lock:
            payload = {
                "original_to_placeholder": dict(self._original_to_placeholder),
                "placeholder_to_original": dict(self._placeholder_to_original),
                "original_to_category": dict(self._original_to_category),
                "category_counters": dict(self._category_counters),
                "total_intercepted_hits": self._total_intercepted_hits,
            }
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

    def load_from_file(self, path: Path) -> None:
        """Validate the entire imported state before merging it into the live vault."""
        source = validate_private_path(path)
        if not source.exists():
            return
        raw = json.loads(source.read_text(encoding="utf-8"))
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

    def save_config(self, new_config: Optional[Dict[str, Any]] = None) -> None:
        """Persist current or provided configuration dictionary to `config.json` atomically."""
        with self._config_lock:
            candidate = self._config_data if new_config is None else new_config
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
    def normalize_hotkeys(sanitize_hotkey: str, restore_hotkey: str) -> Dict[str, str]:
        """Validate a candidate without changing settings or writing to disk."""
        san_clean = re.sub(r"\s+", "", str(sanitize_hotkey or "").strip().lower())
        res_clean = re.sub(r"\s+", "", str(restore_hotkey or "").strip().lower())
        if not san_clean or not res_clean:
            raise ValueError("Hotkey cannot be empty")
        if san_clean == res_clean:
            raise ValueError("Sanitize and Restore hotkeys must be different")
        if not re.match(r"^[a-z0-9_+/\-]+$", san_clean) or not re.match(
            r"^[a-z0-9_+/\-]+$", res_clean
        ):
            raise ValueError("Invalid hotkey format")
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

    def export_config(self, target_path: Path) -> None:
        """Export current `config.json` to `target_path`."""
        self.reload_config()
        atomic_write_private(
            target_path, json.dumps(self._config_data, indent=2, ensure_ascii=False)
        )

    def import_config(self, source_path: Path) -> Dict[str, Any]:
        """Import and merge/replace configuration from `source_path`."""
        raw = Path(source_path).read_text(encoding="utf-8")
        imported = json.loads(raw)
        if not isinstance(imported, dict) or "custom_dictionary" not in imported:
            raise ValueError("Invalid config format: missing 'custom_dictionary'")
        with self._config_lock:
            self.save_config(imported)
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

    def sanitize(self, text: str) -> SanitizeResult:
        """Sanitize text using Layer 1 (Custom Dictionary) followed by Layer 2 (Regex Rules)."""
        if len(text) > MAX_SANITIZE_CHARS:
            raise InputTooLargeError()
        if not text:
            return SanitizeResult(sanitized_text=text, total_count=0, category_counts={})

        semantic_ip = self.semantic_ip_mode
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

        def unprotect(value: str) -> str:
            return sentinel_pattern.sub(
                lambda match: sentinel_to_placeholder.get(match.group(0), match.group(0)), value
            )

        def protected_sub(pattern: re.Pattern, replacer) -> str:
            # Do not let short dictionary terms or rules rewrite fragments inside a marker.
            spans = [match.span() for match in sentinel_pattern.finditer(working_text)]
            starts = [start for start, _ in spans]
            ends = [end for _, end in spans]

            def guarded(match: re.Match) -> str:
                first = bisect_right(ends, match.start())
                last = bisect_left(starts, match.end()) - 1
                if first <= last and (
                    match.start() > starts[first] or match.end() < ends[last]
                ):
                    return match.group(0)
                return replacer(match)

            return pattern.sub(guarded, working_text)

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
        for existing_ph, _, _ in self.vault.snapshot_placeholders():
            if existing_ph in working_text:
                working_text = re.sub(
                    _placeholder_pattern(existing_ph),
                    lambda _match, ph=existing_ph: allocate_sentinel(ph), working_text,
                )

        # --- Layer 1: Custom High-Risk Dictionary (Sorted Longest to Shortest, Case-Insensitive) ---
        for term, category in self._get_sorted_custom_terms():
            if term.lower() in allowlist_lower:
                continue
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            if not pattern.search(working_text):
                continue

            def _dict_replacer(match: re.Match, cat: str = category) -> str:
                matched_val = match.group(0)
                if matched_val in sentinel_to_placeholder:
                    return matched_val
                matched_val = unprotect(matched_val)
                if matched_val.lower() in allowlist_lower:
                    return matched_val
                ph = self.vault.get_or_create_placeholder(
                    original=matched_val,
                    category=cat,
                    template="[{category}_{index}]",
                    semantic_ip_mode=semantic_ip,
                )
                record_hit(cat)
                return allocate_sentinel(ph)

            working_text = protected_sub(pattern, _dict_replacer)

        # --- Layer 2: Built-in High-Strength Regex Engine ---
        for rule in self.rules:
            if not rule.enabled_by_default or rule.name in disabled_set:
                continue

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
                    ph = self.vault.get_or_create_placeholder(
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

                ph = self.vault.get_or_create_placeholder(
                    original=original_match,
                    category=current_rule.category,
                    template=current_rule.placeholder_template,
                    semantic_ip_mode=semantic_ip,
                )
                record_hit(current_rule.category)
                return allocate_sentinel(ph)

            working_text = protected_sub(rule.pattern, _rule_replacer)

        for sentinel, ph in sentinel_to_placeholder.items():
            working_text = working_text.replace(sentinel, ph)

        if total_count > 0:
            self.vault.record_hits(total_count)

        return SanitizeResult(
            sanitized_text=working_text,
            total_count=total_count,
            category_counts=category_counts,
        )

    def restore(self, text: str) -> RestoreResult:
        """Restore all placeholders in `text` back to their original sensitive values (2-stage exact + fuzzy)."""
        if not text:
            return RestoreResult(restored_text=text, restored_count=0)

        placeholders = self.vault.snapshot_placeholders()
        if not placeholders:
            return RestoreResult(restored_text=text, restored_count=0)

        working_text = text
        restored_count = 0
        sentinel_to_original: Dict[str, str] = {}
        res_prefix = f"\x00\x02__RES_{secrets.token_hex(6)}_"

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

        for sentinel, orig in sentinel_to_original.items():
            working_text = working_text.replace(sentinel, orig)

        return RestoreResult(
            restored_text=working_text,
            restored_count=restored_count,
        )

    def clear_session(self) -> int:
        """Clear all in-memory mappings and return cleared entry count."""
        return self.vault.clear()
