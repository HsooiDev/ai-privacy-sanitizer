<div align="center">

# 🛡️ AI Privacy Sanitizer (AI 隐私脱敏卫士) `v0.5.0`

**本地处理 · 默认内存映射 · 零外部网络请求 · 侧边栏可视化控制中心 · AES-256-GCM 加密导出 · 零权限浏览器扩展 · 双向无损还原系统**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20Preview%20%7C%20Linux%20%7C%20Web%20%7C%20MV3%20Ext-059669.svg)](#)
[![Zero Network](https://img.shields.io/badge/Privacy-Local%20Processing-10b981.svg)](#安全承诺-security-commitment)

[**English**](README.md) | [**简体中文**](README.zh-CN.md)

</div>

---

## 💡 为什么需要 AI Privacy Sanitizer？

在日常使用 **ChatGPT、Claude、DeepSeek、Gemini、Cursor** 等大模型排查生产故障、分析日志或重构代码时，直接从终端或 IDE 复制粘贴极易泄露高危机密：
- 🔑 **API 密钥与云凭证** (`sk-...`, `sk_live_...`, `ghp_...`, `AKIA...`, `AIza...`, `xoxb-...`, `gsk_...`, `hf_...`, `npm_...`, `pypi-...`, `dop_v1_...`, `lin_api_...`, `sbp_...`, `PMAK-...`, `shpat_...`, Azure SAS `sig=...`, JWT, Bearer Token, `Authorization: Basic ...`, 飞书/钉钉/企微/Slack/Discord Webhook)
- 🗄️ **数据库连接串与密码** (`postgres://`, `mysql://`, `mongodb://`, `redis://` 完整支持密码内含 `@` 字符, ODBC 连接串, `.env` 环境变量, `curl -u` 账号密码)
- 📜 **多行私钥证书块** (`-----BEGIN RSA/OPENSSH PRIVATE KEY-----` 及 `-----BEGIN PGP PRIVATE KEY BLOCK-----`)
- 💻 **本地文件路径中的真实系统用户名** (`C:\Users\<username>`、`/Users/<username>`、`/home/<username>`，兼容无尾部斜杠及中文/Unicode 用户名)
- 🌐 **内网与网络基础设施** (内网 IPv4、公网 IPv4 含 `.0` 末段、压缩格式 IPv6 如 `2001:db8::8a2e:370:7334`、MAC 地址)
- 🪪 **个人身份与隐私信息 (PII)** (电子邮箱、马来西亚 `+60`/`01x` 及中国大陆/国际手机号、带州属代码校验的大马 MyKad NRIC、带 GB 11643-1999 校验位与真实闰年日历校验的中国 18 位身份证、护照号、带 Luhn 校验的 Visa/Mastercard 2xxx/Amex 15位/银联 19位银行卡号)
- 🏢 **商业机密实体** (公司全称/简称 `Sdn Bhd`、客户名称、内部项目代号，默认开启英文整词边界防止 `art` 误伤 `Start`)

**AI Privacy Sanitizer** 常驻于系统托盘，无需复杂配置，通过全局快捷键一键完成**剪贴板双层脱敏 (`Alt+S`)**、**复制即自动脱敏（巡航模式）**与 **AI 回复占位符容错还原 (`Alt+R`)**。默认会话映射仅驻留本地内存（RAM），并支持闲置自动清空、Windows `Win+V` 剪贴板历史防落盘保护，以及可选的 **Scrypt + AES-256-GCM 本地口令加密导出**。

---

## ✨ 核心特性 (`v0.5.0` 全新升级)

### 1. 🖥️ 侧边栏可视化控制中心 (`src/gui.py` & `src/hud.py`)
- **🧭 侧边栏 6 页专业导航**：左侧固定侧边栏（首页总览 / 实时沙盒 / 词典与规则 / 内存保险箱 / 安全与快捷键 / 使用指南），实时展示防护状态、巡航快捷开关、闲置自动清理倒计时与深浅色/中英原地无缝切换。
- **🏠 首页总览与本地文件脱敏/还原**：动态 KPI 仪表盘（拦截次数 / 活跃映射 / 已启用规则 `active/total`），支持一键操作 **📄 本地文件脱敏 / 还原**（`.env` / `.log` / `.json` / `.yaml` / `.csv` 原子私有落盘），内置 **⏪ 撤销脱敏 (Undo)** 与 **🤖 AI 防变形提示词注入**（还原时自动无损剥离）。
- **🧪 独立隔离沙盒 + 五级风险着色 + 右键秒加白名单**：沙盒默认使用独立临时保险箱避免污染主剪贴板映射（可一键同步至全局保险箱）；按 5 级风险语义高亮（红=密钥、琥珀=数据库/密码、蓝=网络/路径、紫=个人 PII、绿=商业机密）；**右键点击任意占位符即可将对应原值一键加入白名单并刷新预览**。
- **📚 专属词典 + 场景化规则预设 (`开发调试` / `人事与法务` / `严格全量`)**：支持中文友好规则名称、示例与实时搜索过滤；支持英文整词边界开关与仅导入词典（保留本机语言/主题/快捷键）；内置带格式化与行列语法错误定位的应用内 JSON 编辑器。
- **🔐 内存映射保险箱 + AES-256-GCM 加密导出 (`src/vault_crypto.py`)**：支持防抖搜索、分页渲染（60 行/页防大数据卡顿）、单条复制占位符/删除、防窥屏遮罩（默认打星号），以及 **Scrypt + AES-256-GCM** 口令加密导入/导出。
- **🛡️ 系统级安全防护 (`src/clipboard_privacy.py` & `src/hud.py`)**：
  - **动态托盘状态图标**（蓝盾就绪 / 翠绿巡航中 / 琥珀活跃映射）与支持多屏/高 DPI 自动定位的无焦点**微浮窗反馈 (Micro-HUD)**。
  - **Windows `Win+V` / 云剪贴板隐私保护**：还原/撤销写回敏感原文时自动附加 `ExcludeClipboardContentFromMonitorProcessing`、`CanIncludeInClipboardHistory=0`、`CanUploadToCloudClipboard=0`（macOS 使用 `ConcealedType`/`TransientType`）。
  - **桌面端闲置自动焚毁**：支持设置 5/10/15/30/60 分钟无操作自动清空内存映射与撤销栈。
  - **IDE 风格即时生效快捷键录制**：点击快捷键盒直接按键录制，或点击 `✏️` 手动输入后按 `Enter` / 点击绿色 `✓` 即时保存并注册全局热键；按 `Esc` 取消，禁止绑定无修饰单键，遇到系统/显卡快捷键冲突自动精准提示。

### 2. 🧠 高性能双层脱敏与容错还原引擎 (`src/sanitizer.py` & `src/rules.py`)
- **47 项内置高强度规则 + C 级预筛加速**：零回溯边界匹配 + `fast_tokens` 预筛选 + 延迟哨兵索引缓存，500KB 混合日志处理仅约 0.7 秒，500KB 未闭合私钥块 0.22 秒内免疫 ReDoS。
- **全类别语义伪装模式 (RFC 5737 & 语义实体)**：开启后真实内网 IP 伪装为 `192.0.2.101`，公网 IP 伪装为 `203.0.113.101`，邮箱伪装为 `user1@example.com`，路径用户名伪装为 `dev_user_1`，避免 AI 报格式语法错误且可逆向还原。
- **两阶段容错逆向还原**：即使大模型将 `<API_KEY_1>` 改写为 `[API_KEY_1]`、`` `API_KEY_1` ``、`<api_key_1>`、`{API_KEY_1}` 或 `&lt;API_KEY_1&gt;`，`restore()` 均能精准还原；并对还原输入同样执行 `1,500,000` 字符上限保护。

### 3. 🌐 CSP 锁定 Web 纯内存版 + 🧩 零权限浏览器扩展 + ⌨️ 增强 CLI 管道
- **100% 纯内存 Web 版 (`web/index.html`)**：内置浏览器级严格 CSP (`default-src 'none'; connect-src 'none'; form-action 'none'`)，规则与桌面端 100% 同源对齐（CI 自动通过 `scripts/sync_web_rules.py --check` 校验）；支持 250ms 防抖、5 级风险高亮差异预览、**点击差异芯片秒加白名单**、本地文件拖入与导出、闲置进度条与恢复默认安全白名单。
- **零权限 Chromium MV3 粘贴卫士扩展 (`browser-extension/`)**：`manifest.json` 声明 `permissions: []`、零外联、零持久化存储；在 ChatGPT / Claude / Gemini / DeepSeek / Poe 页面粘贴 (`Ctrl+V`) 时实时拦截检测并弹窗提供「🛡️ 一键脱敏后粘贴 / 仍粘贴原文 / 取消」。
- **开发者终端 CLI 管道模式 (`src/main.py`)**：支持 `--stdin`、`--restore-stdin`、`--file`、`--restore-file`、`--output`、`--encoding`、`--vault-file`、`--encrypt`、`--passphrase-stdin`、`--passphrase-env`。

---

## 🔄 3 秒极简日常工作流

```mermaid
flowchart TD
    A["① 复制代码或日志 (Ctrl + C)"] --> B["② 按 Alt + S（或巡航模式 / 浏览器扩展粘贴拦截）──► 机密替换为安全占位符<br/>例如：postgres://admin:[DB_PASS_1]@192.0.2.101:5432/prod"]
    B --> C["③ 粘贴给 ChatGPT / Claude / Gemini / DeepSeek 提问并复制 AI 回复"]
    C --> D["④ 按 Alt + R ──► AI 回复中的所有占位符（含变形占位符）100% 无损恢复为真实数据！"]
```

---

## 🚀 快速开始

### 方式一：直接下载并打开独立 `.exe`（Windows 用户推荐）
1. **下载与校验**：前往 [GitHub Releases](https://github.com/HsooiDev/ai-privacy-sanitizer/releases) 下载对应版本的 `Sanitizer.exe`、`SHA256SUMS` 和 `build-info.json`，建议放到本地固定文件夹（如 `D:\Tools\Sanitizer\Sanitizer.exe`，尽量避开 OneDrive 等云盘同步目录）。运行前可在 PowerShell 核对哈希：
   ```powershell
   Get-FileHash .\Sanitizer.exe -Algorithm SHA256
   ```
2. **首次双击启动**：在资源管理器中**直接双击** `Sanitizer.exe` 即可打开。首次启动会自动弹出**侧边栏可视化控制中心**，并在右下角系统托盘生成盾牌图标（点击窗口右上角 `×` 默认**最小化到托盘继续保护**，若需彻底退出请右键托盘菜单选择 **退出程序**；若默认 `Alt+R` 被显卡面板占用，首次启动会自动顺延为可用默认键 `Ctrl+Shift+R`）。
3. **如果遇到 Windows 安全拦截怎么办**：
   - **情况 A：Windows Defender SmartScreen（“Windows 已保护你的电脑”）**
     由于独立开源软件尚未购买商业 EV 代码签名证书，首次运行可能弹出蓝框提示。请点击文字链接 **`更多信息` (More info)** → 点击下方 **`仍要运行` (Run anyway)** 即可正常打开。
   - **情况 B：Windows 11 智能应用控制 / 应用控制策略阻止运行**
     如果系统开启了严格模式（Smart App Control / Windows Application Control），会直接禁止未签名 `.exe` 启动。此时**无需关闭系统安全防护**，推荐使用以下零拦截替代方案：
     - **从源码运行官方 Python（推荐桌面用户）**：按照下方 **方式二** 安装官方 Python 后执行 `python -m src.main`，完整享有全局快捷键、托盘与全部 GUI 功能；
     - **免安装 Web 版 / 浏览器扩展**：直接用浏览器打开 `web/index.html`（方式三），或加载 `browser-extension/`（方式四）。
4. **私有配置隔离存储**：Windows `.exe` 的配置文件自动保存于 `%LOCALAPPDATA%\Sanitizer\config.json`（与 `.exe` 目录隔离，避免升级或移动文件时丢失设置）。

### 方式二：从源码运行 / 终端 CLI 管道 / 打包 `.exe`（开发者）

```powershell
# 1. 创建并激活虚拟环境，安装依赖（含可选 cryptography 以启用 AES-256-GCM 加密导出）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 运行回归测试、Web 安全测试与跨平台规则对齐校验
python -m pytest -v
node tests/test_web_security.cjs
python scripts/sync_web_rules.py --check
python -m src.main --self-test

# 3. 开发者终端 CLI 管道 & AES-256-GCM 加密 Vault 跨进程脱敏/还原
$env:APS_VAULT_PASS = "YourStrongPassphrase"
python -m src.main --file .env.production --output .env.sanitized --vault-file vault.enc.json --encrypt --passphrase-env APS_VAULT_PASS
python -m src.main --restore-file ai_reply.txt --output restored.txt --vault-file vault.enc.json --passphrase-env APS_VAULT_PASS

# 4. 从源码启动桌面程序
python -m src.main

# 5. 导出多分辨率盾牌图标并打包单文件无黑框 .exe（已禁用 UPX 降低误报）
python -m src.main --export-ico assets/icon.ico
python -m PyInstaller --noconfirm AI-Privacy-Sanitizer.spec
```

### 方式三：使用 Web 纯内存版
直接用任意浏览器打开 [`web/index.html`](web/index.html)（或单文件静态部署），无需安装任何环境即可在浏览器内存中安全脱敏、拖入本地文件或差异预览。

### 方式四：加载零权限浏览器粘贴卫士扩展（Chrome / Edge / Brave）
打开 `chrome://extensions/` → 开启「开发者模式」→ 点击「加载已解压的扩展程序」→ 选择仓库中的 [`browser-extension/`](browser-extension/) 目录即可（详阅 [`browser-extension/README.md`](browser-extension/README.md)）。

### 方式五：实验性 macOS `.app` / `.dmg`（macOS 15 及以上）

Windows 的 `.exe` 无法在 macOS 原生运行。仓库提供实验性原生打包工作流：**Actions → Experimental macOS Build → Run workflow** 选择 `arm64`（Apple Silicon）或 `x86_64`（Intel）。产物采用 ad-hoc 临时签名（无 Apple 公证），暂不启用全局快捷键，配置私有保存于 `~/Library/Application Support/AI-Privacy-Sanitizer/config.json`。本地构建：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-macos-lock.txt
python scripts/build_macos.py --arch arm64  # Intel Mac 使用 x86_64
```

---

## 📘 新手完整使用教程

打开桌面端后，左侧栏提供 6 个核心页面，日常高频操作只需 4 步：

1. **🏠 首页总览：一键日常脱敏 / 还原 / 本地文件处理**
   - **日常剪贴板流程**：在 IDE 或终端按 `Ctrl+C` 复制含密钥/IP/手机号的文本 → 按 `Alt+S`（屏幕右下角弹出 Micro-HUD 提示脱敏数量）→ 将安全占位符粘贴给 AI → 复制 AI 回复后按 `Alt+R`（如被占用则自动为 `Ctrl+Shift+R`）即可 100% 还原；若想取回脱敏前原文，可点击首页或托盘的 **⏪ 撤销脱敏**。
   - **巡航模式（懒人全自动）**：打开首页或托盘中的 **⚡ 复制即自动脱敏**，复制后约 `0.55s` 内自动脱敏（托盘盾牌变为翠绿色），适合连续贴报错日志时使用；复制完毕粘贴前建议顺眼确认占位符。
   - **本地文件脱敏/还原**：点击 **📄 脱敏本地文件** 选择 `.env` / `.log` / `.json` 等文件，会输出脱敏副本而**不覆盖原文件**；拿回 AI 修改后的代码/配置后再点 **📥 还原本地文件**。

2. **🧪 实时沙盒：先试再发 & 右键秒加白名单**
   - 不放心规则效果时，直接把文本贴进 **实时沙盒** 输入框点击脱敏，沙盒默认只在隔离的临时映射中运行，不会污染主保险箱（确认无误后也可点击同步至主保险箱）。
   - 如果某个内部代号或版本号被误判为敏感词，在右侧预览框中**右键点击该占位符**，即可将该原值一键加入白名单并即时刷新结果。

3. **📚 词典与规则：贴合你自己的项目和团队**
   - **专属词典**：添加你们公司的域名、内部服务名、测试账号或客户简称（支持开启英文整词边界，避免误伤局部单词）。
   - **场景化预设**：在预设区一键切换 **开发调试**、**人事与法务** 或 **严格全量** 规则集，也可针对单条规则单独开关。

4. **🔐 内存保险箱：查看映射、防窥遮罩与加密迁移**
   - 这里集中显示当前会话拦截的所有真实值与占位符对照（默认自动打星号防窥屏，可切换显隐、搜索过滤、点击单行 **Copy Tag** 复制占位符或删除单条记录）。
   - 需要换电脑、重启软件或跨团队交接还原权限时，点击 **加密导出** 设置强口令，生成 `AES-256-GCM` 加密保险箱文件，后续随时导入恢复映射关系。

5. **⚙️ 安全与快捷键：自定义按键与自动焚毁**
   - **修改全局快捷键**：直接点击快捷键显示框即可开始录制，按下你想用的组合键（例如 `Ctrl+Shift+S`）松手即立即生效；按 `Esc` 可取消。若更习惯手动输入，点击右侧 `✏️` 输入文本后按 `Enter` 或点击绿色 `✓` 立即保存生效。如果某键被显卡面板或系统占用，点击 **↺ 恢复默认** 会自动避开冲突键位并提示可用组合。
   - **闲置自动焚毁**：开启后在指定分钟数（5–60 分钟）无操作时自动清空内存映射与撤销栈，离开工位更安心。

---

## ⌨️ 快捷键与托盘菜单指南

| 操作 | 默认快捷键 | 托盘右键菜单项 | 功能说明 |
| :--- | :--- | :--- | :--- |
| **打开控制中心** | 左键点击托盘图标 | `🖥️ 打开可视化控制中心` | 侧边栏图形化管理词典、预设规则、沙盒、保险箱与安全设置 |
| **一键脱敏** | `Alt + S` | `1. 立即脱敏剪贴板` | 将剪贴板敏感内容替换为安全占位符并弹出微浮窗统计反馈 |
| **一键还原** | `Alt + R` | `2. 立即还原剪贴板` | 将 AI 回复中的占位符容错恢复为真实数据（启用 Win+V 隐私保护） |
| **撤销脱敏** | 界面/托盘点击 | `⏪ 撤销上一次脱敏` | 一键恢复最近一次脱敏前的原始剪贴板内容（最多保留 5 次） |
| **自动脱敏巡航** | 界面/托盘勾选 | `⚡ 复制即自动脱敏 (巡航模式)` | 约每 0.55 秒尽力轮询；托盘盾牌变翠绿，粘贴前请核对结果 |
| **开机自动启动** | 界面/托盘勾选 | `🚀 开机自动启动` | 勾选后登录 Windows 时自动静默驻留右下角托盘（校验有效路径） |
| **清空内存映射** | 界面/托盘点击 | `4. 清空当前内存映射表` | 立即销毁当前会话内存中的所有映射记录与撤销栈 |
| **完全退出程序** | 界面/托盘点击 | `5. 退出程序 (Exit)` | 卸载全局快捷键并安全退出托盘进程 |

---

## 📂 目录结构

```text
ai-privacy-sanitizer/
├── .github/workflows/
│   └── ci-build.yml            # 跨平台自动化测试、规则对齐校验与 Windows EXE 发布流水线
├── browser-extension/          # 零权限 (permissions: []) Chromium MV3 AI 聊天粘贴拦截扩展
│   ├── manifest.json
│   ├── sanitizer_core.js
│   ├── content.js
│   ├── popup.html / popup.js
│   └── README.md
├── scripts/
│   ├── build_macos.py          # 实验性 macOS .app/.dmg 构建脚本
│   └── sync_web_rules.py       # Python 与 Web 跨平台黄金用例规则对齐校验脚本
├── src/
│   ├── __init__.py             # 版本信息定义 (v0.5.0)
│   ├── main.py                 # 动态托盘、微浮窗调度、闲置清理、全局快捷键、CLI 管道入口
│   ├── gui.py                  # CustomTkinter 侧边栏深浅色双语控制中心
│   ├── hud.py                  # 轻量级无焦点右下角微浮窗反馈 (FloatingMicroHud)
│   ├── clipboard_privacy.py    # Windows Win+V / 云剪贴板与 macOS Concealed 隐私标记
│   ├── vault_crypto.py         # Scrypt + AES-256-GCM 认证加密本地保险箱导入/导出
│   ├── i18n.py                 # 简体中文与英文国际化词条库
│   ├── sanitizer.py            # 双层高性能引擎、整词边界、AI 防变形提示、双阶段容错还原
│   ├── rules.py                # 47 项内置规则 + Luhn / MyKad NRIC / GB 11643 校验器 + 场景预设
│   ├── secure_io.py            # 私有权限原子写盘（POSIX 0600 / Windows 禁用继承 DACL）
│   └── startup.py              # 64 位安全 Windows 单实例唤醒/热替换、POSIX flock 与开机自启
├── tests/
│   ├── fixtures/rules_golden_cases.json  # Python & Web 共享黄金回归测试集
│   ├── test_v05_upgrades.py    # v0.3.2–v0.5.0 安全、性能、加密、CLI、GUI 与扩展回归测试
│   ├── test_web_security.cjs   # Web CSP、零存储、差异边界与黄金用例 Node 测试
│   └── ...                     # 核心引擎、安全边界、GUI 过渡、Windows 配置与快捷键测试
├── web/
│   └── index.html              # CSP 锁定 100% 纯浏览器内存 Web 版
├── config.example.json         # 公开的【示例】配置文件模板
├── requirements.txt            # Python 依赖清单
├── README.md                   # 英文版项目说明文档
└── README.zh-CN.md             # 简体中文版项目说明文档
```

---

## 🔒 安全承诺 (Security Commitment)

1. **100% 纯本地运行**：无任何遥测、无分析统计、无任何外发 HTTP/Socket 请求，绝不调用任何外部大模型 API；Web 版额外使用浏览器级 `Content-Security-Policy: default-src 'none'; connect-src 'none'` 强制断网。
2. **默认内存映射 + 可选 AES-256-GCM 加密落盘**：桌面会话映射默认仅驻留进程内存（并支持 5–60 分钟闲置自动清空）。如需跨进程或跨天复用映射，建议通过 GUI 加密导出或 CLI `--vault-file ... --encrypt --passphrase-env ...` 使用 **Scrypt + AES-256-GCM** 保护（不加 `--encrypt` 时 CLI `--vault-file` 仍兼容旧明文 JSON）。
3. **私有文件创建**：Vault、配置和导出通过私有临时文件及原子发布保存。POSIX 使用 `0600`，Windows 在写入前设置仅允许当前用户访问、禁止继承的 DACL；拒绝软链接、junction、硬链接和非普通文件。
4. **剪贴板历史防落盘**：启用「系统剪贴板隐私保护」后，还原/撤销写回真实敏感数据时会自动标记 Windows 排除剪贴板历史 (`Win+V`) 与云同步，降低敏感明文残留在 OS 历史记录中的风险（仍建议操作后尽快核对与清理）。
5. **长度、检测与剪贴板边界**：桌面、Web 与 CLI 在脱敏和还原两端均执行 `1,500,000` 字符上限保护；超限时安全失败且不输出错误或残留文本。模式匹配不能替代人工安全审查，提交高敏内容前请务必确认脱敏预览。
6. **主动还原与导入校验**：仅在本地由明确操作触发。AI 回复是不可信文本，有效映射标签会恢复真实数据，分享前必须检查。导入的 Vault（明文或加密）与配置均会经过严格 Schema 与一致性校验，无效或篡改文件会被原子拒绝且不影响当前会话。

### 安全输出与加密跨进程恢复

```powershell
python -m src.main --file input.log --output sanitized.log
# 已有输出必须显式允许覆盖；输入/输出的同文件别名始终拒绝。
python -m src.main --file input.log --output sanitized.log --overwrite
# 推荐：使用 --encrypt 与环境变量口令进行 AES-256-GCM 加密映射
$env:APS_VAULT_PASS = "YourStrongPassphrase"
python -m src.main --file input.log --output sanitized.log --vault-file private-mapping.enc.json --encrypt --passphrase-env APS_VAULT_PASS
python -m src.main --restore-file reply.txt --output restored.txt --vault-file private-mapping.enc.json --passphrase-env APS_VAULT_PASS
```

输入、输出、Vault 和配置必须是不同文件，包含路径别名。Shell 的 `>` 重定向可能在 Python 启动前就清空文件；需要保留原文件时优先使用 `--file`/`--output`。Vault 和输出分别原子保存，不构成多文件事务。

### 构建依赖与发布来源

CI 与 Windows 发行构建使用 `python -m pip install --require-hashes -r requirements-lock.txt`，固定直接/传递依赖的精确版本及 PyPI 产物 SHA-256。`requirements-macos-lock.txt` 在共享版本锁定之上补充带哈希的 macOS 构建依赖；源码安装保留 `requirements.txt` 兼容范围。更新时在干净的 Python 3.11 环境明确解析版本、包含 Windows 专用依赖、对照 PyPI 核验哈希，并只运行相关定向检查。Actions 固定完整上游提交 SHA；更新 SHA 与版本注释前需审阅上游变更。

只有标签 push 的发布 Job 获得 `contents: write`，PR/测试 Job 使用只读权限。发行构建附带源码提交/运行信息 (`build-info.json`) 和产物校验和 (`SHA256SUMS`)。校验和用于检测下载变更，不等同于代码签名或不同 runner 上逐字节可复现构建。比较下载的发行版 EXE 与源码时，请核对记录中的版本和校验和。

---

## 📄 开源协议 (License)

本项目基于 [MIT License](LICENSE) 开源。

