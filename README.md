<div align="center">

# 🛡️ AI Privacy Sanitizer `v0.3.0`

**100% Local In-Memory · Zero Network Requests · Visual GUI Control Center · Lossless Bidirectional Clipboard & CLI Sanitizer for LLMs**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20Web-059669.svg)](#)
[![Zero Network](https://img.shields.io/badge/Privacy-100%25%20Local%20RAM-10b981.svg)](#security-commitment)

[**English**](README.md) | [**简体中文**](README.zh-CN.md)

</div>

---

## 💡 Why AI Privacy Sanitizer?

When debugging production incidents, reviewing code, or analyzing server logs with cloud LLMs (**ChatGPT, Claude, DeepSeek, Gemini, Cursor**), pasting raw text directly from your terminal or IDE can easily leak:
- 🔑 **API Keys & Cloud Tokens** (`sk-...`, `sk_live_...`, `ghp_...`, `AKIA...`, `AIza...`, `xoxb-...`, `gsk_...`, `hf_...`, `npm_...`, `pypi-...`, `dop_v1_...`, `lin_api_...`, `sbp_...`, `PMAK-...`, `shpat_...`, Azure SAS `sig=...`, JWTs, Bearer tokens, Slack/Discord/Feishu/DingTalk/WeCom Webhook URLs)
- 🗄️ **Database & Auth Secrets** (`postgres://`, `mysql://`, `mongodb://`, `redis://`, ODBC connection strings, `.env` variables, `curl -u` credentials)
- 📜 **PEM / SSH Private Keys** (`-----BEGIN RSA/OPENSSH PRIVATE KEY-----`)
- 💻 **System File Path Usernames** (`C:\Users\<username>\...`, `/Users/<username>/...`, `/home/<username>/...` — masks only the personal OS username while preserving path structure)
- 🌐 **Internal Infrastructure** (Private IPv4 `10.x.x.x` / `192.168.x.x` / `172.16-31.x.x`, Public IPv4, IPv6, MAC addresses)
- 🪪 **Personal Identifiable Information (PII)** (Emails, International & Malaysian `+60` phone numbers, Malaysian MyKad NRIC with state PB-code validation, Mainland China 18-digit ID, Passports, Luhn-validated Bank Cards)
- 🏢 **Proprietary Business Entities** (Company names, Client names, Internal project codenames)

**AI Privacy Sanitizer** sits quietly in your system tray and sanitizes your clipboard in **under 2 milliseconds** via global hotkeys (`Alt+S` to sanitize, `Alt+R` to restore) or automatic **Cruise Mode (`Ctrl+C` auto-sanitization)** — keeping all original-to-placeholder mappings strictly in local volatile RAM (`SessionVault`).

---

## ✨ Key Features

### 1. 🖥️ Zero-Setup Visual GUI Control Center (`src/gui.py`)
- **🏠 Dashboard & Instant Toggles**: Monitor session interception stats and toggle **Auto-Sanitize on Copy (Cruise Mode)**, **Semantic Disguise Mode (`192.0.2.x` / `user1@example.com` / `dev_user_1`)**, **Windows Startup**, **Dark/Light Themes**, and **English/Chinese UI** with a single click. Includes **⏪ Undo Last Sanitize** (retains up to 5 recent raw clipboard snapshots in RAM).
- **⌨️ Custom Global Hotkey Recorder**: Easily rebind `Alt+S` / `Alt+R` to any key combination using presets or live keypress recording.
- **🧪 Live Interactive Sandbox**: Paste raw logs on the left and preview sanitized output with green highlighted placeholders and **per-category interception pills** (`API_KEY: 6 | DB_PASS: 5`) in real time on the right.
- **📚 Optional Custom Dictionary + Allowlist & Built-in Rule Toggles**:
  - Organize proprietary terms under `COMPANY`, `CLIENT`, `PROJECT`, and `CUSTOM_SECRET` with batch import/export and an **in-app JSON editor** (never forces open external IDEs).
  - Switch to the **🛡️ Allowlist & Built-in Rule Switches** panel to add safe strings that bypass sanitization or enable/disable individual built-in regex rules.
- **🔐 Live RAM Session Vault with Anti-Shoulder-Surfing Mask**: Inspect active `Placeholder <-> Original Value` mappings in memory. Defaults to **masked preview (`sk-pro***O678`)** during screen sharing/recording, with a one-click **👁️ Reveal/Mask Originals** toggle.

### 2. 🧠 Two-Layer Precision Sanitization Engine (`src/sanitizer.py` & `src/rules.py`)
- **Layer 1 — Custom Dictionary (Longest-Match-First)**: Matches custom company, client, and project names from longest to shortest (case-insensitive) so short aliases never truncate full legal names (e.g., `"Acme Global Technologies Sdn Bhd"` is matched before `"Acme Global"`).
- **Layer 2 — 35+ High-Precision Built-in Regex Detectors + Algorithmic Validators**:
  - **Algorithmic Checksum Validators**: Built-in `luhn_checksum_valid` prevents 16-digit timestamps/order numbers from false-matching as bank cards; `my_nric_valid` validates Malaysian birth dates and official State/Country PB codes.
  - **Structure-Preserving Masking**: Masks only the secret portion in database URIs, Basic Auth URLs, OS file paths, and key-value assignments (`postgres://dbadmin:[DB_PASS_1]@[PRIVATE_IP_1]:5432/prod`).
  - **English & Chinese Natural Key-Value Support**: Supports `password = "..."`, `pass = ...`, `pw = ...`, `id = ...`, `密码-123123`, `账号=asdasd`, `户口=...`.
  - **Two-Stage Exact + Fuzzy/Case-Insensitive Restore**: Even if an LLM alters `<API_KEY_1>` into `[API_KEY_1]`, `` `API_KEY_1` ``, `<api_key_1>`, `{API_KEY_1}`, or `&lt;API_KEY_1&gt;`, `restore()` accurately recovers the original secret.

### 3. 🌐 Semantic Disguise Mode (RFC 5737 & Synthetic Entities)
- When troubleshooting Nginx, firewall, or Kubernetes network configs, replacing IPs with `[PRIVATE_IP_1]` can cause LLMs to complain about invalid syntax.
- Enabling **Semantic Disguise Mode** replaces real private IPs (`10.52.18.9`) with RFC 5737 test IPs (`192.0.2.101`), public IPs with `203.0.113.101`, emails with `user1@example.com`, and OS path usernames with `dev_user_1` — while `Alt+R` still restores them back to real values with 100% accuracy.

### 4. 🛡️ Single-Instance Guard, Developer CLI Pipes & Zero-Storage Web Edition
- **Kernel-Level Single-Instance Protection (`src/startup.py`)**: Uses Windows Named Mutex & Events (zero network ports). Double-clicking the `.exe` when already running in the tray wakes up the existing Control Center window or hot-replaces the process if upgraded.
- **Developer Terminal CLI Pipeline (`src/main.py`)**: Pipe logs directly in terminal workflows via `--stdin`, `--restore-stdin`, `--file <in>`, and `--output <out>`.
- **Standalone RAM-Only Web Edition (`web/index.html`)**: A zero-dependency single HTML file running 100% in browser RAM (zero `localStorage`, zero cookies, zero network requests, 10-minute auto-wipe idle timer, **🔍 Highlighted Diff Preview with hover tooltips**, Vault secret masking, and RAM Allowlist).

---

## 🔄 3-Second Daily Workflow

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. Copy sensitive code/logs in your IDE or terminal (Ctrl + C)             │
│                                  │                                         │
│                                  ▼                                         │
│ 2. Press Alt + S (or auto via Cruise Mode) ──► Secrets masked in Clipboard │
│    e.g. postgres://admin:[DB_PASS_1]@192.0.2.101:5432/prod                 │
│                                  │                                         │
│                                  ▼                                         │
│ 3. Paste into ChatGPT / Claude / DeepSeek (Ctrl + V) & copy AI's reply     │
│                                  │                                         │
│                                  ▼                                         │
│ 4. Press Alt + R ──► Placeholders (even AI-mutated ones) 100% restored!    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Getting Started

### Option 1: Standalone Windows Executable (Recommended for Users)
1. Download or run **`AI-Privacy-Sanitizer.exe`**.
2. On first launch, the **Visual Control Center** opens automatically and places a blue shield-lock icon in your Windows system tray.
3. Closing the window (`X`) minimizes it safely to the system tray. Left-click the tray icon or double-click the `.exe` anytime to reopen the Control Center.

### Option 2: Run from Source / CLI Pipeline / Build `.exe` (For Developers)

```powershell
# 1. Create virtual environment and install dependencies
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Run unit tests and built-in self-test
pytest -v
python -m src.main --self-test

# 3. Developer CLI Pipeline usage (stdin / file sanitization)
Get-Content app.log | python -m src.main --stdin > app.sanitized.log
python -m src.main --file .env.production --output .env.sanitized

# 4. Launch the desktop app from source
python -m src.main

# 5. Export multi-resolution icon & package standalone .exe
python -m src.main --export-ico assets/icon.ico
pyinstaller --noconfirm AI-Privacy-Sanitizer.spec
```

### Option 3: Pure In-Memory Web Edition
Open [`web/index.html`](web/index.html) directly in any modern browser (or upload it as a single file to Hostinger / GitHub Pages / Cloudflare Pages). All sanitization and restoration run 100% inside JavaScript volatile variables.

---

## ⌨️ Hotkeys & System Tray Guide

| Action | Default Hotkey | System Tray Menu Item | Description |
| :--- | :--- | :--- | :--- |
| **Open Control Center** | Left-click Tray Icon | `🖥️ Open Control Center` | Manage custom words, Allowlist, rule switches, Sandbox, and Vault |
| **Sanitize Clipboard** | `Alt + S` | `1. Sanitize Clipboard` | Replace sensitive clipboard strings with safe placeholders + Toast summary |
| **Restore Clipboard** | `Alt + R` | `2. Restore Clipboard` | Recover original values from exact or AI-mutated placeholders |
| **Undo Last Sanitize** | Button in UI / Tray | `⏪ Undo Last Sanitize` | Restore the pre-sanitized raw clipboard content (up to 5 snapshots) |
| **Cruise Mode** | Toggle in UI / Tray | `⚡ Auto-Sanitize on Copy` | Automatically sanitize clipboard within 0.5s after pressing `Ctrl+C` |
| **Windows Startup** | Toggle in UI / Tray | `🚀 Launch at Startup` | Start silently in the system tray when logging into Windows |
| **Clear Session Vault** | Button in UI / Tray | `4. Clear Session Map` | Immediately wipe all in-memory placeholder mappings and undo snapshots |
| **Exit Application** | Button in UI / Tray | `5. Exit` | Unhook global hotkeys and terminate the tray process cleanly |

---

## 📂 Project Structure

```text
ai-privacy-sanitizer/
├── .github/workflows/
│   └── ci-build.yml         # Automated multi-OS pytest & Windows EXE release workflow
├── src/
│   ├── __init__.py          # Package version metadata (v0.3.0)
│   ├── main.py              # System tray controller, hotkeys, undo stack, CLI pipes
│   ├── gui.py               # CustomTkinter Dark/Light bilingual GUI Control Center
│   ├── i18n.py              # English & Simplified Chinese localization strings
│   ├── sanitizer.py         # Two-layer engine, Allowlist, fuzzy restore & SessionVault
│   ├── rules.py             # 35+ compiled regex detectors + Luhn & MyKad NRIC validators
│   └── startup.py           # Windows HKCU Run startup & kernel-level SingleInstanceGuard
├── tests/
│   └── test_sanitizer.py    # 18 comprehensive unit tests (core, GUI, CLI, Web integrity)
├── web/
│   └── index.html           # 100% RAM-Only standalone Web Edition (zero storage/network)
├── config.example.json      # Safe template configuration file
├── requirements.txt         # Python dependencies
├── README.md                # English documentation
└── README.zh-CN.md          # Simplified Chinese documentation
```

---

## 🔒 Security Commitment

1. **100% Local Execution**: Zero telemetry, zero analytics, zero outbound HTTP/Socket connections, and zero external LLM/API calls.
2. **Zero Disk Residue for Secrets**: Every `Placeholder <-> Original Secret` mapping in `SessionVault` resides strictly in process RAM and is permanently destroyed when you clear the vault or exit the app.
3. **Git Leak Protection**: Local `config.json`, `*.local.json`, and `*secret*` files are strictly excluded via `.gitignore` so your proprietary company or client dictionary is never accidentally committed.

---

## 📄 License

Released under the [MIT License](LICENSE).
