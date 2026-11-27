"""Read-only CLI secret scanner for files, directories, and Git staged diffs (--scan / --git-staged)."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
from typing import List, Optional, Tuple

from src.file_batch import SKIP_DIR_NAMES, _is_reparse_or_link, is_supported_text_file
from src.sanitizer import InputTooLargeError, MAX_SANITIZE_CHARS, PrivacySanitizer, SessionVault
from src.secure_io import validate_private_path


_PEM_BLOCK_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----"
    r"[\s\S]{1,32768}?"
    r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----"
)
_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class ScanFinding:
    """Represents one redacted secret finding without exposing plaintext."""

    file_path: str
    line_number: int
    category: str
    masked_excerpt: str


def mask_secret_for_terminal(secret: str) -> str:
    """Strictly mask secrets for terminal output so plaintext never leaks to CI logs."""
    cleaned = str(secret or "").replace("\r", " ").replace("\n", " ").strip()
    n = len(cleaned)
    if n <= 4:
        return "*" * max(1, n)
    if n <= 8:
        return f"{cleaned[0]}{'*' * (n - 2)}{cleaned[-1]}"
    return f"{cleaned[:2]}{'*' * 6}{cleaned[-2:]} (len={n})"


def scan_text_lines(
    sanitizer: PrivacySanitizer,
    text: str,
    file_label: str,
    *,
    line_offset: int = 1,
    entropy_enabled: Optional[bool] = None,
) -> List[ScanFinding]:
    """Scan `text` strictly read-only in an isolated vault and return masked findings with line numbers."""
    if not text:
        return []
    if len(text) > MAX_SANITIZE_CHARS:
        raise InputTooLargeError()

    findings: List[ScanFinding] = []
    working = text

    # Detect multi-line PEM/PGP blocks first so line numbers point to the block start.
    if "-----BEGIN " in working:
        def _blank_pem(match: re.Match) -> str:
            block = match.group(0)
            start_line = line_offset + working[: match.start()].count("\n")
            findings.append(
                ScanFinding(
                    file_path=file_label,
                    line_number=start_line,
                    category="PRIVATE_KEY",
                    masked_excerpt=mask_secret_for_terminal(block),
                )
            )
            return "\n" * block.count("\n")

        working = _PEM_BLOCK_RE.sub(_blank_pem, working)

    for rel_idx, line in enumerate(working.splitlines()):
        if not line.strip():
            continue
        vault = SessionVault()
        res = sanitizer.sanitize(
            line,
            vault=vault,
            include_ai_hint=False,
            entropy_enabled=entropy_enabled,
        )
        if res.total_count == 0:
            continue
        for _ph, orig, cat in res.matched_items:
            findings.append(
                ScanFinding(
                    file_path=file_label,
                    line_number=line_offset + rel_idx,
                    category=cat,
                    masked_excerpt=mask_secret_for_terminal(orig),
                )
            )

    findings.sort(key=lambda item: (item.file_path, item.line_number, item.category))
    return findings


def scan_path(
    sanitizer: PrivacySanitizer,
    target: Path,
    *,
    entropy_enabled: Optional[bool] = None,
) -> Tuple[List[ScanFinding], int]:
    """Scan a single file or directory recursively in read-only mode."""
    target_path = Path(target)
    if _is_reparse_or_link(target_path):
        raise OSError("Linked paths are not scanned")
    if not target_path.exists():
        raise FileNotFoundError(str(target_path))

    findings: List[ScanFinding] = []
    files_scanned = 0

    def _scan_one(fpath: Path, label: str) -> None:
        nonlocal files_scanned
        validate_private_path(fpath)
        with fpath.open(encoding="utf-8", errors="replace") as stream:
            raw = stream.read(MAX_SANITIZE_CHARS + 1)
        if len(raw) > MAX_SANITIZE_CHARS:
            raise InputTooLargeError()
        files_scanned += 1
        findings.extend(
            scan_text_lines(sanitizer, raw, label, line_offset=1, entropy_enabled=entropy_enabled)
        )

    if target_path.is_file():
        _scan_one(target_path, target_path.name)
        return findings, files_scanned

    if target_path.is_dir():
        for root_str, dirnames, filenames in os.walk(target_path, followlinks=False):
            root_path = Path(root_str)
            dirnames[:] = sorted(
                d
                for d in dirnames
                if d not in SKIP_DIR_NAMES and not _is_reparse_or_link(root_path / d)
            )
            for fname in sorted(filenames):
                fpath = root_path / fname
                if not is_supported_text_file(fpath):
                    continue
                rel_label = fpath.relative_to(target_path).as_posix()
                try:
                    _scan_one(fpath, rel_label)
                except (InputTooLargeError, OSError):
                    continue
        return findings, files_scanned

    raise ValueError("Unsupported scan target")


def parse_unified_diff_added_hunks(diff_text: str) -> List[Tuple[str, int, str]]:
    """Parse unified=0 git diff into (relative_path, start_line, added_block) tuples."""
    hunks: List[Tuple[str, int, str]] = []
    current_file: Optional[str] = None
    hunk_start_line: Optional[int] = None
    added_lines: List[str] = []

    def _flush() -> None:
        nonlocal hunk_start_line, added_lines
        if current_file is not None and hunk_start_line is not None and added_lines:
            hunks.append((current_file, hunk_start_line, "\n".join(added_lines)))
        hunk_start_line = None
        added_lines = []

    for line in (diff_text or "").splitlines():
        if line.startswith("diff --git "):
            _flush()
            current_file = None
            continue
        if line.startswith("+++ b/"):
            _flush()
            current_file = line[6:].strip()
            continue
        if line.startswith("+++ /dev/null"):
            _flush()
            current_file = None
            continue
        m = _HUNK_HEADER_RE.match(line)
        if m:
            _flush()
            hunk_start_line = int(m.group(1))
            continue
        if hunk_start_line is not None and line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])

    _flush()
    return hunks


def scan_git_staged(
    sanitizer: PrivacySanitizer,
    repo_dir: Optional[Path] = None,
    *,
    entropy_enabled: Optional[bool] = None,
) -> Tuple[List[ScanFinding], int]:
    """Scan Git staged diff (`git diff --cached --unified=0`) strictly read-only."""
    cwd = str(repo_dir) if repo_dir is not None else None
    proc = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color"],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff --cached failed")

    hunks = parse_unified_diff_added_hunks(proc.stdout)
    findings: List[ScanFinding] = []
    scanned_files = set()
    for rel_path, start_line, block in hunks:
        scanned_files.add(rel_path)
        findings.extend(
            scan_text_lines(
                sanitizer,
                block,
                rel_path,
                line_offset=start_line,
                entropy_enabled=entropy_enabled,
            )
        )
    return findings, len(scanned_files)


def format_scan_report(
    findings: List[ScanFinding],
    files_scanned: int,
    *,
    as_json: bool = False,
    lang: str = "en",
) -> str:
    """Format strictly masked scan findings for terminal or CI output."""
    if as_json:
        payload = {
            "files_scanned": files_scanned,
            "finding_count": len(findings),
            "findings": [
                {
                    "file": f.file_path,
                    "line": f.line_number,
                    "category": f.category,
                    "masked_excerpt": f.masked_excerpt,
                }
                for f in findings
            ],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    if not findings:
        if lang == "zh":
            return f"OK: 已扫描 {files_scanned} 个文件，未发现敏感信息泄露。"
        return f"OK: Scanned {files_scanned} file(s); no secrets detected."

    lines = []
    if lang == "zh":
        lines.append(f"ALERT: 在 {files_scanned} 个文件中发现 {len(findings)} 处疑似敏感信息（已脱敏展示）：")
    else:
        lines.append(f"ALERT: Detected {len(findings)} potential secret(s) across {files_scanned} file(s) (masked):")
    for f in findings:
        lines.append(f"  {f.file_path}:{f.line_number} [{f.category}] {f.masked_excerpt}")
    return "\n".join(lines)
