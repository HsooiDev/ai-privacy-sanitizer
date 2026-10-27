"""Bilingual (Simplified Chinese & English) localization strings for AI Privacy Sanitizer."""

from typing import Dict
from src import APP_NAME


STRINGS: Dict[str, Dict[str, str]] = {
    "zh": {
        "macos_preview_hotkeys": "macOS 实验版：暂不注册全局快捷键，请使用界面或菜单栏按钮；无需管理员权限。",
        'notify_input_too_large': '⚠️ 超过 1,500,000 字符，未处理；剪贴板原文仍未脱敏，请勿直接粘贴到外部服务',
        'notify_clip_changed': '⚠️ 剪贴板内容已变化，已取消写回，请重新操作',
        'msg_operation_failed': '操作失败，请检查格式、文件权限与安全保存位置。',
        'msg_export_warning': '导出文件包含自定义敏感词条和可能的凭证。请保存在私有目录，避免 Git、共享或云同步位置。',
        'msg_restore_warning': '已恢复真实数据；仅在本地使用，分享前请检查',
        'msg_copied': '📋 已复制到剪贴板',
        "window_title": APP_NAME,
        "brand_title": APP_NAME,
        "btn_about": "关于",
        "about_title": "关于 Sanitizer",
        "about_version": "版本 {version}",
        "about_description": "在本机进行敏感内容脱敏与还原的工具。",
        "brand_subtitle": "100% 本地内存运行 · 零网络请求 · 双向无损还原",
        "btn_lang": "🌐 EN / 简中",
        "btn_theme_dark": "🌙 暗色模式",
        "btn_theme_light": "☀️ 浅色模式",
        "nav_home": "🏠 首页总览",
        "nav_sandbox": "🧪 脱敏沙盒",
        "nav_dict": "📚 选填词库",
        "nav_vault": "🔐 内存保险箱",
        "nav_guide": "📖 使用指南",
        # Home Dashboard
        "hero_badge": "🟢 智能防护已就绪 · 零配置开箱即用",
        "hero_desc": (
            "无需预先填写任何资料！系统已自动开启 20+ 种高危敏感信息防护：\n"
            "API Keys (OpenAI/Claude/AWS/GitHub)、数据库密码、SSH 私钥、内网 IP、\n"
            "马来西亚手机号 (+60 / 01x)、大马身份证 (NRIC)、护照、银行卡与电子邮箱。"
        ),
        "btn_hero_sanitize": "🛡️ 一键脱敏剪贴板 (Alt + S)",
        "btn_hero_restore": "🔄 一键还原剪贴板 (Alt + R)",
        "stat_intercepted_title": "本次会话累计保护",
        "stat_intercepted_unit": "处敏感信息",
        "stat_vault_title": "当前内存映射数",
        "stat_vault_unit": "组对应关系",
        "stat_rules_title": "内置高强度规则",
        "stat_rules_unit": "项全自动启用",
        "switches_section_title": "⚡ 自动化与高级偏好设置（点击开关立即生效）",
        "sw_cruise_title": "⚡ 复制即自动脱敏（懒人巡航模式）",
        "sw_cruise_desc": "约每 0.55 秒尽力检查（上限 1,500,000 字符），不保证粘贴前完成；敏感文本请手动脱敏并检查结果",
        "sw_semantic_title": "🌐 同类型语义 IP 伪装 (192.0.2.x)",
        "sw_semantic_desc": "将真实内网/公网 IP 伪装为合法测试 IP（如 192.0.2.101），避免 AI 在分析服务器或网络配置时报错",
        "sw_startup_title": "🚀 开机自动启动 (Windows Startup)",
        "sw_startup_desc": "登录电脑时自动在右下角系统托盘静默待命，随时响应快捷键",
        "hotkey_section_title": "⌨️ 全局快捷键自定义（如遇 Alt+S 与其他软件冲突，可在此自由修改）",
        "hotkey_section_desc": "可从下拉框选择常用组合、手动输入（如 ctrl+shift+s / alt+q / f8），或点击“录制按键”后直接按下键盘组合：",
        "lbl_hk_sanitize": "🛡️ 脱敏快捷键：",
        "lbl_hk_restore": "🔄 还原快捷键：",
        "btn_hk_record": "🎯 录制按键",
        "btn_hk_recording": "⌨️ 请按下组合键...",
        "btn_hk_save": "💾 保存并立即生效",
        "btn_hk_reset": "↺ 恢复默认",
        "msg_hk_saved": "✅ 全局快捷键已更新并立即生效：脱敏 [{san}] | 还原 [{res}]",
        "msg_hk_err": "❌ 快捷键格式无效、重复或已被系统/其他程序占用，请重新设置",
        "msg_hk_rollback_err": "❌ 设置未保存，但无法确认旧快捷键已恢复。请暂用界面/托盘按钮，并重新应用快捷键。",
        "workflow_title": "💡 3 秒极简日常用法",
        "workflow_steps": (
            "① 复制代码或日志 (Ctrl+C)   ➔   "
            "② 按 Alt+S 脱敏后粘贴给 AI (Ctrl+V)   ➔   "
            "③ 复制 AI 回复后按 Alt+R 还原真实数据"
        ),
        # Sandbox Tab
        "sandbox_hint": "在左侧粘贴任意代码或日志，右侧实时查看脱敏效果（绿色高亮为已被保护的占位符）",
        "btn_load_sample": "📋 载入大马本地化测试样本",
        "btn_run_sanitize": "🛡️ 立即脱敏预览 ➔",
        "btn_run_restore": "🔄 测试逆向还原",
        "btn_copy_output": "📑 复制脱敏结果",
        "btn_clear_sandbox": "🧹 清空",
        "sandbox_left_title": "📥 原始文本 (Raw Input)",
        "sandbox_right_title": "🛡️ 脱敏后安全文本 (Sanitized Output)",
        # Dictionary Tab
        "dict_banner_title": "💡 进阶选填：个人专属名词词库（不填也不影响软件正常使用）",
        "dict_banner_desc": "软件已自动拦截所有密钥、密码、IP、+60 电话与 NRIC。仅当您希望隐藏特定的【公司名 / 客户名 / 项目代号】时才需在此添加。",
        "lbl_add_cat": "分类：",
        "placeholder_add_word": "输入公司名/客户名（支持用逗号 , 分隔批量添加多个词，回车保存）...",
        "btn_add_word": "➕ 添加词条",
        "lbl_filter_cat": "查看筛选：",
        "btn_del_selected": "🗑️ 删除选中",
        "btn_clear_all_dict": "🧹 清空全部示例词",
        "btn_json_editor": "🛠️ 内置 JSON 编辑器",
        "btn_import": "📥 导入",
        "btn_export": "📤 导出",
        "cat_all": "📋 全部类别 (ALL)",
        "cat_company": "🏢 公司名称 (COMPANY)",
        "cat_client": "🤝 客户名称 (CLIENT)",
        "cat_project": "🚀 项目代号 (PROJECT)",
        "cat_secret": "🔑 其他机密 (CUSTOM_SECRET)",
        # Vault Tab
        "vault_banner": "🔐 以下映射关系 100% 仅驻留于本地内存 (RAM)，绝不写入硬盘；程序退出或点击清空即刻销毁。",
        "placeholder_search_vault": "🔍 搜索占位符或原始值...",
        "btn_refresh_vault": "🔄 刷新列表",
        "btn_clear_vault": "🧹 清空内存保险箱",
        "vault_empty": "当前内存保险箱为空。当您按 Alt+S 或在沙盒执行脱敏后，映射关系会实时显示在这里。",
        "btn_copy_ph": "复制占位符",
        # JSON Modal
        "json_modal_title": "🛠️ 内置配置文件编辑器 (config.json) —— 直接修改无需外部软件",
        "json_modal_hint": "在此直接查看或编辑 config.json 内容，点击下方“保存并生效”即可（会自动校验 JSON 语法）：",
        "btn_save_json": "💾 保存并立即生效",
        "btn_open_folder": "📂 在资源管理器中定位文件",
        "btn_close": "关闭",
        "msg_json_saved": "✅ config.json 已成功保存并立即生效！",
        "msg_json_err": "❌ JSON 语法错误，请检查引号或逗号：\n",
        # Bottom Status Bar & Tray / Notifications
        "status_ready": "🟢 就绪：快捷键 Alt+S 脱敏剪贴板 | Alt+R 还原剪贴板",
        "btn_hide_tray": "🔽 最小化到托盘",
        "btn_exit_app": "🚪 完全退出程序",
        "btn_hero_undo": "⏪ 撤销上次脱敏",
        "sandbox_cat_empty": "📊 分类拦截统计：等待脱敏...",
        "sandbox_cat_prefix": "📊 拦截明细：",
        "dict_mode_words": "📚 自定义敏感词库 (Custom Words)",
        "dict_mode_rules": "🛡️ 白名单与内置规则开关 (Allowlist & Rules)",
        "allowlist_title": "🏳️ 免脱敏白名单 (Allowlist —— 列表中的 IP / 域名 / 邮箱将永远不会被脱敏)",
        "placeholder_allowlist": "输入无需脱敏的白名单项（如 127.0.0.1, localhost, example.com）...",
        "btn_add_allowlist": "➕ 加入白名单",
        "rules_toggle_title": "⚙️ 内置高强度规则开关 (取消勾选即可临时禁用对应检测器)",
        "sw_reveal_vault": "👁️ 显示原始敏感值",
        "tray_tooltip": "{app} (左键打开控制中心 | {san} 脱敏 | {res} 还原)",
        "tray_open_gui": "🖥️ 打开可视化控制中心 (设置 / 词典 / 教程)",
        "tray_sanitize": "1. 立即脱敏剪贴板 ({san})",
        "tray_restore": "2. 立即还原剪贴板 ({res})",
        "tray_undo": "⏪ 撤销上一次剪贴板脱敏 (Undo)",
        "tray_cruise": "⚡ 复制即自动脱敏 (巡航模式)",
        "tray_startup": "🚀 开机自动启动 (Windows Startup)",
        "tray_open_config": "3. 打开个人敏感词典 (config.json)",
        "tray_clear_vault": "4. 清空当前内存映射表 (Clear Session Map)",
        "tray_exit": "5. 退出程序 (Exit)",
        "notify_clip_read_err": "❌ 读取剪贴板失败: {err}",
        "notify_clip_write_err": "❌ 写入剪贴板失败: {err}",
        "notify_clip_empty_san": "ℹ️ 剪贴板为空，无需脱敏",
        "notify_clip_empty_res": "ℹ️ 剪贴板为空，无需还原",
        "notify_undo_ok": "⏪ 已撤销脱敏：剪贴板已恢复为脱敏前的原始文本（剩余可撤销 {left} 次）",
        "notify_undo_empty": "ℹ️ 当前没有可撤销的剪贴板脱敏记录",
        "notify_cruise_on": "⚡ 已开启“复制即自动脱敏”巡航模式（Ctrl+C 自动脱敏）",
        "notify_cruise_off": "⏹️ 已关闭“复制即自动脱敏”巡航模式",
        "notify_cruise_hit": "⚡ 自动巡航{summary}",
        "notify_startup_on": "🚀 已开启开机自动启动",
        "notify_startup_off": "⏹️ 已关闭开机自动启动",
        "notify_startup_err": "❌ 修改开机自动启动设置失败",
        "notify_vault_cleared": "🧹 已清空当前内存映射表（共释放 {count} 条记录）",
        # Tutorial Content
        "tutorial_body": """🛡️ 欢迎使用 Sanitizer —— 零门槛极速指南

1. 我需要先填写资料才能用吗？
   完全不需要！本软件开箱即用（Zero-Config Ready）。
   内置的 20+ 项高强度规则已经自动帮您拦截：
   • 马来西亚手机号（+60 12-345 6789 / 011-xxxx xxxx / +603-...）及国际号码
   • 马来西亚身份证号 (MyKad NRIC: 900307-14-5521)、护照号、银行卡号、电子邮箱
   • 各类大模型与云密钥 (sk-..., ghp_..., AKIA..., AIza..., xoxb-..., JWT, Bearer Token)
   • 数据库连接串密码 (postgres://, mysql://, mongodb://, redis://) 与 .env 配置文件密码
   • SSH / PEM 私钥证书块 (-----BEGIN PRIVATE KEY-----)
   • 内网 IPv4 (10.x.x.x, 192.168.x.x, 172.16-31.x.x)、公网 IPv4、IPv6、MAC 地址

2. 日常配合 ChatGPT / Claude / DeepSeek 怎么用？
   【标准快捷键模式】
   ① 复制 (Ctrl + C)：在编辑器或终端复制含机密的代码或日志。
   ② 脱敏 (Alt + S) ：按一下键盘 Alt + S，剪贴板里的机密瞬间变成安全标签（如 <API_KEY_1>、[PHONE_1]）。
   ③ 粘贴 (Ctrl + V)：直接粘贴给 AI 提问。
   ④ 还原 (Alt + R) ：复制 AI 回复的代码后按一下 Alt + R，所有标签 100% 自动变回您的真实数据！

   【懒人自动巡航模式】
   如果您在【🏠 首页总览】打开了“⚡ 复制即自动脱敏”开关，那么连 Alt + S 都不用按！
   约每 0.55 秒尽力检查，上限 1,500,000 字符；不保证粘贴前完成，请先检查脱敏结果。

3. 什么时候需要用【📚 选填词库】？
   只有当您想额外隐藏特定的“公司名字”（如某某 Sdn Bhd）、“客户名字”或“项目代号”时，
   才需要去【📚 选填词库】添加。系统会自动按字数从长到短优先匹配，且忽略英文大小写。

4. 什么是【🌐 同类型语义 IP 伪装】？
   开启后，真实内网 IP（如 10.52.18.9）会被替换为标准测试网段 IP（192.0.2.101），
   避免 AI 在帮您排查防火墙、Nginx 或网络配置时因为看到 [PRIVATE_IP_1] 标签而报错。
   按 Alt + R 时依然能 100% 还原回 10.52.18.9！
""",
    },
    "en": {
        "macos_preview_hotkeys": "macOS preview: global hotkeys are disabled; use GUI or menu-bar buttons. No administrator privileges required.",
        'notify_input_too_large': '⚠️ Over 1,500,000 characters; not processed. Clipboard remains UNSANITIZED; do not paste into external services.',
        'notify_clip_changed': '⚠️ Clipboard changed; write cancelled. Please retry.',
        'msg_operation_failed': 'Operation failed. Check format, permissions and private file location.',
        'msg_export_warning': 'Export includes custom sensitive terms and possibly credentials. Use a private folder outside Git, sharing and cloud sync.',
        'msg_restore_warning': 'Original values restored; use locally and review before sharing',
        'msg_copied': '📋 Copied to clipboard',
        "window_title": APP_NAME,
        "brand_title": APP_NAME,
        "btn_about": "About",
        "about_title": "About Sanitizer",
        "about_version": "Version {version}",
        "about_description": "A local tool for sanitizing and restoring sensitive content.",
        "brand_subtitle": "100% Local In-Memory · Zero Network Requests · Lossless Restore",
        "btn_lang": "🌐 简中 / EN",
        "btn_theme_dark": "🌙 Dark Mode",
        "btn_theme_light": "☀️ Light Mode",
        "nav_home": "🏠 Dashboard",
        "nav_sandbox": "🧪 Live Sandbox",
        "nav_dict": "📚 Custom Words",
        "nav_vault": "🔐 Session Vault",
        "nav_guide": "📖 Quick Guide",
        # Home Dashboard
        "hero_badge": "🟢 Protection Active · Zero-Setup Ready Out of the Box",
        "hero_desc": (
            "No manual form filling required! 20+ built-in detectors automatically mask:\n"
            "API Keys (OpenAI/Claude/AWS/GitHub), DB Passwords, SSH Keys, Private/Public IPs,\n"
            "Malaysian Phones (+60 / 01x), MyKad NRIC, Passports, Bank Cards & Emails."
        ),
        "btn_hero_sanitize": "🛡️ Sanitize Clipboard Now (Alt + S)",
        "btn_hero_restore": "🔄 Restore Clipboard Now (Alt + R)",
        "stat_intercepted_title": "Protected in Session",
        "stat_intercepted_unit": "sensitive items",
        "stat_vault_title": "Active Vault Mappings",
        "stat_vault_unit": "unique pairs",
        "stat_rules_title": "Built-in Detectors",
        "stat_rules_unit": "active rules",
        "switches_section_title": "⚡ Automation & Preferences (Instant Toggle)",
        "sw_cruise_title": "⚡ Auto-Sanitize on Copy (Cruise Mode)",
        "sw_cruise_desc": "Best-effort checks about every 0.55s (1,500,000-character limit); may miss an immediate paste. Sanitize sensitive text manually and review it",
        "sw_semantic_title": "🌐 Semantic IP Disguise Mode (192.0.2.x)",
        "sw_semantic_desc": "Replace real private/public IPs with RFC 5737 test IPs (e.g. 192.0.2.101) so AI tools parse network configs without syntax errors",
        "sw_startup_title": "🚀 Launch at Windows Startup",
        "sw_startup_desc": "Start silently in the system tray when you log into Windows",
        "hotkey_section_title": "⌨️ Custom Global Hotkeys (Change anytime if Alt+S conflicts with other apps)",
        "hotkey_section_desc": "Select a preset, type a custom key combo (e.g. ctrl+shift+s / alt+q / f8), or click 'Record Key' and press your shortcut:",
        "lbl_hk_sanitize": "🛡️ Sanitize Key:",
        "lbl_hk_restore": "🔄 Restore Key:",
        "btn_hk_record": "🎯 Record Key",
        "btn_hk_recording": "⌨️ Press keys...",
        "btn_hk_save": "💾 Save & Apply Now",
        "btn_hk_reset": "↺ Reset Default",
        "msg_hk_saved": "✅ Global hotkeys updated & active immediately: Sanitize [{san}] | Restore [{res}]",
        "msg_hk_err": "❌ Invalid, duplicate, or unavailable global hotkeys (possibly used by another app); please try again",
        "msg_hk_rollback_err": "❌ Settings were not saved, but previous hotkeys could not be confirmed restored. Use GUI/tray buttons and reapply your shortcuts.",
        "workflow_title": "💡 3-Second Daily Workflow",
        "workflow_steps": (
            "① Copy code/logs (Ctrl+C)   ➔   "
            "② Press Alt+S & Paste into AI (Ctrl+V)   ➔   "
            "③ Copy AI reply & Press Alt+R to restore real data"
        ),
        # Sandbox Tab
        "sandbox_hint": "Paste any code or logs on the left to preview sanitization in real time (green highlights show masked placeholders)",
        "btn_load_sample": "📋 Load MY Sample Log",
        "btn_run_sanitize": "🛡️ Sanitize Preview ➔",
        "btn_run_restore": "🔄 Test Restore",
        "btn_copy_output": "📑 Copy Sanitized Text",
        "btn_clear_sandbox": "🧹 Clear",
        "sandbox_left_title": "📥 Raw Input (Code / Logs)",
        "sandbox_right_title": "🛡️ Sanitized Output (Safe for AI)",
        # Dictionary Tab
        "dict_banner_title": "💡 Optional Custom Dictionary (Not required for standard protection)",
        "dict_banner_desc": "API keys, passwords, IPs, +60 phones & NRIC are already masked automatically. Add words here ONLY if you want to mask specific Company, Client, or Project names.",
        "lbl_add_cat": "Category:",
        "placeholder_add_word": "Enter company/client name (comma-separated for batch add, press Enter)...",
        "btn_add_word": "➕ Add Word",
        "lbl_filter_cat": "Filter:",
        "btn_del_selected": "🗑️ Delete Selected",
        "btn_clear_all_dict": "🧹 Clear All Examples",
        "btn_json_editor": "🛠️ In-App JSON Editor",
        "btn_import": "📥 Import",
        "btn_export": "📤 Export",
        "cat_all": "📋 All Categories (ALL)",
        "cat_company": "🏢 Company (COMPANY)",
        "cat_client": "🤝 Client (CLIENT)",
        "cat_project": "🚀 Project (PROJECT)",
        "cat_secret": "🔑 Custom Secret (CUSTOM_SECRET)",
        # Vault Tab
        "vault_banner": "🔐 All mappings below exist strictly in local RAM and are never written to disk. Exiting or clearing wipes them immediately.",
        "placeholder_search_vault": "🔍 Search placeholder or original value...",
        "btn_refresh_vault": "🔄 Refresh",
        "btn_clear_vault": "🧹 Clear Session Vault",
        "vault_empty": "Session Vault is currently empty. Press Alt+S or run the Sandbox to see live mappings here.",
        "btn_copy_ph": "Copy Tag",
        # JSON Modal
        "json_modal_title": "🛠️ Built-in Config Editor (config.json) — No External App Needed",
        "json_modal_hint": "Edit config.json directly inside the app and click Save & Apply below (JSON syntax is validated automatically):",
        "btn_save_json": "💾 Save & Apply Immediately",
        "btn_open_folder": "📂 Show File in Explorer",
        "btn_close": "Close",
        "msg_json_saved": "✅ config.json saved and applied immediately!",
        "msg_json_err": "❌ Invalid JSON syntax, please check quotes/commas:\n",
        # Bottom Status Bar & Tray / Notifications
        "status_ready": "🟢 Ready: Press Alt+S to Sanitize Clipboard | Alt+R to Restore Clipboard",
        "btn_hide_tray": "🔽 Minimize to Tray",
        "btn_exit_app": "🚪 Exit App",
        "btn_hero_undo": "⏪ Undo Sanitize",
        "sandbox_cat_empty": "📊 Category Breakdown: Waiting for input...",
        "sandbox_cat_prefix": "📊 Intercepted:",
        "dict_mode_words": "📚 Custom Words Dictionary",
        "dict_mode_rules": "🛡️ Allowlist & Built-in Rule Toggles",
        "allowlist_title": "🏳️ Allowlist (Values here will NEVER be sanitized — e.g. safe test IPs or domains)",
        "placeholder_allowlist": "Enter safe value to ignore (e.g. 127.0.0.1, localhost, example.com)...",
        "btn_add_allowlist": "➕ Add to Allowlist",
        "rules_toggle_title": "⚙️ Built-in Detector Toggles (Uncheck to temporarily disable specific rules)",
        "sw_reveal_vault": "👁️ Reveal Originals",
        "tray_tooltip": "{app} (Left-click Control Center | {san} Sanitize | {res} Restore)",
        "tray_open_gui": "🖥️ Open Control Center (Settings / Words / Guide)",
        "tray_sanitize": "1. Sanitize Clipboard Now ({san})",
        "tray_restore": "2. Restore Clipboard Now ({res})",
        "tray_undo": "⏪ Undo Last Clipboard Sanitize",
        "tray_cruise": "⚡ Auto-Sanitize on Copy (Cruise Mode)",
        "tray_startup": "🚀 Launch at Windows Startup",
        "tray_open_config": "3. Open Config Editor (config.json)",
        "tray_clear_vault": "4. Clear Session Vault",
        "tray_exit": "5. Exit Application",
        "notify_clip_read_err": "❌ Failed to read clipboard: {err}",
        "notify_clip_write_err": "❌ Failed to write clipboard: {err}",
        "notify_clip_empty_san": "ℹ️ Clipboard is empty; nothing to sanitize",
        "notify_clip_empty_res": "ℹ️ Clipboard is empty; nothing to restore",
        "notify_undo_ok": "⏪ Undone: Clipboard restored to original pre-sanitized text ({left} undos left)",
        "notify_undo_empty": "ℹ️ No previous clipboard sanitization to undo",
        "notify_cruise_on": "⚡ Best-effort Cruise Mode enabled; review before pasting",
        "notify_cruise_off": "⏹️ Auto-Sanitize Cruise Mode disabled",
        "notify_cruise_hit": "⚡ Cruise {summary}",
        "notify_startup_on": "🚀 Windows Startup auto-launch enabled",
        "notify_startup_off": "⏹️ Windows Startup auto-launch disabled",
        "notify_startup_err": "❌ Failed to update Windows Startup setting",
        "notify_vault_cleared": "🧹 Cleared Session Vault ({count} mappings released)",
        # Tutorial Content
        "tutorial_body": """🛡️ Welcome to Sanitizer — Quick Start Guide

1. Do I need to fill in any forms before using it?
   NO! The app works 100% out of the box with zero configuration.
   Over 20 built-in high-precision detectors automatically protect:
   • Malaysian Phone Numbers (+60 12-345 6789 / 011-xxxx xxxx / +603-...) & International Numbers
   • Malaysian NRIC (900307-14-5521), Passports, Bank Cards & Email Addresses
   • AI & Cloud API Keys (sk-..., ghp_..., AKIA..., AIza..., xoxb-..., JWT, Bearer Tokens)
   • Database Connection Strings (postgres://, mysql://, mongodb://, redis://) & .env Passwords
   • SSH / PEM Private Key Blocks (-----BEGIN PRIVATE KEY-----)
   • Private IPv4 (10.x.x.x, 192.168.x.x, 172.16-31.x.x), Public IPv4, IPv6 & MAC Addresses

2. How do I use it with ChatGPT / Claude / DeepSeek?
   [Standard Hotkey Mode]
   ① Copy (Ctrl + C)   : Copy sensitive code or logs from your IDE or terminal.
   ② Sanitize (Alt + S): Press Alt + S. Secrets in your clipboard are replaced with safe tags (e.g. <API_KEY_1>, [PHONE_1]).
   ③ Paste (Ctrl + V)  : Paste directly into ChatGPT or Claude.
   ④ Restore (Alt + R) : Copy the AI's response and press Alt + R — all tags are 100% restored to your real values!

   [Effortless Cruise Mode]
   Turn on "⚡ Auto-Sanitize on Copy" on the Home Dashboard.
   The app checks about every 0.55 seconds, up to 1,500,000 characters. It cannot guarantee completion before paste; review the result first.

3. When should I use [📚 Custom Words]?
   Only when you want to mask specific proprietary names (like your Company Sdn Bhd, Client names, or internal Project codenames).
   Longer phrases are automatically matched before shorter ones, case-insensitively.

4. What is [🌐 Semantic IP Disguise Mode]?
   When enabled, private IPs (like 10.52.18.9) are replaced with valid RFC 5737 test IPs (192.0.2.101)
   instead of [PRIVATE_IP_1], preventing AI tools from complaining about invalid IP syntax in firewall/Nginx configs.
   Pressing Alt + R still restores 192.0.2.101 back to 10.52.18.9 with 100% accuracy!
""",
    },
}


def tr(lang: str, key: str) -> str:
    """Return localized string for `lang` ('zh' or 'en') and `key`."""
    lang_key = "en" if str(lang).lower() == "en" else "zh"
    return STRINGS.get(lang_key, STRINGS["zh"]).get(key, key)

