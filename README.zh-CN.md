<div align="center">

# 🛡️ AI Privacy Sanitizer (AI 隐私脱敏卫士) `v0.6.0`

**纯本地运行 · 默认内存保险箱 · 零外部网络请求 · 原生事件巡航 · 自定义正则规则 · 文件夹拖拽批处理 · 零权限浏览器扩展 · CLI 泄密守门**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20Preview%20%7C%20Linux%20%7C%20Web%20%7C%20MV3%20Ext-059669.svg)](#)
[![Zero Network](https://img.shields.io/badge/Privacy-Local%20Processing-10b981.svg)](#安全承诺-security-commitment)

[**English**](README.md) | [**简体中文**](README.zh-CN.md)

</div>

---

## 💡 为什么需要 AI Privacy Sanitizer？

在使用 **ChatGPT、Claude、Gemini、Perplexity、Grok、Microsoft Copilot、GitHub Copilot、DeepSeek** 等大模型排查生产故障、分析日志或重构代码时，直接复制粘贴极易泄露高危机密：
- 🔑 **API 密钥与国际云凭证** (`sk-...`、`sk_live_...`、`whsec_...`、`ghp_...`、`AKIA...`、`AIza...`、`cfut_...` / Cloudflare Origin CA、`sbp_...` / `sb_secret_...`、`vercel_pat_...`、`lin_api_...`、`dapi...`、`123456789:AA...` Telegram Bot、Azure SAS `sig=...` 与 `AccountKey=`/`SharedAccessKey=` 连接串、JWT、Bearer Token、`Authorization: Basic ...`、Slack/Discord Webhook)
- 🗄️ **结构化配置与数据库连接串** (`.env`、JSON、YAML、URL Query 参数如 `SUPABASE_SERVICE_ROLE_KEY`、`signing_secret`、`x-api-key`、`postgres://`/`redis://` 含 `@` 密码、`curl -u` 凭证，以及可选的**高信息熵随机密钥兜底检测**)
- 📜 **多行私钥证书块** (`-----BEGIN RSA/OPENSSH PRIVATE KEY-----` 与 `-----BEGIN PGP PRIVATE KEY BLOCK-----`)
- 💻 **本机文件路径用户名** (`C:\Users\<username>`、`/Users/<username>`、`/home/<username>`，兼容无尾部斜杠与 Unicode 用户名)
- 🌐 **内网与网络基础设施** (内网 IPv4、公网 IPv4 含 `.0` 网段、压缩格式 IPv6、MAC 地址)
- 🪪 **个人隐私信息 (PII)** (邮箱、国际 E.164 及各国手机号、带校验的身份证件/护照号、Luhn 校验银行卡号)
- 🏢 **商业机密实体与自定义正则规则** (公司名、客户名、项目代号，以及支持 `(?P<secret>...)` 局部捕获组和 ReDoS 防卡死校验的自定义正则)

---

## ✨ `v0.6.0` 核心升级特性

1. **⌨️ 全局热键注册状态可视化 + 冲突一键顺延修复**
   - 侧边栏状态区、首页与设置页实时显示系统级热键绑定状态（`热键已就绪` vs `冲突: [KEY]`）。
   - 当检测到快捷键被显卡 Overlay 等软件抢占时，点击 **🔧 一键自动顺延修复** 自动寻找并绑定可用组合键，同步更新配置与托盘提示。
2. **🧩 用户自定义正则规则（词库与规则 → 自定义正则）**
   - 支持自定义规则名、分类名、占位符模板（`[{category}_{index}]`、`<{category}_{index}>`、`{{{category}_{index}}}`）及可选 `(?P<secret>...)` 局部脱敏。
   - 内置实时测试预览框、语法报错提示、静态 ReDoS AST 防护（拦截嵌套量词/危险回溯）与运行超时保护，完全兼容配置导入导出及 CLI。
3. **📥 单文件 / 多文件 / 文件夹拖拽脱敏与还原**
   - Windows 端使用零额外依赖的原生 Win32 `WM_DROPFILES` 实现，将 `.env`、`.log`、`.json`、`.yaml`、`.csv`、`.txt` 或整个日志文件夹直接拖入窗口即可批处理（也可点击 **📁 批量目录**）。
   - 自动保留相对目录结构输出至安全副本（绝不覆盖原文件），且同批次共享同一 `SessionVault`，确保跨文件相同 IP/密钥生成一致占位符。
4. **🔎 首页“最近一次剪贴板脱敏快览” + 误伤一键放行**
   - 在首页卡片实时展示最近一次 `Alt+S` 或巡航模式脱敏的命中摘要（默认防窥遮罩，支持显隐切换）。
   - 发现误判时直接点击 **🏳️ 加入白名单并重跑**，自动加入白名单并无感更新当前剪贴板为修正后的脱敏文本。
5. **🧬 结构化配置感知 + 高信息熵兜底 + 国际云/开发平台规则**
   - 增强 `.env`/JSON/YAML/URL Query 键值感知；新增可开关的“高信息熵随机密钥兜底检测”（仅作用于赋值右侧，避开普通英文与 UUID）；补齐 Cloudflare、Supabase、Vercel、Linear、Stripe Webhook、Azure 连接串、Databricks、Telegram 等规则。
6. **⚡ Windows 原生剪贴板事件监听升级巡航模式**
   - Windows 平台使用 `AddClipboardFormatListener` (`WM_CLIPBOARDUPDATE`) 替代纯轮询，复制瞬间毫秒级响应且平时零后台轮询；非 Windows 平台优雅回退 `0.55s` 轮询，兼容防死循环写回、`Win+V` 隐私标记与闲置焚毁。
7. **🧩 浏览器扩展（Paste Guard）全面进化 + 三端同源校验**
   - 保持 `permissions: []` 零联网零落盘；新增 Perplexity、Grok、Microsoft Copilot、GitHub Copilot、Google AI Studio、Mistral Le Chat。
   - 升级 ProseMirror/Lexical 现代富文本输入粘贴兼容性；新增网页端 Shadow DOM 悬浮 **🔄 一键还原复制** 按钮与中英双语自适应；`scripts/sync_web_rules.py --check` 纳入 Python + Web + Extension 三端强校验。
8. **🔍 CLI 只读安全扫描守门模式（`--scan` / `--git-staged`）**
   - 终端支持 `python -m src.main --scan <文件或目录>` 与 `--git-staged`（扫描暂存区），仅输出文件路径、行号、类别与掩码摘要（绝不打印完整明文密钥），命中时返回非 0 退出码，可直接接入 Git `pre-commit` 或 CI。
9. **🚀 Windows 免拦截便携启动器与分发增强**
   - 提供免编译官方 Python 无黑框启动器 **`run-sanitizer.vbs`** 与 **`run-sanitizer.bat`**（解决 Windows 11 Smart App Control 拦截），提供 `packaging/` 下 Scoop / Winget 清单模板，并在 `.github/workflows/ci-build.yml` 预留可选代码签名步骤。

---

## 🔄 3 秒极简日常工作流

```mermaid
flowchart TD
    A["① 复制代码或日志 (Ctrl + C)"] --> B["② 按 Alt + S（或原生事件巡航 / 浏览器粘贴拦截）──► 机密替换为安全占位符"]
    B --> C["③ 在首页快览确认无误伤（可一键加白名单重跑）后粘贴给 AI"]
    C --> D["④ 复制 AI 回复按 Alt + R（或网页内点击一键还原复制）──► 本机无损还原！"]
```

---

## 🚀 快速开始

### 方式一：独立 Windows `.exe` 或免拦截便携脚本 `run-sanitizer.vbs`
1. 前往 [GitHub Releases](https://github.com/HsooiDev/ai-privacy-sanitizer/releases) 下载 `Sanitizer.exe` 与 `SHA256SUMS`，用 `Get-FileHash .\Sanitizer.exe -Algorithm SHA256` 校验后双击启动。
2. **若 Windows 11 智能应用控制（Smart App Control）阻止未签名 `.exe`**：无需关闭系统安全策略！安装官方 Python 3.11+（`pip install -r requirements.txt`）后，直接双击仓库根目录的 **`run-sanitizer.vbs`**（无黑框静默拉起 GUI 与托盘）或 **`run-sanitizer.bat`** 即可零拦截运行。
3. Windows `.exe` 私有配置存储于 `%LOCALAPPDATA%\Sanitizer\config.json`。

### 方式二：源码运行 / CLI 扫描守门 / 本地打包

```powershell
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 运行全量测试、Web 安全测试与三端规则同源校验
python -m pytest --ignore=work -v
node tests/test_web_security.cjs
python scripts/sync_web_rules.py --check
python -m src.main --self-test

# 3. CLI 只读安全扫描守门（适合 Git pre-commit 或 CI）
python -m src.main --scan ./src
python -m src.main --git-staged
python -m src.main --scan .env.example --entropy --json

# 4. 启动桌面控制中心
python -m src.main

# 5. 打包独立 .exe（若本机开启 Smart App Control，请勿在终端直接执行未签名的 dist\Sanitizer.exe）
python -m src.main --export-ico assets/icon.ico
python -m PyInstaller --noconfirm AI-Privacy-Sanitizer.spec
```

### 方式三：Web 纯内存版（`web/index.html`）
浏览器直接打开 [`web/index.html`](web/index.html)，强制启用 `Content-Security-Policy: default-src 'none'; connect-src 'none'; form-action 'none'`，关闭即焚。

### 方式四：零权限浏览器粘贴卫士（`browser-extension/`）
打开 `chrome://extensions/` → 开启「开发者模式」→「加载已解压的扩展程序」→ 选择 [`browser-extension/`](browser-extension/)（详阅 [`browser-extension/README.md`](browser-extension/README.md)）。

### 方式五：实验性 macOS `.app` / `.dmg`
可在 GitHub Actions 运行 **Experimental macOS Build**，或本机运行 `python scripts/build_macos.py --arch arm64`。

---

## 🔒 安全承诺 (Security Commitment)

1. **100% 纯本地离线**：零遥测、零外发 HTTP/Socket 请求。
2. **默认内存保险箱 + AES-256-GCM**：映射仅驻留 RAM，支持 5–60 分钟闲置自动清空及 Scrypt + AES-256-GCM 加密迁移。
3. **私有权限原子写盘**：配置、保险箱与批量副本均通过 POSIX `0600` / Windows 受保护 DACL 原子落盘，拒绝软链接与 junction。
4. **剪贴板历史隐私保护**：还原/撤销写回敏感原文时附加 Windows `Win+V` 与云剪贴板排除标记。
5. **只读扫描绝不吐明文**：`--scan` 与 `--git-staged` 只读检测且严格脱敏输出摘要。

---

## 💡 常见使用疑问与贴士

- **为什么“加入白名单”后带 `token=` / `password=` 的那行还是会被脱敏？**
  白名单最适合放行被误判的公司名、普通词、测试域名或内网 IP；如果前面自带 `token=`、`password=` 等明显机密前缀，或夹着很像手机号的连续数字，系统出于安全底线仍会按规则拦截。需要完全放行这类格式时，可到「词库与规则 → 白名单与规则」里关闭对应的单项规则开关。
- **文件/文件夹拖入后原文件会被改写吗？**
  绝不会。会在原路径旁自动生成安全副本（如 `xxx.sanitized.log` 或 `文件夹名_sanitized/`），点击窗口里的“📂 打开输出目录”即可直接定位；同一批文件共享映射，方便让 AI 跨文件联动分析。
- **中途需要关机或重启怎么办？**
  映射表默认仅存在内存中，退出或超时即清空；如需跨重启继续还原 AI 回复，先在「实时内存保险箱」点“🔐 加密导出”，下次打开软件后再“🔓 加密导入”。
- **开着巡航模式点 `Alt+R` 还原会马上又被脱敏回去吗？**
  不会。软件会自动识别自己写回的还原/撤销结果并附上防 `Win+V` 标记，直到你下次在别处手动复制新文本才会继续触发巡航。

---

## 📄 开源协议 (License)

基于 [MIT License](LICENSE) 开源。
