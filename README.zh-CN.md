<div align="center">

# 🛡️ AI Privacy Sanitizer (AI 隐私脱敏卫士) `v0.3.1`

**100% 纯本地内存运行 · 零外部网络请求 · 可视化 GUI 控制中心 · 双向无损还原的系统剪贴板与 CLI 脱敏工具**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20Web-059669.svg)](#)
[![Zero Network](https://img.shields.io/badge/Privacy-100%25%20Local%20RAM-10b981.svg)](#安全承诺-security-commitment)

[**English**](README.md) | [**简体中文**](README.zh-CN.md)

</div>

---

## 💡 为什么需要 AI Privacy Sanitizer？

在日常使用 **ChatGPT、Claude、DeepSeek、Gemini、Cursor** 等大模型排查生产故障、分析日志或重构代码时，直接从终端或 IDE 复制粘贴极易泄露高危机密：
- 🔑 **API 密钥与云凭证** (`sk-...`, `sk_live_...`, `ghp_...`, `AKIA...`, `AIza...`, `xoxb-...`, `gsk_...`, `hf_...`, `npm_...`, `pypi-...`, `dop_v1_...`, `lin_api_...`, `sbp_...`, `PMAK-...`, `shpat_...`, Azure SAS `sig=...`, JWT, Bearer Token, 飞书/钉钉/企微/Slack/Discord Webhook)
- 🗄️ **数据库连接串与密码** (`postgres://`, `mysql://`, `mongodb://`, `redis://`, ODBC 连接串, `.env` 环境变量, `curl -u` 账号密码)
- 📜 **多行私钥证书块** (`-----BEGIN RSA/OPENSSH PRIVATE KEY-----`)
- 💻 **本地文件路径中的真实系统用户名** (`C:\Users\<username>\...`、`/Users/<username>/...`、`/home/<username>/...`，仅脱敏个人系统用户名段并完整保留路径结构)
- 🌐 **内网与网络基础设施** (内网 IPv4 `10.x.x.x` / `192.168.x.x` / `172.16-31.x.x`、公网 IPv4、IPv6、MAC 地址)
- 🪪 **个人身份与隐私信息 (PII)** (电子邮箱、马来西亚 `+60`/`01x` 及中国大陆/国际手机号、带州属代码校验的大马身份证 MyKad NRIC、中国 18 位身份证、护照号、带 Luhn 校验的银行卡号)
- 🏢 **商业机密实体** (公司全称/简称 `Sdn Bhd`、客户名称、内部项目代号)

**AI Privacy Sanitizer** 常驻于系统托盘，无需复杂配置，通过全局快捷键一键完成**剪贴板双层脱敏 (`Alt+S`)**、**复制即自动脱敏（巡航模式）**与 **AI 回复占位符 100% 容错无损还原 (`Alt+R`)**。所有敏感映射关系仅保存在本地运行内存（RAM）中，关机或退出即焚。

---

## ✨ 核心特性

### 1. 🖥️ 零门槛可视化 GUI 控制中心 (`src/gui.py`)
- **🏠 首页总览与即时开关**：直观展示本次会话拦截统计，支持一键切换 **复制即自动脱敏（懒人巡航模式）**、**全类别语义伪装模式 (`192.0.2.x` / `user1@example.com` / `dev_user_1`)**、**开机自动启动**、**深色/浅色主题** 与 **中英双语界面**。内置 **⏪ 撤销脱敏 (Undo)** 按钮（纯内存保留最近 5 次脱敏前快照）。
- **⌨️ 全局快捷键自由录制**：若默认 `Alt+S` / `Alt+R` 与其他软件冲突，可直接下拉选择或点击“🎯 录制按键”自定义任意组合键，保存即刻生效。
- **🧪 实时脱敏测试沙盒**：左侧输入或粘贴原始代码/日志，右侧实时预览脱敏效果（绿色高亮标记被保护的占位符），顶部实时展示**按类别统计的彩色胶囊标签**（如 `API_KEY: 6 | DB_PASS: 5`）。
- **📚 选填专属词典 + 白名单与内置规则开关**：
  - 按 `COMPANY`（公司）、`CLIENT`（客户）、`PROJECT`（项目）、`CUSTOM_SECRET`（机密）分类管理词条，支持逗号批量添加、导入/导出备份，并内置语法校验 JSON 编辑器（绝不强行跳转外部编辑器）。
  - 支持切换至 **“🛡️ 白名单 (Allowlist) 与内置规则开关”** 子面板，自由添加免脱敏白名单或按需启用/禁用任意内置正则规则。
- **🔐 内存映射保险箱 (`SessionVault`) 与防窥屏遮罩**：实时检索当前会话内存中保存的 `占位符 <-> 真实敏感值` 对应关系；默认将原始敏感值打星号遮罩（如 `sk-pro***O678`），点击 **“👁️ 显示/遮罩原始敏感值”** 才明文显示，防止共享屏幕或录屏时意外泄密。

### 2. 🧠 双层高强度脱敏与容错还原引擎 (`src/sanitizer.py` & `src/rules.py`)
- **第一层：个人高危词典（按词长从长到短优先匹配）**：忽略大小写，严格优先匹配长词条（例如先匹配 `"Acme Global Technologies Sdn Bhd"`，再匹配 `"Acme Global"`），防止短词截断长词。
- **第二层：35+ 项内置高强度正则规则库 + 算法级校验器**：
  - **Luhn 与大马 NRIC 校验器**：内置 `luhn_checksum_valid` 彻底消除 16 位时间戳/订单号误报为银行卡的问题；内置 `my_nric_valid` 严格校验出生月日与马来西亚合法州属代码（PB Code）。
  - **保留结构脱敏**：精准识别数据库连接串、URL Basic Auth、操作系统文件路径与代码赋值语句，仅替换密码、Token 或用户名部分（如 `postgres://dbadmin:[DB_PASS_1]@[PRIVATE_IP_1]:5432/prod`），完美保留代码语法结构。
  - **中英文自然语言键值兼容**：全面支持 `password = "..."`、`pass = ...`、`pw = ...`、`id = ...` 以及中文日常表达（如 `密码-123123`、`登录密码 是 xxx`、`账号=asdasd`、`户口=...`）。
  - **两阶段容错逆向还原 (Fuzzy & Case-Insensitive Restore)**：即使大模型在回复中将 `<API_KEY_1>` 改写为 `[API_KEY_1]`、`` `API_KEY_1` ``、`<api_key_1>`、`{API_KEY_1}` 或 HTML 实体 `&lt;API_KEY_1&gt;`，`restore()` 依然能 100% 准确识别并还原。

### 3. 🌐 全类别语义伪装模式 (RFC 5737 & 语义实体)
- 在让 AI 排查防火墙、Nginx 或集群网络配置时，如果将 IP 替换为 `[PRIVATE_IP_1]`，部分模型可能会报格式语法错误。
- 开启 **语义伪装模式** 后，真实内网 IP（如 `10.52.18.9`）伪装为 RFC 5737 标准测试 IP（`192.0.2.101`），公网 IP 伪装为 `203.0.113.101`，邮箱伪装为 `user1@example.com`，路径用户名伪装为 `dev_user_1`；按 `Alt+R` 时依然能 **100% 逆向还原**回原始真实值！

### 4. 🛡️ 内核级防多开热替换 + 终端 CLI 管道 + 纯前端零残留 Web 版
- **单实例防多开与自动唤醒 (`src/startup.py`)**：基于 Windows 内核命名互斥锁（Mutex）与事件对象（Event），零网络端口占用。程序在后台托盘运行时，再次双击 `.exe` 会直接唤醒已有控制中心窗口；若检测到 `.exe` 版本更新，会自动通知旧进程退出并无缝完成热替换。
- **开发者终端 CLI 管道模式 (`src/main.py`)**：支持 `--stdin`、`--restore-stdin`、`--file <path>` 与 `--output <path>`，可直接嵌入终端管道流批处理脱敏日志文件。
- **100% 纯内存 Web 版 (`web/index.html`)**：单文件零依赖网页版，所有脱敏与还原均在浏览器当前标签页的 JS 内存变量中完成，**绝不写入 `localStorage` / Cookie，零网络请求，内置 10 分钟闲置自动清空倒计时、🔍 差异高亮悬停预览 (Diff Preview)、保险箱防窥遮罩与纯内存白名单**，关闭或刷新页面即彻底销毁。

---

## 🔄 3 秒极简日常工作流

```text
┌────────────────────────────────────────────────────────────────────────────┐
│ ① 复制代码或日志 (Ctrl + C)                                                │
│                                  │                                         │
│                                  ▼                                         │
│ ② 按 Alt + S（或开启巡航模式自动触发）──► 剪贴板机密瞬间替换为安全占位符   │
│   例如：postgres://admin:[DB_PASS_1]@192.0.2.101:5432/prod                 │
│                                  │                                         │
│                                  ▼                                         │
│ ③ 直接粘贴给 ChatGPT / Claude / DeepSeek 提问 (Ctrl + V) 并复制 AI 回复    │
│                                  │                                         │
│                                  ▼                                         │
│ ④ 按 Alt + R ──► AI 回复中的所有占位符（含变形占位符）100% 恢复为真实数据  │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 方式一：直接双击独立 `.exe` 运行（推荐普通用户）
1. 直接双击运行 **`AI-Privacy-Sanitizer.exe`**。
2. 首次启动会自动弹出**可视化控制中心窗口**，并在右下角系统托盘生成蓝色盾牌锁图标。
3. 点击窗口右上角 `X` 会自动最小化常驻到右下角系统托盘；左键点击托盘图标或再次双击 `.exe` 即可随时唤出控制中心。

### 方式二：从源码运行 / 终端 CLI 管道 / 打包 `.exe`（开发者）

```powershell
# 1. 创建并激活虚拟环境，安装依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. 运行单元测试与内置自检
pytest -v
python -m src.main --self-test

# 3. 开发者终端 CLI 管道脱敏用法
Get-Content app.log | python -m src.main --stdin > app.sanitized.log
python -m src.main --file .env.production --output .env.sanitized

# 4. 从源码启动桌面程序
python -m src.main

# 5. 导出多分辨率盾牌图标并打包单文件无黑框 .exe
python -m src.main --export-ico assets/icon.ico
pyinstaller --noconfirm AI-Privacy-Sanitizer.spec
```

### 方式三：使用 Web 纯内存版
直接用任意浏览器打开 [`web/index.html`](web/index.html)（或单文件上传至 Hostinger / GitHub Pages / Cloudflare Pages），无需安装任何环境即可在浏览器内存中安全脱敏与还原。

---

## ⌨️ 快捷键与托盘菜单指南

| 操作 | 默认快捷键 | 托盘右键菜单项 | 功能说明 |
| :--- | :--- | :--- | :--- |
| **打开控制中心** | 左键点击托盘图标 | `🖥️ 打开可视化控制中心` | 图形化增删敏感词、白名单与规则开关、沙盒测试、查看内存映射表 |
| **一键脱敏** | `Alt + S` | `1. 立即脱敏剪贴板` | 将剪贴板敏感内容替换为安全占位符并弹出拦截统计通知 |
| **一键还原** | `Alt + R` | `2. 立即还原剪贴板` | 将 AI 回复中的占位符或伪装值 100% 容错恢复为真实数据 |
| **撤销脱敏** | 界面/托盘点击 | `⏪ 撤销上一次脱敏` | 一键恢复最近一次脱敏前的原始剪贴板内容（最多保留 5 次） |
| **自动脱敏巡航** | 界面/托盘勾选 | `⚡ 复制即自动脱敏 (巡航模式)` | 开启后只要 `Ctrl+C` 复制文本即在 0.5 秒内自动完成脱敏 |
| **开机自动启动** | 界面/托盘勾选 | `🚀 开机自动启动` | 勾选后登录 Windows 时自动静默驻留右下角托盘 |
| **清空内存映射** | 界面/托盘点击 | `4. 清空当前内存映射表` | 立即销毁当前会话内存中的所有映射记录与撤销栈 |
| **完全退出程序** | 界面/托盘点击 | `5. 退出程序 (Exit)` | 卸载全局快捷键并安全退出托盘进程 |

---

## 📂 目录结构

```text
ai-privacy-sanitizer/
├── .github/workflows/
│   └── ci-build.yml         # GitHub Actions 跨平台自动测试与 Windows EXE 自动发布流水线
├── src/
│   ├── __init__.py          # 版本信息定义 (v0.3.0)
│   ├── main.py              # 托盘图标、全局快捷键、撤销栈、巡航监听、CLI 管道与单实例入口
│   ├── gui.py               # CustomTkinter 深浅色中英双语 GUI 控制中心
│   ├── i18n.py              # 简体中文与英文国际化词条库
│   ├── sanitizer.py         # 核心：双层脱敏引擎、白名单、双阶段容错还原与 SessionVault
│   ├── rules.py             # 35+ 项内置高强度正则表达式库 + Luhn/MyKad NRIC 校验器
│   └── startup.py           # Windows 开机自启注册表管理与内核级单实例唤醒/热替换机制
├── tests/
│   └── test_sanitizer.py    # 18 项完整单元测试（核心引擎、校验器、CLI 管道、Web 完整性）
├── web/
│   └── index.html           # 100% 纯浏览器内存运行 Web 版（零 localStorage 落盘）
├── config.example.json      # 公开的【示例】配置文件模板
├── requirements.txt         # Python 依赖库清单
├── README.md                # 英文版项目说明文档
└── README.zh-CN.md          # 简体中文版项目说明文档
```

---

## 🔒 安全承诺 (Security Commitment)

1. **100% 纯本地运行**：无任何遥测、无分析统计、无任何外发 HTTP/Socket 请求，绝不调用任何外部大模型 API。
2. **敏感数据零落盘**：所有双向映射表（`SessionVault`）仅驻留于进程内存（RAM）中，程序退出或点击“清空当前内存映射表”即刻彻底销毁。
3. **防泄密 Git 保护**：`.gitignore` 已严格忽略本地 `config.json`、`*.local.json`、`*secret*` 等文件，确保您的真实公司名、客户名与内部代号永远不会被意外提交到代码仓库。

---

## 📄 开源协议 (License)

本项目基于 [MIT License](LICENSE) 开源。

