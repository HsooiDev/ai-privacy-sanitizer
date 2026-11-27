<div align="center">

# 🛡️ AI Privacy Sanitizer `v0.6.0`

**Local Processing · RAM Vault by Default · Zero Network Requests · Native Event Cruise · Custom Regex Guard · Batch Folder Drop · Zero-Permission Browser Extension · CLI Leak Scanner**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20Preview%20%7C%20Linux%20%7C%20Web%20%7C%20MV3%20Ext-059669.svg)](#)
[![Zero Network](https://img.shields.io/badge/Privacy-Local%20Processing-10b981.svg)](#security-commitment)

[**English**](README.md) | [**简体中文**](README.zh-CN.md)

</div>

---

## 💡 Why AI Privacy Sanitizer?

When debugging production incidents, reviewing configs, or analyzing server logs with cloud LLMs (**ChatGPT, Claude, Gemini, Perplexity, Grok, Microsoft Copilot, GitHub Copilot, DeepSeek**), pasting raw text directly can leak:
- 🔑 **API Keys & Cloud Platform Tokens** (`sk-...`, `sk_live_...`, `whsec_...`, `ghp_...`, `AKIA...`, `AIza...`, `cfut_...` / Cloudflare Origin CA, `sbp_...` / `sb_secret_...`, `vercel_pat_...`, `lin_api_...`, `dapi...`, `123456789:AA...` Telegram Bot, Azure SAS `sig=...` & `AccountKey=`/`SharedAccessKey=` Connection Strings, JWTs, Bearer tokens, `Authorization: Basic ...`, Slack/Discord Webhooks)
- 🗄️ **Structured Configs & Database Secrets** (`.env`, JSON, YAML, URL query keys like `SUPABASE_SERVICE_ROLE_KEY`, `signing_secret`, `x-api-key`, `postgres://` / `redis://` passwords containing `@`, `curl -u` credentials, plus optional **High Shannon Entropy** fallback for opaque RHS tokens)
- 📜 **Multi-Line Private Keys** (`-----BEGIN RSA/OPENSSH PRIVATE KEY-----` & `-----BEGIN PGP PRIVATE KEY BLOCK-----`)
- 💻 **OS File Path Usernames** (`C:\Users\<username>`, `/Users/<username>`, `/home/<username>` — handles trailing-slash-free and Unicode usernames)
- 🌐 **Internal Infrastructure** (Private IPv4, Public IPv4 including `.0` last octets, compressed IPv6, MAC addresses)
- 🪪 **Personal Identifiable Information (PII)** (Emails, International `+1`/`+44`/`+60`/`+65`/E.164 phone numbers, National IDs & Passports with checksum/regional validation, Luhn-validated Visa / Mastercard / Amex / UnionPay cards)
- 🏢 **Proprietary Business Entities & Custom Regex Rules** (Company names, clients, projects, plus user-defined regexes with `(?P<secret>...)` partial capture groups and ReDoS safety protection)

---

## ✨ What's New in `v0.6.0`

1. **⌨️ Global Hotkey Status Visibility + One-Click Conflict Auto-Fix**
   - Sidebar, Dashboard, and Settings display live OS hotkey registration status (`Hotkeys Ready` vs `Conflict: [KEY]`).
   - When an app (such as a GPU overlay) steals a shortcut, click **🔧 Auto-Fix Conflict** to automatically locate and bind an available fallback chord and sync your config & tray tooltip.
2. **🧩 User-Defined Custom Regex Rules (`Words & Rules → Custom Regex`)**
   - Add custom rules with rule name, category, placeholder template (`[{category}_{index}]`, `<{category}_{index}>`, `{{{category}_{index}}}`), and optional `(?P<secret>...)` partial masking.
   - Includes a live test box with syntax errors, static ReDoS AST analysis (blocks nested quantifiers / catastrophic backtracking), and runtime timeout protection.
3. **📥 Single / Multi-File / Folder Drag-and-Drop Batch Processing**
   - Drag and drop `.env`, `.log`, `.json`, `.yaml`, `.csv`, `.txt`, or entire log folders directly onto the Windows app window (powered by zero-dependency native Win32 `WM_DROPFILES`), or click **📁 Batch Folder**.
   - Preserves relative subdirectory structure in a brand-new output folder (never overwrites originals) and shares one `SessionVault` across the entire batch so identical IPs/keys map consistently across files.
4. **🔎 Dashboard Recent Clipboard Diff Quick-View + One-Click Allowlist & Rerun**
   - Displays the latest `Alt+S` or Cruise Mode sanitization hits right on the Dashboard (masked by default with Reveal toggle).
   - Click **🏳️ Allowlist & Rerun** on any false-positive hit to add it to your allowlist and silently update your clipboard with the corrected output.
5. **🧬 Structured Config Awareness + High-Entropy Fallback + Cloud Rules**
   - Enhanced `.env`/JSON/YAML/URL query awareness, opt-in Shannon entropy fallback detector (assignment RHS only), and rules for Cloudflare, Supabase, Vercel, Linear, Stripe Webhooks, Azure Connection Strings, Databricks, and Telegram.
6. **⚡ Windows Native Clipboard Event Cruise Mode**
   - Uses Win32 `AddClipboardFormatListener` (`WM_CLIPBOARDUPDATE`) on Windows for instant zero-polling sanitization on copy (with graceful `0.55s` polling fallback on non-Windows), fully compatible with `Win+V` privacy markers and idle auto-wipe.
7. **🧩 Browser Extension Evolution + 3-Way Parity CI**
   - Keeps `permissions: []`, adds Perplexity, Grok, Microsoft Copilot, GitHub Copilot, Google AI Studio, and Mistral Le Chat, upgrades rich-text editor pasting (ProseMirror / Lexical), adds bilingual EN/ZH UI, and adds an in-page Shadow DOM **🔄 Restore & Copy** floating pill.
   - `scripts/sync_web_rules.py --check` verifies Python, Web, and Browser Extension identically in CI.
8. **🔍 Read-Only CLI Secret Scanner (`--scan` / `--git-staged`)**
   - Run `python -m src.main --scan <file_or_dir>` or `python -m src.main --git-staged` (ideal for Git `pre-commit` hooks or CI). Prints strictly masked excerpts with file/line/category and exits non-zero (`1`) on leaks without ever printing plaintext secrets.
9. **🚀 Windows Smart App Control Friendly Launchers & Packaging**
   - Includes zero-console `run-sanitizer.vbs` and `run-sanitizer.bat` launchers using official Python (`pythonw.exe`), Scoop/Winget manifest templates under `packaging/`, and optional Authenticode signing support in `.github/workflows/ci-build.yml`.

---

## 🔄 3-Second Daily Workflow

```mermaid
flowchart TD
    A["1. Copy code/logs (Ctrl + C)"] --> B["2. Press Alt + S (or Native Event Cruise / Browser Paste Guard) ──► Secrets masked"]
    B --> C["3. Inspect hits on Dashboard Quick-View (Allowlist & Rerun if needed) & paste to AI"]
    C --> D["4. Copy AI reply & press Alt + R (or click in-page Restore & Copy) ──► 100% restored locally!"]
```

---

## 🚀 Getting Started

### Option 1: Standalone Windows `.exe` or Unblocked `run-sanitizer.vbs`
1. Download `Sanitizer.exe`, `SHA256SUMS`, and `build-info.json` from [GitHub Releases](https://github.com/HsooiDev/ai-privacy-sanitizer/releases), verify with `Get-FileHash .\Sanitizer.exe -Algorithm SHA256`, and double-click to launch.
2. **If Windows 11 Smart App Control blocks unsigned `.exe` binaries**: You do **not** need to disable Windows security. Clone or extract the repo, install official Python 3.11+ (`pip install -r requirements.txt`), and double-click **`run-sanitizer.vbs`** (zero console window) or **`run-sanitizer.bat`**.
3. Windows `.exe` settings live privately at `%LOCALAPPDATA%\Sanitizer\config.json`.

### Option 2: Run from Source / CLI Leak Gate / Build `.exe`

```powershell
# 1. Create virtual environment and install dependencies
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Verify tests, Web security, and 3-way Python/Web/Extension parity
python -m pytest --ignore=work -v
node tests/test_web_security.cjs
python scripts/sync_web_rules.py --check
python -m src.main --self-test

# 3. Read-only secret scanner (safe for CI & Git pre-commit hooks)
python -m src.main --scan ./src
python -m src.main --git-staged
python -m src.main --scan .env.example --entropy --json

# 4. Launch Desktop GUI & Tray App
python -m src.main

# 5. Package standalone Windows .exe (do not execute unsigned dist\Sanitizer.exe under Smart App Control)
python -m src.main --export-ico assets/icon.ico
python -m PyInstaller --noconfirm AI-Privacy-Sanitizer.spec
```

### Option 3: Pure In-Memory Web Edition (`web/index.html`)
Open [`web/index.html`](web/index.html) directly in any browser. Enforces `Content-Security-Policy: default-src 'none'; connect-src 'none'; form-action 'none'` with zero `localStorage`.

### Option 4: Zero-Permission Browser Paste Guard (`browser-extension/`)
Open `chrome://extensions/` → enable **Developer mode** → **Load unpacked** → select [`browser-extension/`](browser-extension/) (see [`browser-extension/README.md`](browser-extension/README.md)).

### Option 5: Experimental macOS `.app` / `.dmg`
Run **Actions → Experimental macOS Build** or build locally with `python scripts/build_macos.py --arch arm64`.

---

## 🔒 Security Commitment

1. **100% Local Execution**: Zero telemetry, zero analytics, zero outbound HTTP/Socket calls.
2. **RAM Vault by Default + Scrypt & AES-256-GCM**: Session mappings stay in process RAM with 5–60 min idle auto-wipe and optional AES-256-GCM passphrase encryption.
3. **Private Atomic File Writes**: Config, vault, and batch outputs use POSIX `0600` / Windows protected current-user DACLs and reject symlinks, junctions, and hardlinks.
4. **Clipboard History Privacy Guard**: Marks restored/undone secrets to bypass Windows `Win+V` / Cloud Clipboard and macOS `ConcealedType`/`TransientType`.
5. **Read-Only Scanner Guarantee**: `--scan` and `--git-staged` never write mappings or echo plaintext secrets to terminal output.

---

## 💡 Everyday Tips & FAQ

- **Allowlisted item still masked after `token=` / `password=`**: Allowlist safely skips standalone terms (company names, test domains, IPs). When text explicitly has a sensitive key prefix (`token=...`, `password=...`) or a phone-like digit sequence inside it, structured/digit rules still protect it by design—toggle individual built-in rules in **Allowlist & Built-in Rules** if needed.
- **Originals are never overwritten on Drag & Drop**: Safe copies (`*.sanitized.*` or `<folder>_sanitized/`) are saved beside your originals with a one-click **Open Output** button, sharing one session vault across the whole batch.
- **Need to reboot mid-conversation?**: Use **Encrypted Export / Import** in **Live Vault** before closing the app; otherwise the RAM vault wipes automatically on exit or idle timeout.
- **Cruise Mode + Restore (`Alt+R`)**: Restoring or undoing inside the app never gets re-sanitized automatically; Cruise Mode waits for your next manual copy.

---

## 📄 License

Released under the [MIT License](LICENSE).
