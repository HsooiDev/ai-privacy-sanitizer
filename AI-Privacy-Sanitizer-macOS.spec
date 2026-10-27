# Native macOS onedir application bundle; invoke through scripts/build_macos.py.
import os
from pathlib import Path
import sys

if sys.platform != "darwin":
    raise SystemExit("The macOS application must be built on macOS")

from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH)
sys.path.insert(0, str(root))
from src import __version__

architecture = os.environ.get("APS_MACOS_ARCH")
if architecture not in ("arm64", "x86_64"):
    raise SystemExit("Select a native architecture through scripts/build_macos.py")
icon = root / "work" / "macos" / f"icon-{architecture}.icns"
datas, binaries, hiddenimports = collect_all("customtkinter")
datas += [(str(root / "config.example.json"), ".")]
hiddenimports += [
    "pystray._darwin", "keyboard._darwinkeyboard",
    "plyer.platforms.macosx.notification", "AppKit", "Foundation", "Quartz", "objc",
]

analysis = Analysis(
    [str(root / "src" / "main.py")], pathex=[str(root)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=["pytest", "unittest", "pdb", "pydoc"], noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive, analysis.scripts, [], exclude_binaries=True,
    name="AI-Privacy-Sanitizer", console=False, debug=False,
    strip=False, upx=False, argv_emulation=False,
    target_arch=architecture, codesign_identity="-", icon=str(icon),
)
collection = COLLECT(
    executable, analysis.binaries, analysis.datas,
    strip=False, upx=False, name="AI-Privacy-Sanitizer",
)
application = BUNDLE(
    collection, name="AI-Privacy-Sanitizer.app", icon=str(icon),
    bundle_identifier="io.github.hsooidev.ai-privacy-sanitizer",
    version=__version__,
    info_plist={
        "CFBundleDisplayName": "AI Privacy Sanitizer",
        "CFBundleVersion": __version__,
        "LSMinimumSystemVersion": "15.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "Copyright HsooiDev. MIT License.",
    },
)
