"""Safe non-destructive batch file and directory sanitization / restoration."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import stat
from typing import Dict, List, Optional, Sequence, Tuple

from src.sanitizer import InputTooLargeError, MAX_SANITIZE_CHARS, PrivacySanitizer
from src.secure_io import atomic_write_private, validate_private_path


SUPPORTED_TEXT_EXTENSIONS = frozenset({
    ".env",
    ".log",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".txt",
    ".ini",
    ".conf",
    ".cfg",
    ".toml",
    ".xml",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".sh",
    ".ps1",
    ".sql",
    ".properties",
    ".tf",
    ".hcl",
})

SKIP_DIR_NAMES = frozenset({
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
})


@dataclass
class BatchProcessResult:
    """Summary of a batch file / folder sanitization or restoration run."""

    mode: str
    output_root: Path
    processed_files: List[Tuple[Path, Path, int]] = field(default_factory=list)
    skipped_files: List[Tuple[Path, str]] = field(default_factory=list)
    total_hits: int = 0
    category_counts: Dict[str, int] = field(default_factory=dict)


def _is_reparse_or_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    return bool(stat.S_ISLNK(info.st_mode) or (getattr(info, "st_file_attributes", 0) & 0x400))


def has_supported_extension(path: Path) -> bool:
    """Return True if file extension (or .env* name) is a supported text/config/log file."""
    name_lower = path.name.lower()
    if name_lower == ".env" or name_lower.startswith(".env."):
        return True
    return path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS


def is_supported_text_file(path: Path) -> bool:
    """Return True if `path` is a regular supported text file without binary NUL bytes."""
    if not has_supported_extension(path):
        return False
    if _is_reparse_or_link(path):
        return False
    try:
        if not path.is_file():
            return False
        with path.open("rb") as stream:
            chunk = stream.read(4096)
        if b"\x00" in chunk:
            return False
        return True
    except OSError:
        return False


def _next_nonclobber_file(candidate: Path) -> Path:
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    idx = 2
    while True:
        alt = candidate.with_name(f"{stem}_{idx}{suffix}")
        if not alt.exists():
            return alt
        idx += 1


def _next_nonclobber_dir(candidate: Path) -> Path:
    if not candidate.exists():
        return candidate
    idx = 2
    while True:
        alt = candidate.with_name(f"{candidate.name}_{idx}")
        if not alt.exists():
            return alt
        idx += 1


def collect_batch_files(
    inputs: Sequence[Path],
) -> Tuple[List[Tuple[Path, Path]], List[Tuple[Path, str]]]:
    """Collect (source_path, relative_output_path) pairs while preserving directory structure."""
    collected: List[Tuple[Path, Path]] = []
    skipped: List[Tuple[Path, str]] = []
    used_rel_paths: set[str] = set()

    def _unique_rel(rel: Path) -> Path:
        key = rel.as_posix().lower()
        if key not in used_rel_paths:
            used_rel_paths.add(key)
            return rel
        idx = 2
        while True:
            alt = rel.with_name(f"{rel.stem}_{idx}{rel.suffix}")
            alt_key = alt.as_posix().lower()
            if alt_key not in used_rel_paths:
                used_rel_paths.add(alt_key)
                return alt
            idx += 1

    single_dir = len(inputs) == 1 and Path(inputs[0]).is_dir()

    for raw_item in inputs:
        item = Path(raw_item)
        if _is_reparse_or_link(item):
            skipped.append((item, "linked path skipped"))
            continue
        if not item.exists():
            skipped.append((item, "missing path"))
            continue
        if item.is_file():
            if not is_supported_text_file(item):
                skipped.append((item, "unsupported or binary file"))
                continue
            collected.append((item, _unique_rel(Path(item.name))))
        elif item.is_dir():
            base_name = item.name or "batch"
            for root_str, dirnames, filenames in os.walk(item, followlinks=False):
                root_path = Path(root_str)
                dirnames[:] = sorted(
                    d
                    for d in dirnames
                    if d not in SKIP_DIR_NAMES and not _is_reparse_or_link(root_path / d)
                )
                for fname in sorted(filenames):
                    fpath = root_path / fname
                    if not has_supported_extension(fpath):
                        continue
                    if not is_supported_text_file(fpath):
                        skipped.append((fpath, "binary or linked file skipped"))
                        continue
                    sub_rel = fpath.relative_to(item)
                    rel_candidate = sub_rel if single_dir else (Path(base_name) / sub_rel)
                    rel = _unique_rel(rel_candidate)
                    collected.append((fpath, rel))
        else:
            skipped.append((item, "unsupported entry"))

    return collected, skipped


def process_batch_paths(
    sanitizer: PrivacySanitizer,
    inputs: Sequence[Path],
    *,
    mode: str = "sanitize",
    output_dir: Optional[Path] = None,
) -> BatchProcessResult:
    """Process one or more files/folders using a shared `SessionVault`, never overwriting sources."""
    if mode not in ("sanitize", "restore"):
        raise ValueError(f"Unsupported batch mode: {mode}")
    normalized_inputs = [Path(p) for p in inputs if str(p or "").strip()]
    if not normalized_inputs:
        raise ValueError("No input paths provided")

    files, skipped = collect_batch_files(normalized_inputs)
    tag = "sanitized" if mode == "sanitize" else "restored"

    is_single_file = len(normalized_inputs) == 1 and normalized_inputs[0].is_file()
    if output_dir is not None:
        out_root = Path(output_dir)
        out_root.mkdir(parents=True, exist_ok=True)
    elif is_single_file:
        out_root = normalized_inputs[0].parent
    else:
        anchor = normalized_inputs[0]
        base_label = anchor.name if anchor.is_dir() else "batch"
        out_root = _next_nonclobber_dir(anchor.parent / f"{base_label}_{tag}")

    result = BatchProcessResult(
        mode=mode,
        output_root=out_root,
        skipped_files=list(skipped),
    )

    if not files:
        return result

    if output_dir is not None or not is_single_file:
        out_root.mkdir(parents=True, exist_ok=True)

    for src_path, rel_path in files:
        try:
            validate_private_path(src_path)
            with src_path.open(encoding="utf-8", errors="replace") as stream:
                raw_text = stream.read(MAX_SANITIZE_CHARS + 1)
            if len(raw_text) > MAX_SANITIZE_CHARS:
                raise InputTooLargeError()
        except InputTooLargeError:
            result.skipped_files.append((src_path, "exceeds size limit"))
            continue
        except OSError:
            result.skipped_files.append((src_path, "unreadable or linked file"))
            continue

        if is_single_file and output_dir is None:
            if src_path.name.lower() == ".env":
                candidate = out_root / f".env.{tag}"
            elif src_path.suffix:
                candidate = out_root / f"{src_path.stem}.{tag}{src_path.suffix}"
            else:
                candidate = out_root / f"{src_path.name}.{tag}"
            dest_path = _next_nonclobber_file(candidate)
        else:
            dest_path = _next_nonclobber_file(out_root / rel_path)

        try:
            if dest_path.resolve() == src_path.resolve():
                result.skipped_files.append((src_path, "destination collides with source"))
                continue
        except OSError:
            result.skipped_files.append((src_path, "path resolution failed"))
            continue

        if mode == "sanitize":
            san = sanitizer.sanitize(raw_text)
            out_text = san.sanitized_text
            hits = san.total_count
            for cat, cnt in san.category_counts.items():
                result.category_counts[cat] = result.category_counts.get(cat, 0) + cnt
        else:
            res = sanitizer.restore(raw_text)
            out_text = res.restored_text
            hits = res.restored_count

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_private(dest_path, out_text, overwrite=False)
        except OSError:
            result.skipped_files.append((src_path, "failed to write output"))
            continue

        result.processed_files.append((src_path, dest_path, hits))
        result.total_hits += hits

    return result
