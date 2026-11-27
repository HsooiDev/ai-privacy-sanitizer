"""Bilingual (Simplified Chinese & English) localization strings for Sanitizer."""

from typing import Dict
from src import APP_NAME


STRINGS: Dict[str, Dict[str, str]] = {
    "zh": {
        "macos_preview_hotkeys": "macOS 实验版：暂不注册全局快捷键，请使用界面或菜单栏按钮；无需管理员权限。",
        "notify_input_too_large": "⚠️ 超过 1,500,000 字符，未处理；剪贴板原文仍未脱敏，请勿直接粘贴到外部服务",
        "notify_clip_changed": "⚠️ 剪贴板内容已变化，已取消写回，请重新操作",
        "notify_idle_wiped": "⏱️ 闲置超时：已自动清空内存保险箱（释放 {count} 条映射）",
        "msg_operation_failed": "操作失败，请检查格式、文件权限与安全保存位置。",
        "msg_export_warning": "导出文件包含自定义敏感词条和可能的凭证。请保存在私有目录，避免 Git、共享或云同步位置。",
        "msg_restore_warning": "已恢复真实数据；仅在本地使用，分享前请检查",
        "msg_copied": "📋 已复制到剪贴板",
        "msg_dict_cleared": "🧹 已清空全部自定义词条",
        "msg_export_ok": "📤 配置备份已安全导出",
        "msg_import_ok": "📥 配置已校验并生效",
        "msg_vault_cleared_status": "🧹 内存保险箱已清空",
        "msg_word_removed": "🗑️ 已移除词条",
        "msg_allowlist_added": "🏳️ 已加入免脱敏白名单并刷新预览",
        "msg_sandbox_synced": "🔗 已将沙盒映射同步到全局保险箱",
        "msg_file_sanitized": "📄 文件已本地脱敏并导出",
        "msg_file_restored": "🔄 文件已本地还原并导出",
        "msg_enc_vault_saved": "🔐 加密保险箱已保存 (AES-256-GCM)",
        "msg_enc_vault_loaded": "🔓 加密保险箱已解密载入",
        "msg_hk_cancelled": "ℹ️ 已取消快捷键录制",
        "msg_hk_modifier_required": "❌ 请使用修饰键组合（如 Ctrl/Alt/Shift + 按键）或功能键 F1–F24",
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
        "sidebar_status_ready": "手动防护就绪",
        "sidebar_status_cruise": "⚡ 巡航运行中",
        "sidebar_cruise_short": "巡航模式",
        "sidebar_idle_label": "⏱️ 自动清空",
        "sidebar_idle_off": "未开启",
        "nav_home": "🏠 首页总览",
        "nav_sandbox": "🧪 脱敏沙盒",
        "nav_dict": "📚 词库与规则",
        "nav_vault": "🔐 内存保险箱",
        "nav_settings": "⚙️ 快捷键与安全",
        "nav_guide": "📖 使用指南",
        # Home Dashboard
        "hero_badge": "🟢 智能防护已就绪 · 零配置开箱即用",
        "hero_desc": (
            "无需预先填写任何资料！系统已自动开启 38+ 项高危敏感信息防护：\n"
            "API Keys、Basic/Bearer 认证、含 @ 数据库密码、SSH/PGP 私钥、IPv4/压缩 IPv6、\n"
            "本机路径用户名、大马 +60 手机与 MyKad NRIC、中国身份证校验、护照与银行卡。"
        ),
        "btn_hero_sanitize": "🛡️ 一键脱敏剪贴板 (Alt + S)",
        "btn_hero_restore": "🔄 一键还原剪贴板 (Alt + R)",
        "btn_hero_undo": "⏪ 撤销上次脱敏",
        "stat_intercepted_title": "本次会话累计保护",
        "stat_intercepted_unit": "处敏感信息",
        "stat_vault_title": "当前内存映射数",
        "stat_vault_unit": "组对应关系",
        "stat_rules_title": "高强度检测规则",
        "stat_rules_unit": "项已启用",
        "switches_section_title": "⚡ 常用防护模式（点击开关立即生效）",
        "sw_cruise_title": "⚡ 复制即自动脱敏（懒人巡航模式）",
        "sw_cruise_desc": "约每 0.55 秒尽力检查（上限 1,500,000 字符），不保证粘贴前完成；敏感文本请手动脱敏并检查结果",
        "sw_semantic_title": "🌐 同类型语义伪装 (192.0.2.x / user1@example.com)",
        "sw_semantic_desc": "将真实 IP / 邮箱 / 路径伪装为合法测试格式，避免 AI 排查服务器或网络配置时报错",
        "sw_ai_hint_title": "🤖 附带 AI 防变形指令（提升还原成功率）",
        "sw_ai_hint_desc": "在脱敏文本顶部自动附加一行极简提示，要求 AI 原样保留占位符，还原时自动剥离",
        "sw_startup_title": "🚀 开机自动启动 (Windows Startup)",
        "sw_startup_desc": "登录电脑时自动在右下角系统托盘静默待命，随时响应快捷键",
        "sw_hud_title": "✨ 右下角轻量悬浮微提示 (HUD)",
        "sw_hud_desc": "即使开启系统勿扰模式，按快捷键后也能在右下角看到不抢焦点的 2 秒确认条",
        "sw_clip_guard_title": "🔒 禁止还原明文写入 Win+V 历史与云剪贴板",
        "sw_clip_guard_desc": "按还原或撤销写回敏感原文时附加系统隐私标记，防止残留于剪贴板历史",
        "sw_whole_word_title": "🔤 英文自定义短词默认整词边界匹配",
        "sw_whole_word_desc": "防止短项目代号（如 art）误切正常英文单词（Start / party）；中文词不受影响",
        "lbl_idle_wipe": "⏱️ 内存保险箱闲置自动清空：",
        "idle_wipe_off": "关闭（仅退出时清空）",
        "idle_wipe_min": "{m} 分钟",
        "file_drop_title": "📄 本地文件一键脱敏 / 还原",
        "file_drop_desc": "支持 .env / .log / .json / .yaml / .csv / .txt，本地原子导出并同步映射",
        "btn_sanitize_file": "📄 选择文件脱敏",
        "btn_restore_file": "🔄 选择文件还原",
        # Hotkeys & Settings Page
        "hotkey_section_title": "⌨️ 全局快捷键自定义（点击直接按键录制 · Esc 取消）",
        "hotkey_section_desc": "点击快捷键框或“录制按键”，直接按下任意组合键（支持字母/数字/符号/方向键/小键盘 + Ctrl/Alt/Shift/Win，或独立 F1-F24），录制后立即生效并同步更新使用指南：",
        "privacy_section_title": "🔒 桌面端隐私与反馈强化设置",
        "lbl_hk_sanitize": "🛡️ 脱敏快捷键：",
        "lbl_hk_restore": "🔄 还原快捷键：",
        "btn_hk_record": "🎯 录制按键",
        "btn_hk_recording": "⏹️ 取消录制 (Esc)",
        "btn_hk_edit": "✏️",
        "hk_box_listening": "⌨️ 请按组合键 (Esc)...",
        "hk_box_edit_hint": "⌨️ 手动输入快捷键后按 Enter 或点 ✓ 立即生效，Esc 取消",
        "btn_hk_save": "💾 保存并立即生效",
        "btn_hk_reset": "↺ 恢复默认",
        "msg_hk_saved": "✅ 全局快捷键已更新并立即生效：脱敏 [{san}] | 还原 [{res}]",
        "msg_hk_err": "❌ 快捷键格式无效、缺少修饰键、重复或已被系统占用，请重新设置",
        "msg_hk_occupied": "❌ 快捷键 [{key}] 已被其他软件（如显卡面板或系统快捷键）占用，请更换其他组合键",
        "msg_hk_reset_fallback": "ℹ️ 默认快捷键 [{conflict}] 已被其他软件占用，已自动切换为可用默认组合：脱敏 [{san}] | 还原 [{res}]",
        "msg_hk_rollback_err": "❌ 设置未保存，但无法确认旧快捷键已恢复。请暂用界面/托盘按钮，并重新应用快捷键。",
        "workflow_title": "💡 3 秒极简日常用法",
        "workflow_steps": (
            "① 复制代码或日志 (Ctrl+C)   ➔   "
            "② 按 Alt+S 脱敏后粘贴给 AI (Ctrl+V)   ➔   "
            "③ 复制 AI 回复后按 Alt+R 还原真实数据"
        ),
        # Sandbox Tab
        "sandbox_hint": "左侧粘贴代码或日志，右侧按风险等级分色预览；右键高亮标签可一键加入白名单",
        "btn_load_sample": "📋 载入测试样本",
        "btn_run_sanitize": "🛡️ 脱敏预览 ➔",
        "btn_run_restore": "🔄 测试还原",
        "btn_copy_output": "📑 复制结果",
        "btn_clear_sandbox": "🧹 清空",
        "sw_sandbox_isolate": "🧪 沙盒隔离（不污染保险箱）",
        "btn_sync_sandbox_vault": "🔗 同步到全局保险箱",
        "sandbox_left_title": "📥 原始文本 (Raw Input)",
        "sandbox_right_title": "🛡️ 脱敏预览（分色高亮 · 右键标签可放行）",
        "sandbox_cat_empty": "📊 分类拦截统计：等待脱敏...",
        "sandbox_cat_prefix": "📊 拦截明细：",
        "ctx_allowlist_placeholder": "🏳️ 将此原值加入白名单 (放行)",
        # Dictionary & Rules Tab
        "dict_mode_words": "📚 自定义敏感词库 (Custom Words)",
        "dict_mode_rules": "🛡️ 白名单与内置规则开关 (Allowlist & Rules)",
        "dict_banner_title": "💡 进阶选填：个人专属名词词库（不填也不影响软件正常使用）",
        "dict_banner_desc": "软件已自动拦截所有密钥、密码、IP、路径、+60 电话与 NRIC。仅当您希望隐藏特定公司名 / 客户名 / 项目代号时在此添加。",
        "lbl_add_cat": "分类：",
        "placeholder_add_word": "输入公司名/客户名（支持用逗号 , 分隔批量添加多个词，回车保存）...",
        "btn_add_word": "➕ 添加词条",
        "lbl_filter_cat": "查看筛选：",
        "btn_del_selected": "🗑️ 删除选中",
        "btn_clear_all_dict": "🧹 清空全部自定义词",
        "btn_json_editor": "🛠️ 内置 JSON 编辑器",
        "btn_import": "📥 导入词库",
        "btn_export": "📤 导出备份",
        "cat_all": "📋 全部类别 (ALL)",
        "cat_company": "🏢 公司名称 (COMPANY)",
        "cat_client": "🤝 客户名称 (CLIENT)",
        "cat_project": "🚀 项目代号 (PROJECT)",
        "cat_secret": "🔑 其他机密 (CUSTOM_SECRET)",
        "allowlist_title": "🏳️ 免脱敏白名单 (Allowlist —— 列表中的值将跳过脱敏)",
        "placeholder_allowlist": "输入无需脱敏的白名单项（如 127.0.0.1, localhost）...",
        "btn_add_allowlist": "➕ 加入白名单",
        "rules_toggle_title": "⚙️ 内置高强度规则开关（支持场景预设与搜索）",
        "placeholder_rule_search": "🔍 搜索规则名称、类别或示例...",
        "preset_dev": "💻 开发运维推荐",
        "preset_hr": "🏢 办公 / HR 全量",
        "preset_strict": "🔑 极简仅密钥",
        "confirm_clear_dict_title": "确认清空自定义词库",
        "confirm_clear_dict_msg": "确定要清空您在全部类别中保存的自定义敏感词吗？此操作不可撤销。",
        # Vault Tab
        "vault_banner": "🔐 以下映射关系 100% 仅驻留于本地内存 (RAM)，默认防窥遮罩；退出、清空或闲置超时即刻销毁。",
        "placeholder_search_vault": "🔍 搜索占位符、类别或原始值...",
        "btn_refresh_vault": "🔄 刷新",
        "btn_clear_vault": "🔥 清空保险箱",
        "btn_export_enc_vault": "🔐 加密导出",
        "btn_import_enc_vault": "🔓 加密导入",
        "vault_empty": "当前内存保险箱为空。当您按 Alt+S 或使用文件脱敏后，映射关系会实时显示在这里。",
        "btn_copy_ph": "复制标签",
        "sw_reveal_vault": "👁️ 显示原始敏感值",
        "confirm_clear_vault_title": "确认清空内存保险箱",
        "confirm_clear_vault_msg": "清空后当前会话的所有映射与撤销快照将立即销毁，无法再还原正在等待的 AI 回复。是否继续？",
        "prompt_passphrase_title": "加密保险箱口令 (AES-256-GCM)",
        "prompt_passphrase_export": "请输入加密口令（至少 4 个字符，仅用于本机加密，切勿遗忘）：",
        "prompt_passphrase_import": "请输入解密口令以载入加密保险箱：",
        # JSON Modal
        "json_modal_title": "🛠️ 内置配置文件编辑器 (config.json)",
        "json_modal_hint": "直接编辑 config.json，保存前会自动校验 JSON 语法与配置结构：",
        "btn_format_json": "✨ 格式化 JSON",
        "btn_save_json": "💾 保存并立即生效",
        "btn_open_folder": "📂 定位文件所在目录",
        "btn_close": "关闭",
        "msg_json_saved": "✅ config.json 已校验保存并立即生效！",
        "msg_json_err": "❌ JSON 语法错误：",
        "msg_json_syntax_pos": "❌ JSON 语法错误（第 {line} 行，第 {col} 列），请检查引号或逗号。",
        # Bottom Status Bar & Tray / Notifications
        "status_ready": "🟢 就绪：快捷键 Alt+S 脱敏剪贴板 | Alt+R 还原剪贴板",
        "btn_hide_tray": "🔽 藏至托盘",
        "btn_exit_app": "🚪 完全退出",
        "tray_tooltip": "{app} (左键打开控制中心 | {san} 脱敏 | {res} 还原)",
        "tray_open_gui": "🖥️ 打开可视化控制中心",
        "tray_sanitize": "1. 立即脱敏剪贴板 ({san})",
        "tray_restore": "2. 立即还原剪贴板 ({res})",
        "tray_undo": "⏪ 撤销上一次剪贴板脱敏 (Undo)",
        "tray_cruise": "⚡ 复制即自动脱敏 (巡航模式)",
        "tray_startup": "🚀 开机自动启动 (Windows Startup)",
        "tray_open_config": "3. 打开个人配置文件编辑器 (config.json)",
        "tray_clear_vault": "4. 清空当前内存映射表 (Clear Session Map)",
        "tray_exit": "5. 退出程序 (Exit)",
        "notify_clip_read_err": "❌ 读取剪贴板失败: {err}",
        "notify_clip_write_err": "❌ 写入剪贴板失败: {err}",
        "notify_clip_empty_san": "ℹ️ 剪贴板为空，无需脱敏",
        "notify_clip_empty_res": "ℹ️ 剪贴板为空，无需还原",
        "notify_undo_ok": "⏪ 已撤销脱敏：剪贴板已恢复为脱敏前的原始文本（剩余可撤销 {left} 次）",
        "notify_undo_empty": "ℹ️ 当前没有可撤销的剪贴板脱敏记录",
        "notify_cruise_on": "⚡ 已开启“复制即自动脱敏”巡航模式（托盘盾牌已切换绿色）",
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
   内置 38+ 项高强度检测规则与算法校验器，自动帮您拦截：
   • 各类大模型与云密钥 (OpenAI/Anthropic/AWS/GitHub/Google/Slack/Stripe/JWT/Bearer/HTTP Basic Auth)
   • 数据库连接串密码（完整支持含 @ 密码）、.env 环境变量、SSH / PEM / PGP 私钥证书块
   • 内网 IPv4、公网 IPv4（含 .0 网段）、完整及压缩格式 IPv6、MAC 地址、本机路径用户名
   • 马来西亚手机 (+60 / 01x)、大马 MyKad NRIC、中国大陆 18 位身份证（GB11643 校验）、护照、银行卡（Luhn 校验）与邮箱

2. 日常配合 ChatGPT / Claude / DeepSeek 怎么用？
   【标准快捷键模式】
   ① 复制 (Ctrl + C)：在编辑器或终端复制含机密的代码或日志。
   ② 脱敏 (Alt + S) ：按一下 Alt + S，剪贴板机密瞬间替换为安全占位符（如 <API_KEY_1>、[DB_PASS_1]）。
   ③ 粘贴 (Ctrl + V)：直接粘贴给 AI 提问（可开启“附带 AI 防变形指令”提高还原率）。
   ④ 还原 (Alt + R) ：复制 AI 回复后按 Alt + R，所有占位符无损还原，并自动附加 Win+V 隐私防留痕标记！

   【懒人自动巡航模式】
   在左侧状态栏或托盘开启“⚡ 巡航模式”后，托盘盾牌变为翡翠绿，软件约每 0.55 秒尽力自动脱敏。

3. 沙盒与误报处理技巧
   • 【🧪 脱敏沙盒】默认使用独立隔离保险箱，随便测试不会污染您的全局会话映射。
   • 看到某项误报？在右侧脱敏结果中**右键点击彩色占位符**即可一键将其加入白名单！
   • 您也可以在【📚 词库与规则】一键切换「开发运维 / 办公 HR / 极简仅密钥」三套预设。

4. 本地文件与加密保险箱
   • 首页支持直接选择 `.env` / `.log` / `.json` 文件一键离线脱敏与还原。
   • 跨天排查故障时，可在【🔐 内存保险箱】使用 AES-256-GCM 口令加密导出映射，次日再安全解密载入。
""",
    },
    "en": {
        "macos_preview_hotkeys": "macOS preview: global hotkeys are disabled; use GUI or menu-bar buttons. No administrator privileges required.",
        "notify_input_too_large": "⚠️ Over 1,500,000 characters; not processed. Clipboard remains UNSANITIZED; do not paste into external services.",
        "notify_clip_changed": "⚠️ Clipboard changed; write cancelled. Please retry.",
        "notify_idle_wiped": "⏱️ Idle timeout: Session Vault auto-cleared ({count} mappings released)",
        "msg_operation_failed": "Operation failed. Check format, permissions and private file location.",
        "msg_export_warning": "Export includes custom sensitive terms and possibly credentials. Use a private folder outside Git, sharing and cloud sync.",
        "msg_restore_warning": "Original values restored; use locally and review before sharing",
        "msg_copied": "📋 Copied to clipboard",
        "msg_dict_cleared": "🧹 Cleared all custom words",
        "msg_export_ok": "📤 Config backup exported safely",
        "msg_import_ok": "📥 Config validated and applied",
        "msg_vault_cleared_status": "🧹 Session Vault cleared",
        "msg_word_removed": "🗑️ Custom word removed",
        "msg_allowlist_added": "🏳️ Added to allowlist and refreshed preview",
        "msg_sandbox_synced": "🔗 Sandbox mappings synced to Session Vault",
        "msg_file_sanitized": "📄 Local file sanitized and saved",
        "msg_file_restored": "🔄 Local file restored and saved",
        "msg_enc_vault_saved": "🔐 Encrypted vault saved (AES-256-GCM)",
        "msg_enc_vault_loaded": "🔓 Encrypted vault decrypted and loaded",
        "msg_hk_cancelled": "ℹ️ Hotkey recording cancelled",
        "msg_hk_modifier_required": "❌ Use a modifier combo (Ctrl/Alt/Shift + key) or F1–F24",
        "window_title": APP_NAME,
        "brand_title": APP_NAME,
        "btn_about": "About",
        "about_title": "About Sanitizer",
        "about_version": "Version {version}",
        "about_description": "A local tool for sanitizing and restoring sensitive content.",
        "brand_subtitle": "100% Local In-Memory · Zero Network · Lossless Restore",
        "btn_lang": "🌐 简中 / EN",
        "btn_theme_dark": "🌙 Dark Mode",
        "btn_theme_light": "☀️ Light Mode",
        "sidebar_status_ready": "Ready (Manual)",
        "sidebar_status_cruise": "⚡ Cruise Active",
        "sidebar_cruise_short": "Cruise Mode",
        "sidebar_idle_label": "⏱️ Auto-Wipe",
        "sidebar_idle_off": "Off",
        "nav_home": "🏠 Dashboard",
        "nav_sandbox": "🧪 Live Sandbox",
        "nav_dict": "📚 Words & Rules",
        "nav_vault": "🔐 Session Vault",
        "nav_settings": "⚙️ Hotkeys & Safety",
        "nav_guide": "📖 Quick Guide",
        # Home Dashboard
        "hero_badge": "🟢 Protection Active · Zero-Setup Ready Out of the Box",
        "hero_desc": (
            "No manual setup required! 38+ built-in detectors automatically mask:\n"
            "API Keys, Basic/Bearer Auth, DB Passwords (incl. '@'), SSH/PGP Keys, IPv4 & Compressed IPv6,\n"
            "OS Path Usernames, MY +60 Phones & MyKad NRIC, CN ID (checksum), Passports & Bank Cards."
        ),
        "btn_hero_sanitize": "🛡️ Sanitize Clipboard Now (Alt + S)",
        "btn_hero_restore": "🔄 Restore Clipboard Now (Alt + R)",
        "btn_hero_undo": "⏪ Undo Sanitize",
        "stat_intercepted_title": "Protected in Session",
        "stat_intercepted_unit": "sensitive items",
        "stat_vault_title": "Active Vault Mappings",
        "stat_vault_unit": "unique pairs",
        "stat_rules_title": "Built-in Detectors",
        "stat_rules_unit": "active rules",
        "switches_section_title": "⚡ Protection Modes (Instant Toggle)",
        "sw_cruise_title": "⚡ Auto-Sanitize on Copy (Cruise Mode)",
        "sw_cruise_desc": "Best-effort checks about every 0.55s (1,500,000-character limit); review before pasting",
        "sw_semantic_title": "🌐 Semantic Disguise Mode (192.0.2.x / user1@example.com)",
        "sw_semantic_desc": "Replace real IPs, emails, and paths with RFC 5737 / valid test formats so AI parses configs cleanly",
        "sw_ai_hint_title": "🤖 Prepend AI Preservation Hint (Higher Restore Rate)",
        "sw_ai_hint_desc": "Adds a concise top note instructing AI to keep placeholders verbatim; auto-stripped on restore",
        "sw_startup_title": "🚀 Launch at Windows Startup",
        "sw_startup_desc": "Start silently in the system tray when you log into Windows",
        "sw_hud_title": "✨ Floating Bottom-Right Micro-HUD",
        "sw_hud_desc": "Shows a brief non-focus-stealing confirmation pill even when OS Focus Assist hides toasts",
        "sw_clip_guard_title": "🔒 Exclude Restored Secrets from Win+V History & Cloud Sync",
        "sw_clip_guard_desc": "Attaches OS privacy markers when writing restored plaintext or undo snapshots to clipboard",
        "sw_whole_word_title": "🔤 Whole-Word Boundaries for ASCII Custom Terms",
        "sw_whole_word_desc": "Prevents short project codes (e.g. 'art') from breaking words ('Start', 'party'); CJK unaffected",
        "lbl_idle_wipe": "⏱️ Auto-Wipe Session Vault After Inactivity:",
        "idle_wipe_off": "Off (Clear on exit only)",
        "idle_wipe_min": "{m} min",
        "file_drop_title": "📄 Local File Sanitize / Restore",
        "file_drop_desc": "Supports .env / .log / .json / .yaml / .csv / .txt with private atomic export",
        "btn_sanitize_file": "📄 Sanitize File",
        "btn_restore_file": "🔄 Restore File",
        # Hotkeys & Settings Page
        "hotkey_section_title": "⌨️ Custom Global Hotkeys (Click & press any combo · Esc cancels)",
        "hotkey_section_desc": "Click a shortcut box or Record Key and press any key combo (letters, digits, symbols, arrows, numpad + Ctrl/Alt/Shift/Win, or standalone F1-F24). Applies immediately & syncs Quick Guide:",
        "privacy_section_title": "🔒 Desktop Privacy & Feedback Controls",
        "lbl_hk_sanitize": "🛡️ Sanitize Key:",
        "lbl_hk_restore": "🔄 Restore Key:",
        "btn_hk_record": "🎯 Record Key",
        "btn_hk_recording": "⏹️ Cancel (Esc)",
        "btn_hk_edit": "✏️",
        "hk_box_listening": "⌨️ Press keys (Esc)...",
        "hk_box_edit_hint": "⌨️ Type shortcut then press Enter or ✓ to apply, Esc to cancel",
        "btn_hk_save": "💾 Save & Apply",
        "btn_hk_reset": "↺ Reset Default",
        "msg_hk_saved": "✅ Global hotkeys updated & active immediately: Sanitize [{san}] | Restore [{res}]",
        "msg_hk_err": "❌ Invalid, unmodified, duplicate, or unavailable global hotkeys; please try again",
        "msg_hk_occupied": "❌ Hotkey [{key}] is already occupied by another app (e.g., GPU overlay / system shortcut). Please pick another combo.",
        "msg_hk_reset_fallback": "ℹ️ Default hotkey [{conflict}] is occupied by another app; reset to available defaults: Sanitize [{san}] | Restore [{res}]",
        "msg_hk_rollback_err": "❌ Settings were not saved, but previous hotkeys could not be confirmed restored. Use GUI/tray buttons and reapply your shortcuts.",
        "workflow_title": "💡 3-Second Daily Workflow",
        "workflow_steps": (
            "① Copy code/logs (Ctrl+C)   ➔   "
            "② Press Alt+S & Paste into AI (Ctrl+V)   ➔   "
            "③ Copy AI reply & Press Alt+R to restore real data"
        ),
        # Sandbox Tab
        "sandbox_hint": "Paste text on the left for risk-colored preview; right-click any tag to allowlist it",
        "btn_load_sample": "📋 Load Sample",
        "btn_run_sanitize": "🛡️ Sanitize ➔",
        "btn_run_restore": "🔄 Test Restore",
        "btn_copy_output": "📑 Copy Output",
        "btn_clear_sandbox": "🧹 Clear",
        "sw_sandbox_isolate": "🧪 Isolate Sandbox (No Vault Pollution)",
        "btn_sync_sandbox_vault": "🔗 Sync to Global Vault",
        "sandbox_left_title": "📥 Raw Input (Code / Logs)",
        "sandbox_right_title": "🛡️ Sanitized Output (Risk-Colored · Right-Click to Allowlist)",
        "sandbox_cat_empty": "📊 Category Breakdown: Waiting for input...",
        "sandbox_cat_prefix": "📊 Intercepted:",
        "ctx_allowlist_placeholder": "🏳️ Add Original Value to Allowlist",
        # Dictionary & Rules Tab
        "dict_mode_words": "📚 Custom Words Dictionary",
        "dict_mode_rules": "🛡️ Allowlist & Built-in Rule Toggles",
        "dict_banner_title": "💡 Optional Custom Dictionary (Not required for standard protection)",
        "dict_banner_desc": "API keys, passwords, IPs, paths, +60 phones & NRIC are already masked automatically. Add proprietary Company/Client/Project terms here.",
        "lbl_add_cat": "Category:",
        "placeholder_add_word": "Enter company/client name (comma-separated for batch add, press Enter)...",
        "btn_add_word": "➕ Add Word",
        "lbl_filter_cat": "Filter:",
        "btn_del_selected": "🗑️ Delete Selected",
        "btn_clear_all_dict": "🧹 Clear All Custom Words",
        "btn_json_editor": "🛠️ In-App JSON Editor",
        "btn_import": "📥 Import",
        "btn_export": "📤 Export",
        "cat_all": "📋 All Categories (ALL)",
        "cat_company": "🏢 Company (COMPANY)",
        "cat_client": "🤝 Client (CLIENT)",
        "cat_project": "🚀 Project (PROJECT)",
        "cat_secret": "🔑 Custom Secret (CUSTOM_SECRET)",
        "allowlist_title": "🏳️ Allowlist (Values here will NEVER be sanitized)",
        "placeholder_allowlist": "Enter safe value to ignore (e.g. 127.0.0.1, localhost)...",
        "btn_add_allowlist": "➕ Add Allowlist",
        "rules_toggle_title": "⚙️ Built-in Detectors (Presets & Search)",
        "placeholder_rule_search": "🔍 Search rule name, category, or example...",
        "preset_dev": "💻 DevOps Recommended",
        "preset_hr": "🏢 Office / HR Full",
        "preset_strict": "🔑 Keys Only (Minimal)",
        "confirm_clear_dict_title": "Clear All Custom Words",
        "confirm_clear_dict_msg": "Are you sure you want to remove ALL custom sensitive words across all categories? This cannot be undone.",
        # Vault Tab
        "vault_banner": "🔐 All mappings below exist strictly in local RAM and are masked by default. Exiting, clearing, or idle timeout wipes them immediately.",
        "placeholder_search_vault": "🔍 Search placeholder, category, or original...",
        "btn_refresh_vault": "🔄 Refresh",
        "btn_clear_vault": "🔥 Clear Vault",
        "btn_export_enc_vault": "🔐 Encrypted Export",
        "btn_import_enc_vault": "🔓 Encrypted Import",
        "vault_empty": "Session Vault is currently empty. Press Alt+S or sanitize a file to see live mappings here.",
        "btn_copy_ph": "Copy Tag",
        "sw_reveal_vault": "👁️ Reveal Originals",
        "confirm_clear_vault_title": "Clear Session Vault",
        "confirm_clear_vault_msg": "All active mappings and undo snapshots will be destroyed immediately. You won't be able to restore pending AI replies. Continue?",
        "prompt_passphrase_title": "Encrypted Vault Passphrase (AES-256-GCM)",
        "prompt_passphrase_export": "Enter a local passphrase (min 4 characters) to encrypt this vault:",
        "prompt_passphrase_import": "Enter the passphrase to decrypt and load this vault:",
        # JSON Modal
        "json_modal_title": "🛠️ Built-in Config Editor (config.json)",
        "json_modal_hint": "Edit config.json directly; JSON syntax and config schema are validated before saving:",
        "btn_format_json": "✨ Format JSON",
        "btn_save_json": "💾 Save & Apply",
        "btn_open_folder": "📂 Show File in Folder",
        "btn_close": "Close",
        "msg_json_saved": "✅ config.json validated, saved, and applied immediately!",
        "msg_json_err": "❌ Invalid JSON syntax: ",
        "msg_json_syntax_pos": "❌ Invalid JSON syntax at line {line}, column {col}. Check quotes or commas.",
        # Bottom Status Bar & Tray / Notifications
        "status_ready": "🟢 Ready: Press Alt+S to Sanitize Clipboard | Alt+R to Restore Clipboard",
        "btn_hide_tray": "🔽 Hide to Tray",
        "btn_exit_app": "🚪 Exit App",
        "tray_tooltip": "{app} (Left-click Control Center | {san} Sanitize | {res} Restore)",
        "tray_open_gui": "🖥️ Open Control Center",
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
        "notify_cruise_on": "⚡ Best-effort Cruise Mode enabled (tray icon turned green)",
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
   38+ built-in high-precision detectors automatically protect:
   • AI & Cloud API Keys (OpenAI/Anthropic/AWS/GitHub/Google/Slack/Stripe/JWT/Bearer/HTTP Basic Auth)
   • DB Connection Passwords (supports '@' inside passwords), .env Secrets, SSH / PEM / PGP Private Keys
   • Private & Public IPv4 (incl. .0 subnets), Full & Compressed IPv6, MAC Addresses, OS Path Usernames
   • MY Phones (+60 / 01x), MyKad NRIC, CN 18-digit ID (checksum), Passports, Bank Cards (Luhn) & Emails

2. How do I use it with ChatGPT / Claude / DeepSeek?
   [Standard Hotkey Mode]
   ① Copy (Ctrl + C)   : Copy sensitive code or logs from your IDE or terminal.
   ② Sanitize (Alt + S): Press Alt + S. Secrets become safe tags (e.g. <API_KEY_1>, [DB_PASS_1]).
   ③ Paste (Ctrl + V)  : Paste directly into ChatGPT or Claude (optionally enable AI Preservation Hint).
   ④ Restore (Alt + R) : Copy the AI's response and press Alt + R — original values recover cleanly with Win+V history protection!

   [Effortless Cruise Mode]
   Toggle "⚡ Cruise Mode" in the sidebar or tray — the shield turns green and best-effort auto-sanitizes copies.

3. Sandbox & One-Click Allowlist
   • [🧪 Live Sandbox] runs in an isolated vault by default so typing tests never pollute your live session.
   • Spot a false positive? Right-click any colored placeholder in the Sandbox output to Allowlist it instantly!
   • Switch between DevOps, Office/HR, and Keys-Only presets in [📚 Words & Rules].

4. Local Files & Encrypted Vault
   • Sanitize or restore local .env / .log / .json files right from the Dashboard.
   • For multi-day investigations, export/import your Session Vault with AES-256-GCM passphrase encryption.
""",
    },
}


def tr(lang: str, key: str) -> str:
    """Return localized string for `lang` ('zh' or 'en') and `key`."""
    lang_key = "en" if str(lang).lower() == "en" else "zh"
    return STRINGS.get(lang_key, STRINGS["zh"]).get(key, key)
