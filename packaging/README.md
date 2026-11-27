# Packaging & Unblocked Windows Launchers

## 1. Windows 11 Smart App Control Friendly Portable Launchers
On Windows 11 devices with **Smart App Control** enabled, unsigned standalone `.exe` binaries may be blocked by OS policy.
Instead of disabling Windows security features, double-click **`run-sanitizer.vbs`** (no black console window) or **`run-sanitizer.bat`** in the repository root. Both invoke the signed official Python runtime (`pythonw.exe`) directly on `src.main`.

## 2. Scoop Manifest Template (`packaging/scoop/ai-privacy-sanitizer.json`)
After publishing a GitHub Release tag (e.g. `v0.6.0`), replace `REPLACE_WITH_RELEASE_SHA256` with the SHA-256 from the release's `SHA256SUMS` asset and submit to your Scoop bucket (or install locally via `scoop install ./packaging/scoop/ai-privacy-sanitizer.json`).

## 3. Winget Manifest Template (`packaging/winget/HsooiDev.AIPrivacySanitizer.yaml`)
Replace `REPLACE_WITH_RELEASE_SHA256` with the release `Sanitizer.exe` SHA-256 and validate with `winget validate --manifest packaging/winget/`.

## 4. Optional CI Authenticode Signing
`.github/workflows/ci-build.yml` checks `secrets.WINDOWS_CODESIGN_PFX_BASE64` and `secrets.WINDOWS_CODESIGN_PASSWORD` during tag releases. When configured, `dist/Sanitizer.exe` is signed with SHA-256 + RFC3161 timestamping before `SHA256SUMS` generation; when unconfigured, the step skips cleanly without blocking releases.
