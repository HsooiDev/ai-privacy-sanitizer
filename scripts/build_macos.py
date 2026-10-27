"""Build experimental native macOS app/DMG artifacts without publishing a release."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "AI-Privacy-Sanitizer"
BUNDLE_ID = "io.github.hsooidev.ai-privacy-sanitizer"


def validate_host(architecture: str) -> None:
    if platform.system() != "Darwin":
        raise RuntimeError("A native macOS runner is required; Linux/Windows cannot build this app")
    if platform.machine() != architecture:
        raise RuntimeError("Use a macOS runner and Python matching the requested architecture")


def run(command, *, timeout=1800, **kwargs):
    return subprocess.run(command, cwd=ROOT, check=True, timeout=timeout, **kwargs)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build(architecture: str) -> Path:
    validate_host(architecture)
    sys.path.insert(0, str(ROOT))
    from src import __version__
    from src.main import create_shield_lock_icon

    output = ROOT / "dist" / "macos" / architecture
    output.mkdir(parents=True, exist_ok=True)
    icon = ROOT / "work" / "macos" / f"icon-{architecture}.icns"
    icon.parent.mkdir(parents=True, exist_ok=True)
    create_shield_lock_icon(1024).save(icon, format="ICNS")
    environment = os.environ.copy()
    environment["APS_MACOS_ARCH"] = architecture
    run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", str(output), "--workpath", str(ROOT / "build" / "macos" / architecture),
        str(ROOT / f"{APP_NAME}-macOS.spec"),
    ], env=environment)

    app = output / f"{APP_NAME}.app"
    with (app / "Contents" / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    if info.get("CFBundleIdentifier") != BUNDLE_ID or info.get("CFBundleVersion") != __version__:
        raise RuntimeError("Unexpected bundle identity or version")
    binary = app / "Contents" / "MacOS" / APP_NAME
    actual_arch = run(["lipo", "-archs", str(binary)], capture_output=True, text=True).stdout.split()
    if actual_arch != [architecture]:
        raise RuntimeError("Bundle executable does not match the requested architecture")
    run(["codesign", "--verify", "--deep", "--strict", str(app)])
    # Synthetic self-test uses its own temporary configuration; no GUI or user settings.
    run([str(binary), "--self-test"], timeout=30, capture_output=True, text=True)

    stem = f"{APP_NAME}-{__version__}-macOS-{architecture}-experimental"
    zipped = output / f"{stem}.zip"
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(zipped)])
    image = output / f"{stem}.dmg"
    with tempfile.TemporaryDirectory(prefix="aps-dmg-") as temporary:
        staging = Path(temporary)
        run(["ditto", str(app), str(staging / app.name)])
        (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
        run([
            "hdiutil", "create", "-volname", "AI Privacy Sanitizer", "-srcfolder", str(staging),
            "-format", "UDZO", "-ov", str(image),
        ])
    run(["hdiutil", "verify", str(image)])

    # Hash only known source/build inputs; never include local config or vault files.
    source_files = sorted((ROOT / "src").glob("*.py")) + [
        ROOT / f"{APP_NAME}-macOS.spec", ROOT / "scripts" / "build_macos.py",
        ROOT / "config.example.json", ROOT / "requirements-lock.txt", ROOT / "requirements-macos-lock.txt",
    ]
    source_hash = hashlib.sha256()
    for path in source_files:
        source_hash.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
        source_hash.update(bytes.fromhex(digest(path)))
    metadata = {
        "version": __version__, "architecture": architecture,
        "source_commit": run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "source_tree_sha256": source_hash.hexdigest(),
        "source_dirty": bool(run(
            ["git", "status", "--porcelain", "--", "src", "scripts", f"{APP_NAME}-macOS.spec",
             "config.example.json", "requirements-lock.txt", "requirements-macos-lock.txt"],
            capture_output=True, text=True,
        ).stdout.strip()),
        "python": platform.python_version(), "macos": platform.mac_ver()[0],
        "code_signing": "ad-hoc", "notarized": False, "experimental": True,
        "packaged_cli_self_test": "passed", "gui_and_permissions_tested": False,
        "workflow_run": os.environ.get("GITHUB_RUN_ID"),
    }
    manifest = output / "build-info.json"
    manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    checksums = "".join(f"{digest(path)}  {path.name}\n" for path in (zipped, image, manifest))
    (output / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("arm64", "x86_64"), required=True)
    args = parser.parse_args(argv)
    try:
        output = build(args.arch)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 2
    print(f"Experimental macOS artifacts: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
