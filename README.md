<div align="center">

# 🛡️ AI Privacy Sanitizer `v0.5.0`

**Local Processing · RAM Vault by Default · Zero Network Requests · Sidebar GUI Control Center · AES-256-GCM Encrypted Export · Zero-Permission Browser Extension · Lossless Bidirectional Sanitizer**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20Preview%20%7C%20Linux%20%7C%20Web%20%7C%20MV3%20Ext-059669.svg)](#)
[![Zero Network](https://img.shields.io/badge/Privacy-Local%20Processing-10b981.svg)](#security-commitment)

[**English**](README.md) | [**简体中文**](README.zh-CN.md)

</div>

---

## 💡 Why AI Privacy Sanitizer?

When debugging production incidents, reviewing code, or analyzing server logs with cloud LLMs (**ChatGPT, Claude, DeepSeek, Gemini, Cursor**), pasting raw text directly from your terminal or IDE can easily leak:
- 🔑 **API Keys & Cloud Tokens** (`sk-...`, `sk_live_...`, `ghp_...`, `AKIA...`, `AIza...`, `xoxb-...`, `gsk_...`, `hf_...`, `npm_...`, `pypi-...`, `dop_v1_...`, `lin_api_...`, `sbp_...`, `PMAK-...`, `shpat_...`, Azure SAS `sig=...`, JWTs, Bearer tokens, `Authorization: Basic ...`, Slack/Discord/Feishu/DingTalk/WeCom Webhook URLs)
- 🗄️ **Database & Auth Secrets** (`postgres://`, `mysql://`, `mongodb://`, `redis://` including passwords containing `@`, ODBC connection strings, `.env` variables, `curl -u` credentials)
- 📜 **Multi-Line Private Keys** (`-----BEGIN RSA/OPENSSH PRIVATE KEY-----` & `-----BEGIN PGP PRIVATE KEY BLOCK-----`)
- 💻 **System File Path Usernames** (`C:\Users\<username>`, `/Users/<username>`, `/home/<username>` — handles trailing-slash-free and Unicode usernames while preserving path structure)
- 🌐 **Internal Infrastructure** (Private IPv4, Public IPv4 including `.0` last octets, compressed IPv6 like `2001:db8::8a2e:370:7334`, MAC addresses)
- 🪪 **Personal Identifiable Information (PII)** (Emails, International & Malaysian `+60` phone numbers, Malaysian MyKad NRIC with PB-code validation, Mainland China 18-digit ID with GB 11643-1999 checksum + real leap-year calendar validation, Passports, Luhn-validated Visa / Mastercard 2-series / Amex 15-digit / UnionPay 19-digit cards)
- 🏢 **Proprietary Business Entities** (Company names, Client names, Project codenames — with ASCII whole-word boundaries enabled by default so `art` never corrupts `Start`)

**AI Privacy Sanitizer** runs in your system tray and sanitizes clipboard text via global hotkeys (`Alt+S` to sanitize, `Alt+R` to restore) or best-effort **Cruise Mode**. Session mappings stay in RAM by default with configurable idle auto-wipe, OS clipboard history exclusion (`Win+V` / macOS `ConcealedType`), and optional **Scrypt + AES-256-GCM passphrase-encrypted local export**.

---

## ✨ Key Features (`v0.5.0`)

### 1. 🖥️ Sidebar Visual Control Center (`src/gui.py` & `src/hud.py`)
- **🧭 6-Page Sidebar Navigation**: Responsive layout across window sizes & DPI (Dashboard / Live Sandbox / Words & Rules / Session Vault / Hotkeys & Safety / Quick Guide) with live protection status, quick Cruise toggle, idle countdown, and zero-flicker in-place Theme & EN/ZH switching.
- **🏠 Dashboard & Local File Sanitize/Restore**: Live KPI cards (Intercepted Hits / Active Mappings / Active Rules `active/total`), one-click **📄 Local File Sanitize / Restore** (`.env`, `.log`, `.json`, `.yaml`, `.csv` with private atomic writes), **⏪ Undo Last Sanitize**, and **🤖 AI Prompt Preservation Hint** (automatically stripped on restore).
- **🧪 Isolated Sandbox + 5-Tier Risk Colors + Right-Click Allowlist**: Uses an isolated `SessionVault` by default so test snippets never pollute your clipboard vault (with one-click sync to Global Vault); highlights tags across 5 risk tiers (Red=Keys, Amber=DB/Passwords, Blue=Network/Paths, Purple=PII, Green=Business); **right-click any placeholder to add its original value to the Allowlist and re-run instantly**.
- **📚 Custom Dictionary + Scenario Rule Presets (`DevOps Recommended` / `Office / HR Full` / `Keys Only`)**: Searchable human-friendly rule labels & examples, ASCII whole-word toggle, dictionary-only config import, and an upgraded in-app JSON editor with Format JSON and line/col syntax error reporting.
- **🔐 Live RAM Vault + AES-256-GCM Encrypted Export (`src/vault_crypto.py`)**: Debounced search, paginated rendering (60 rows/page), per-row removal, anti-shoulder-surfing masking, and **Scrypt + AES-256-GCM** encrypted export/import.
- **🛡️ OS-Level Privacy & UX (`src/clipboard_privacy.py` & `src/hud.py`)**:
  - **Dynamic Tray Icon States** (Blue Ready / Emerald Cruise / Amber Active Vault) + high-DPI, multi-monitor-aware non-focus-stealing bottom-right **Floating Micro-HUD**.
  - **Clipboard History Privacy Guard**: Marks restored/undone secrets on Windows with `ExcludeClipboardContentFromMonitorProcessing`, `CanIncludeInClipboardHistory=0`, and `CanUploadToCloudClipboard=0` (and `ConcealedType`/`TransientType` on macOS).
  - **Desktop Idle Auto-Wipe**: Automatically clears RAM vault & undo snapshots after 5/10/15/30/60 minutes of inactivity.
  - **IDE-Style Instant Keybinding Recorder**: Click and press any combo (letters, digits, symbols, arrows, numpad + `Ctrl`/`Alt`/`Shift`/`Win`, or standalone `F1`–`F24`) or edit inline via `✏️` → `✓`; applies immediately, syncs the Quick Guide & Dashboard live, reports exact conflicting shortcuts, and automatically falls back from `Alt+R` if occupied by GPU overlays.

### 2. 🧠 High-Performance Two-Layer Engine (`src/sanitizer.py` & `src/rules.py`)
- **47 Built-in Precision Detectors + C-Level Prefilters**: Zero-backtracking boundary anchors, `fast_tokens` prefiltering, and lazy sentinel span caching — processes a 500KB log in ~0.7s and rejects unclosed 500KB PEM blocks in ~0.22s with zero ReDoS risk.
- **Semantic Disguise Mode (RFC 5737 & Synthetic Entities)**: Replaces real private IPs with `192.0.2.101`, public IPs with `203.0.113.101`, emails with `user1@example.com`, and OS usernames with `dev_user_1` while keeping restoration lossless.
- **Two-Stage Exact + Fuzzy Restore**: Recovers original values even if an LLM rewrites `<API_KEY_1>` into `[API_KEY_1]`, `` `API_KEY_1` ``, `<api_key_1>`, `{API_KEY_1}`, or `&lt;API_KEY_1&gt;`, and enforces the `1,500,000`-char input cap on `restore()` too.

### 3. 🌐 CSP-Locked Web Edition + 🧩 Zero-Permission Browser Extension + ⌨️ Enhanced CLI
- **Standalone RAM-Only Web Edition (`web/index.html`)**: Enforces browser-level CSP (`default-src 'none'; connect-src 'none'; form-action 'none'`), maintains 100% rule parity with desktop (verified in CI via `scripts/sync_web_rules.py --check`), adds 250ms debounce, 5-tier risk-colored Diff Preview with **click-to-allowlist**, offline local file drop/export, idle progress bar, and Restore Default Safe Allowlist.
- **Zero-Permission Chromium MV3 Paste Guard (`browser-extension/`)**: Declares `permissions: []` with zero network requests and zero persistent storage; intercepts `Ctrl+V` on ChatGPT, Claude, Gemini, DeepSeek, and Poe when secrets are detected and offers one-click **🛡️ Sanitize & Paste / Paste Raw / Cancel**.
- **Developer CLI Pipeline (`src/main.py`)**: Supports `--stdin`, `--restore-stdin`, `--file`, `--restore-file`, `--output`, `--encoding`, `--vault-file`, `--encrypt`, `--passphrase-stdin`, and `--passphrase-env`.

---

## 🔄 3-Second Daily Workflow

```mermaid
flowchart TD
    A["1. Copy sensitive code/logs in your IDE or terminal (Ctrl + C)"] --> B["2. Press Alt + S (or Cruise Mode / Browser Extension Paste Guard) ──► Secrets masked<br/>e.g. postgres://admin:[DB_PASS_1]@192.0.2.101:5432/prod"]
    B --> C["3. Paste into ChatGPT / Claude / Gemini / DeepSeek & copy AI's reply"]
    C --> D["4. Press Alt + R ──► Placeholders (even AI-mutated ones) 100% restored locally!"]
```

---

## 🚀 Getting Started

### Option 1: Download & Open Standalone Windows `.exe` (Recommended)
1. **Download & Verify**: Download `Sanitizer.exe`, `SHA256SUMS`, and `build-info.json` from [GitHub Releases](https://github.com/HsooiDev/ai-privacy-sanitizer/releases) into a local folder (e.g., `D:\Tools\Sanitizer\Sanitizer.exe`, ideally outside OneDrive/cloud-synced folders). Verify integrity in PowerShell:
   ```powershell
   Get-FileHash .\Sanitizer.exe -Algorithm SHA256
   ```
2. **First Launch**: **Double-click** `Sanitizer.exe` in Windows File Explorer. On first launch, the **Sidebar Control Center** opens and places a dynamic shield icon in the system tray (closing the window with `×` minimizes to the tray to keep protecting your clipboard; use **Exit** in the tray menu to quit completely). If `Alt+R` is already taken by GPU overlays, startup automatically falls back to `Ctrl+Shift+R`.
3. **If Windows Security Prompts or Blocks the `.exe`**:
   - **Case A — Windows Defender SmartScreen ("Windows protected your PC")**:
     Because this open-source binary is not signed with a paid EV certificate, Windows may show a blue prompt on first run. Click **`More info`** → **`Run anyway`** to launch normally.
   - **Case B — Windows 11 Smart App Control / WDAC Policy Blocks Execution**:
     On systems enforcing strict unsigned-executable blocking (Smart App Control), Windows will refuse to start unsigned `.exe` binaries. You do **not** need to disable system security — simply use one of these clean alternatives:
     - **Run via Official Python (Recommended desktop alternative)**: Follow **Option 2** below and run `python -m src.main` to get the full desktop GUI, tray icon, and global hotkeys;
     - **Zero-install Browser Options**: Open `web/index.html` directly (**Option 3**) or load the extension in `browser-extension/` (**Option 4**).
4. **Private Config Location**: Windows `.exe` settings are stored separately in `%LOCALAPPDATA%\Sanitizer\config.json` so moving or upgrading the binary never loses your rules.

### Option 2: Run from Source / CLI Pipeline / Build `.exe` (Developers)

```powershell
# 1. Create virtual environment and install dependencies (includes cryptography for AES-256-GCM)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Run regression tests, Web security tests, and cross-platform rule parity check
python -m pytest -v
node tests/test_web_security.cjs
python scripts/sync_web_rules.py --check
python -m src.main --self-test

# 3. Developer CLI Pipeline with AES-256-GCM encrypted cross-process vault
$env:APS_VAULT_PASS = "YourStrongPassphrase"
python -m src.main --file .env.production --output .env.sanitized --vault-file vault.enc.json --encrypt --passphrase-env APS_VAULT_PASS
python -m src.main --restore-file ai_reply.txt --output restored.txt --vault-file vault.enc.json --passphrase-env APS_VAULT_PASS

# 4. Launch the desktop app from source
python -m src.main

# 5. Export multi-resolution icon & package standalone .exe (UPX disabled to reduce AV false positives)
python -m src.main --export-ico assets/icon.ico
python -m PyInstaller --noconfirm AI-Privacy-Sanitizer.spec
```

### Option 3: Pure In-Memory Web Edition
Open [`web/index.html`](web/index.html) directly in any modern browser (or host it as a single static HTML file). All sanitization, file drop/export, and restoration stay 100% inside tab RAM with strict CSP.

### Option 4: Zero-Permission Browser Paste Guard (Chrome / Edge / Brave)
Open `chrome://extensions/` → enable **Developer mode** → click **Load unpacked** → select [`browser-extension/`](browser-extension/) (see [`browser-extension/README.md`](browser-extension/README.md)).

### Option 5: Experimental macOS `.app` / `.dmg` (macOS 15+)

The Windows `.exe` cannot run natively on macOS. Trigger **Actions → Experimental macOS Build → Run workflow** for `arm64` (Apple Silicon) or `x86_64` (Intel). Artifacts are ad-hoc signed (not Apple-notarized), global hotkeys are disabled in this preview, and settings live privately at `~/Library/Application Support/AI-Privacy-Sanitizer/config.json`. Native Mac build:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-macos-lock.txt
python scripts/build_macos.py --arch arm64  # use x86_64 on Intel Mac
```

---

## 📘 Step-by-Step User Guide

Once the desktop app is open, use the 6 sidebar tabs as follows:

1. **🏠 Overview — Daily Sanitize, Restore & Local Files**
   - **Daily Clipboard Flow**: Copy code/logs containing secrets (`Ctrl+C`) → press `Alt+S` (the bottom-right Micro-HUD shows how many secrets were masked) → paste the safe placeholders into your AI chat → copy the AI reply and press `Alt+R` (or `Ctrl+Shift+R` if auto-fallback triggered) to restore original values locally. Need the raw pre-sanitized clipboard back? Click **⏪ Undo Last Sanitize**.
   - **Cruise Mode (Hands-Free Auto-Sanitize)**: Toggle **⚡ Auto-Sanitize on Copy** in the UI or tray menu. The tray icon turns emerald and checks clipboard changes every ~0.55s — always glance at the pasted text before submitting.
   - **Local File Sanitize / Restore**: Click **📄 Sanitize Local File** on `.env`, `.log`, `.json`, `.yaml`, or `.csv` files to produce a sanitized copy without overwriting your original file, then run **📥 Restore Local File** on the AI-edited output.

2. **🧪 Live Sandbox — Preview Safely & Right-Click Allowlist**
   - Paste any sample text into **Live Sandbox** to test rules in an isolated temporary vault without polluting your main session mappings (you can promote sandbox mappings to the main vault whenever ready).
   - Spotted a false positive (such as a release tag or harmless internal ID)? **Right-click that placeholder** in the preview pane to add its raw value to your Allowlist and refresh immediately.

3. **📚 Dictionary & Rules — Custom Terms & Presets**
   - **Custom Dictionary**: Add company domains, internal service names, client aliases, or test usernames (with optional whole-word matching for English tokens).
   - **Scenario Presets**: Switch between **Dev & Debug**, **HR & Legal**, and **Strict Full** presets, or toggle individual built-in rules on/off.

4. **🔐 Session Vault — Inspect, Copy Tag & Encrypted Export**
   - Browse active placeholder-to-secret mappings in RAM (masked with `***` by default for shoulder-surfing protection; search, toggle reveal, click **Copy Tag**, or delete individual rows).
   - Moving across machines or restarting? Use **Encrypted Export** with a passphrase to save an `AES-256-GCM` encrypted vault file and import it later.

5. **⚙️ Security & Hotkeys — Instant IDE-Style Binding & Auto-Wipe**
   - **Change Global Hotkeys**: Click any hotkey pill and press your desired combo (for example `Ctrl+Shift+S`) — it saves and registers immediately on release (`Esc` cancels). Prefer typing? Click `✏️`, type the shortcut, and press `Enter` or click the green `✓` to save instantly. Clicking **↺ Reset Default** automatically picks non-conflicting fallbacks if `Alt+R` is occupied by another app.
   - **Idle Auto-Wipe**: Enable automatic RAM vault clearing after 5–60 minutes of inactivity.

---

## ⌨️ Hotkeys & System Tray Guide

| Action | Default Hotkey | System Tray Menu Item | Description |
| :--- | :--- | :--- | :--- |
| **Open Control Center** | Left-click Tray Icon | `🖥️ Open Control Center` | Sidebar GUI for Dictionary, Rule Presets, Sandbox, Vault, and Settings |
| **Sanitize Clipboard** | `Alt + S` | `1. Sanitize Clipboard` | Replace sensitive clipboard strings with safe placeholders + Micro-HUD |
| **Restore Clipboard** | `Alt + R` | `2. Restore Clipboard` | Recover original values locally (with OS clipboard history protection) |
| **Undo Last Sanitize** | Button in UI / Tray | `⏪ Undo Last Sanitize` | Restore pre-sanitized raw clipboard content (up to 5 RAM snapshots) |
| **Cruise Mode** | Toggle in UI / Tray | `⚡ Auto-Sanitize on Copy` | Best-effort polling (~0.55s); tray shield turns emerald |
| **Windows Startup** | Toggle in UI / Tray | `🚀 Launch at Startup` | Launch silently in tray on Windows login (validates executable path) |
| **Clear Session Vault** | Button in UI / Tray | `4. Clear Session Map` | Immediately wipe all in-memory mappings and undo snapshots |
| **Exit Application** | Button in UI / Tray | `5. Exit` | Unhook global hotkeys and terminate cleanly |

---

## 📂 Project Structure

```text
ai-privacy-sanitizer/
├── .github/workflows/
│   └── ci-build.yml            # Multi-OS pytest, Web security, rule parity & Windows release CI
├── browser-extension/          # Zero-permission (permissions: []) Chromium MV3 Paste Guard
│   ├── manifest.json
│   ├── sanitizer_core.js
│   ├── content.js
│   ├── popup.html / popup.js
│   └── README.md
├── scripts/
│   ├── build_macos.py          # Experimental macOS .app/.dmg packager
│   └── sync_web_rules.py       # Python vs Web golden-case rule parity verifier
├── src/
│   ├── __init__.py             # Package version metadata (v0.5.0)
│   ├── main.py                 # Dynamic tray, HUD dispatch, idle auto-wipe, hotkeys, CLI pipes
│   ├── gui.py                  # CustomTkinter Sidebar Dark/Light bilingual Control Center
│   ├── hud.py                  # Non-focus-stealing bottom-right FloatingMicroHud
│   ├── clipboard_privacy.py    # Windows Win+V/Cloud & macOS Concealed clipboard exclusion
│   ├── vault_crypto.py         # Scrypt + AES-256-GCM authenticated vault encryption
│   ├── i18n.py                 # English & Simplified Chinese localization
│   ├── sanitizer.py            # High-speed two-layer engine, whole-word, AI hint, fuzzy restore
│   ├── rules.py                # 47 built-in detectors + Luhn/MyKad/GB 11643 validators + presets
│   ├── secure_io.py            # Atomic private writes (POSIX 0600 / Windows protected DACL)
│   └── startup.py              # 64-bit-safe Windows single-instance guard, POSIX flock & startup
├── tests/
│   ├── fixtures/rules_golden_cases.json  # Shared Python & Web golden test fixture
│   ├── test_v05_upgrades.py    # v0.3.2–v0.5.0 security, perf, crypto, CLI, GUI & extension tests
│   ├── test_web_security.cjs   # Web CSP, zero-storage, diff-boundary & golden-case Node tests
│   └── ...                     # Core, security boundary, GUI transition, Windows config/hotkey tests
├── web/
│   └── index.html              # CSP-locked 100% RAM-Only standalone Web Edition
├── config.example.json         # Safe template configuration file
├── requirements.txt            # Python dependencies
├── README.md                   # English documentation
└── README.zh-CN.md             # Simplified Chinese documentation
```

---

## 🔒 Security Commitment

1. **100% Local Execution**: Zero telemetry, zero analytics, zero outbound HTTP/Socket connections, and zero external LLM/API calls. The Web Edition additionally enforces `Content-Security-Policy: default-src 'none'; connect-src 'none'`.
2. **RAM Vault by Default + Optional AES-256-GCM Encryption**: Desktop mappings live strictly in process memory (with configurable 5–60 minute idle auto-wipe). When cross-process persistence is needed, use GUI encrypted export or CLI `--vault-file ... --encrypt --passphrase-env ...` (**Scrypt + AES-256-GCM**). Plaintext JSON remains supported for backward compatibility when `--encrypt` is omitted.
3. **Private File Creation**: Vault, config, and export writes use private staging files and atomic publication (POSIX `0600` / Windows protected current-user DACL with inheritance disabled) and fail closed on symlinks, junctions, hardlinks, or nonregular destinations.
4. **Clipboard History Privacy Guard**: When enabled, restoring or undoing secrets marks clipboard writes to bypass Windows `Win+V` Clipboard History and Cloud Clipboard sync (and macOS `ConcealedType`/`TransientType`).
5. **Size, Detection & Clipboard Limits**: Desktop, Web, and CLI enforce the `1,500,000`-character cap on both `sanitize()` and `restore()`, failing closed without emitting stale or partial output. Pattern matching cannot replace human review before sharing sensitive material.
6. **Intentional Restoration & Strict Import Validation**: Restoration runs only via explicit local action. Imported configs and vaults (plaintext or encrypted) undergo strict schema, integrity, and KDF cost validation; invalid or tampered files are rejected atomically without mutating active session state.

### Safe CLI Files & Encrypted Cross-Process Restoration

```powershell
python -m src.main --file input.log --output sanitized.log
# Replacing an existing output requires explicit --overwrite; input/output aliases are always rejected.
python -m src.main --file input.log --output sanitized.log --overwrite
# Recommended: protect cross-process mappings with Scrypt + AES-256-GCM
$env:APS_VAULT_PASS = "YourStrongPassphrase"
python -m src.main --file input.log --output sanitized.log --vault-file private-mapping.enc.json --encrypt --passphrase-env APS_VAULT_PASS
python -m src.main --restore-file reply.txt --output restored.txt --vault-file private-mapping.enc.json --passphrase-env APS_VAULT_PASS
```

Input, output, vault and configuration paths must be distinct, including aliases. Shell redirection can itself truncate an existing file before Python starts; prefer `--file`/`--output` when file preservation matters. Vault and output publication are separate file operations, not a multi-file transaction.

### Release inputs and provenance

CI and Windows releases install exact direct/transitive versions and upstream artifact SHA-256 hashes from `requirements-lock.txt` using `python -m pip install --require-hashes -r requirements-lock.txt`. `requirements-macos-lock.txt` extends these shared pins with hashed macOS build dependencies; `requirements.txt` keeps source-install compatibility ranges. To update, resolve deliberately in a clean Python 3.11 environment, include Windows-only dependencies, verify the hashes against PyPI, and run only the affected focused checks. Actions use full upstream commit SHAs; review the upstream change before updating each SHA/comment.

Only the tag-push release job receives `contents: write`; PR and test jobs use read access. Release builds include source commit/run metadata (`build-info.json`) and asset checksums (`SHA256SUMS`). These checksums detect changed downloads; they are not code signing or a guarantee of bit-identical builds across runner images. Check the recorded revision and checksum when comparing a downloaded release EXE with source.

---

## 📄 License

Released under the [MIT License](LICENSE).
