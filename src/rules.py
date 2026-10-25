"""Built-in high-strength regex rule definitions and sample payloads for ai-privacy-sanitizer."""

from dataclasses import dataclass
from typing import Callable, List, Optional, Pattern
import re


def luhn_checksum_valid(card_str: str) -> bool:
    """Validate a bank card number string (13-19 digits after stripping spaces/hyphens) using the Luhn algorithm."""
    digits = re.sub(r"[\s\-]", "", str(card_str or ""))
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    if len(set(digits)) == 1:
        return False
    total = 0
    for idx, ch in enumerate(digits[::-1]):
        n = int(ch)
        if idx % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def my_nric_valid(nric_str: str) -> bool:
    """Validate Malaysian MyKad NRIC (month 01-12, valid max days per month, and valid Place of Birth PB codes)."""
    digits = re.sub(r"[\s\-]", "", str(nric_str or ""))
    if not digits.isdigit() or len(digits) != 12:
        return False
    mm = int(digits[2:4])
    dd = int(digits[4:6])
    pb = int(digits[6:8])
    max_days = {
        1: 31,
        2: 29,
        3: 31,
        4: 30,
        5: 31,
        6: 30,
        7: 31,
        8: 31,
        9: 30,
        10: 31,
        11: 30,
        12: 31,
    }
    if mm not in max_days or not (1 <= dd <= max_days[mm]):
        return False
    valid_pb = (
        (1 <= pb <= 16)
        or (21 <= pb <= 59)
        or (60 <= pb <= 68)
        or (71 <= pb <= 79)
        or (82 <= pb <= 83)
        or (98 <= pb <= 99)
    )
    return valid_pb


@dataclass(frozen=True)
class SanitizeRule:
    """Represents a single regex sanitization rule."""

    name: str
    category: str
    pattern: Pattern[str]
    placeholder_template: str = "[{category}_{index}]"
    target_group: str = ""  # If set, only sanitize this named group within the match
    validator: Optional[Callable[[str], bool]] = None
    enabled_by_default: bool = True


# Common non-secret programming keywords to exclude from unquoted shorthand assignments
_NON_SECRET_LOOKAHEAD = (
    r"(?![\$\{\(\[])"
    r"(?!(?:true|false|null|none|nil|undefined|nan|yes|no|int|str|string|bool|float|"
    r"number|object|array|auto|default|void|return|break|continue|pass)\b)"
    r"(?!\w+\()"
    r"(?!(?:self|this|cls|super|window|document|req|res|request|response|row|item|data|obj|event|err|error)\.)"
)

# Separator for Chinese keys: supports =, :, ：, -, —, ~, 是, 为, or spaces
_ZH_SEP = r"(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+)"

# Separator for English keys: supports =, :, ：, spaced hyphen " - ", or tight hyphen when value has digits
_EN_SEP = r"(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d))"


def _compile_rules() -> List[SanitizeRule]:
    """Compile and return ordered regex sanitization rules."""
    return [
        # --- 0. Multi-line PEM / SSH Private Key Blocks ---
        SanitizeRule(
            name="pem_ssh_private_key",
            category="PRIVATE_KEY",
            pattern=re.compile(
                r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
            ),
            placeholder_template="<PRIVATE_KEY_{index}>",
        ),
        # --- 1. Database, URL Basic Auth & CLI Auth Connection Strings ---
        SanitizeRule(
            name="db_connection_uri_password",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis(?:s)?|amqp|mssql)"
                r"://(?:[^:/@\s'\"`]+:)?(?P<secret>[^@\s'\"`]+)@"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="url_basic_auth_password",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)\b(?:https?|ftp)://[^:/@\s'\"`]+:(?P<secret>[^@\s'\"`]+)@"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="cli_curl_basic_auth",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)(?<!\S)(?:-u|--user)\s+['\"`]?[^:\s'\"`]+:(?P<secret>[^\s'\"`]+)['\"`]?"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="webhook_secret_url",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)(?:discord(?:app)?\.com/api/webhooks/\d+/|"
                r"hooks\.slack\.com/services/|"
                r"open\.feishu\.cn/open-apis/bot/v2/hook/|"
                r"oapi\.dingtalk\.com/robot/send\?access_token=|"
                r"qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=)"
                r"(?P<secret>[A-Za-z0-9_\-/]{16,})"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
        ),
        # --- 2. Explicit Signature API Keys & Cloud Tokens ---
        SanitizeRule(
            name="jwt_token",
            category="API_KEY",
            pattern=re.compile(
                r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"
            ),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="openai_anthropic_sk_key",
            category="API_KEY",
            pattern=re.compile(
                r"\bsk-(?:proj-|ant-api\d{2}-|ant-|live-|test-)?[A-Za-z0-9_\-]{16,}\b"
            ),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="stripe_live_test_key",
            category="API_KEY",
            pattern=re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[0-9a-zA-Z]{16,}\b"),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="github_token",
            category="API_KEY",
            pattern=re.compile(
                r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
            ),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="groq_hf_npm_pypi_key",
            category="API_KEY",
            pattern=re.compile(
                r"\b(?:gsk_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|npm_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_\-]{24,})\b"
            ),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="aws_access_key",
            category="API_KEY",
            pattern=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="google_api_key",
            category="API_KEY",
            pattern=re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="slack_token",
            category="API_KEY",
            pattern=re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b"),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="telegram_bot_token",
            category="API_KEY",
            pattern=re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b"),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="sendgrid_api_key",
            category="API_KEY",
            pattern=re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="cloudflare_or_do_or_linear_or_supabase_token",
            category="API_KEY",
            pattern=re.compile(
                r"\b(?:dop_v1_[a-f0-9]{64}|lin_api_[A-Za-z0-9]{40}|sbp_[a-f0-9]{40}|"
                r"PMAK-[a-f0-9]{24}-[a-f0-9]{34}|shpat_[a-fA-F0-9]{32})\b"
            ),
            placeholder_template="<API_KEY_{index}>",
        ),
        SanitizeRule(
            name="azure_sas_url",
            category="API_KEY",
            pattern=re.compile(r"(?i)[?&]sig=(?P<secret>[A-Za-z0-9%+/=]{24,})"),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
        ),
        SanitizeRule(
            name="bearer_token",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)\bBearer\s+(?P<secret>[A-Za-z0-9_\-\.~+/]{12,}=*)"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
        ),
        # --- 3. Email Addresses ---
        SanitizeRule(
            name="email_address",
            category="EMAIL",
            pattern=re.compile(
                r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
            ),
            placeholder_template="[EMAIL_{index}]",
        ),
        # --- 4. Network & Infrastructure ---
        SanitizeRule(
            name="mac_address",
            category="MAC_ADDR",
            pattern=re.compile(
                r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"
            ),
            placeholder_template="[MAC_{index}]",
        ),
        SanitizeRule(
            name="ipv6_address",
            category="IPV6",
            pattern=re.compile(
                r"\b(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|"
                r"(?:[0-9A-Fa-f]{1,4}:){1,7}:|"
                r"(?:[0-9A-Fa-f]{1,4}:){1,6}:[0-9A-Fa-f]{1,4}|"
                r"(?:[0-9A-Fa-f]{1,4}:){1,5}(?::[0-9A-Fa-f]{1,4}){1,2}|"
                r"(?:[0-9A-Fa-f]{1,4}:){1,4}(?::[0-9A-Fa-f]{1,4}){1,3}|"
                r"fe80:(?::[0-9A-Fa-f]{0,4}){0,4}%[0-9a-zA-Z]{1,})\b"
            ),
            placeholder_template="[IPV6_{index}]",
        ),
        SanitizeRule(
            name="private_ipv4",
            category="PRIVATE_IP",
            pattern=re.compile(
                r"(?<![\d.])(?:"
                r"10\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|"
                r"172\.(?:1[6-9]|2\d|3[01])\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|"
                r"192\.168\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
                r")(?![\d.])"
            ),
            placeholder_template="[PRIVATE_IP_{index}]",
        ),
        SanitizeRule(
            name="public_ipv4",
            category="PUBLIC_IP",
            pattern=re.compile(
                r"(?<![\d.vV])"
                r"(?!0\.)(?!10\.)(?!127\.)"
                r"(?!192\.168\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)"
                r"(?!192\.0\.2\.)(?!198\.51\.100\.)(?!203\.0\.113\.)"
                r"(?:25[0-4]|2[0-4]\d|1\d\d|[1-9]\d?)\."
                r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\."
                r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\."
                r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]\d?)"
                r"(?![\d.])"
            ),
            placeholder_template="[PUBLIC_IP_{index}]",
        ),
        # --- 5. Personal Identifiable Information (PII - Malaysia Prioritized) & User Paths ---
        SanitizeRule(
            name="user_file_path",
            category="USER_PATH",
            pattern=re.compile(
                r"(?i)(?:[A-Za-z]:[\\/]+Users[\\/]+|(?<![A-Za-z0-9_])/Users/|(?<![A-Za-z0-9_])/home/)"
                r"(?!(?:Public|Default(?:\s+User)?|All\s+Users|root|ubuntu|admin|ec2-user|vagrant|docker|nobody|www-data|postgres|git|runner)(?:[\\/]|$))"
                r"(?P<secret>[A-Za-z0-9._\- ]{2,64}?)(?=[\\/])"
            ),
            placeholder_template="[USER_PATH_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="my_nric",
            category="ID_CARD",
            pattern=re.compile(r"\b\d{6}-\d{2}-\d{4}\b"),
            placeholder_template="[ID_CARD_{index}]",
            validator=my_nric_valid,
        ),
        SanitizeRule(
            name="cn_id_card",
            category="ID_CARD",
            pattern=re.compile(
                r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"
            ),
            placeholder_template="[ID_CARD_{index}]",
        ),
        SanitizeRule(
            name="bank_card",
            category="BANK_CARD",
            pattern=re.compile(
                r"\b(?:4\d{3}|5[1-5]\d{2}|62\d{2})(?:[ -]?\d{4}){3}\b"
            ),
            placeholder_template="[BANK_CARD_{index}]",
            validator=luhn_checksum_valid,
        ),
        SanitizeRule(
            name="passport_number",
            category="PASSPORT",
            pattern=re.compile(r"\b(?:[A-HK-NP-Z]\d{8}|[EGDSP]\d{8})\b"),
            placeholder_template="[PASSPORT_{index}]",
        ),
        SanitizeRule(
            name="phone_number",
            category="PHONE",
            pattern=re.compile(
                r"(?<!\d)(?:"
                r"(?:(?:\+|00)60[\s\-]?|0)1(?:1[\s\-]?\d{4}[\s\-]?\d{4}|[02-9][\s\-]?\d{3}[\s\-]?\d{4})|"
                r"(?:\+|00)60[\s\-]?[3-9][\s\-]?\d{3,4}[\s\-]?\d{4}|"
                r"\+(?:65|1|44|61|81|82|852|853|886)[\s\-]?\d{3,4}[\s\-]?\d{4,6}|"
                r"(?:(?:\+|00)86[\s\-]?)?1[3-9]\d[\s\-]?\d{4}[\s\-]?\d{4}"
                r")(?!\d)"
            ),
            placeholder_template="[PHONE_{index}]",
        ),
        # --- 6. Chinese Key-Value Assignments (Supports -, =, :, ：, 是, 为, space, plus quoted spaces) ---
        SanitizeRule(
            name="zh_password_quoted_assignment",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)(?:数据库密码|登录密码|管理员密码|管理密码|初始密码|默认密码|支付密码|交易密码|"
                r"无线密码|新密码|旧密码|原密码|密码|口令|安全码|验证码|动态码|校验码|PIN码)"
                + _ZH_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{3,})(?P=q)"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="zh_password_assignment",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)(?:数据库密码|登录密码|管理员密码|管理密码|初始密码|默认密码|支付密码|交易密码|"
                r"无线密码|新密码|旧密码|原密码|密码|口令|安全码|验证码|动态码|校验码|PIN码)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>[^\s#;,，。！!？?)'\"`\]\}\r\n]{3,})['\"`]?"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="zh_api_key_quoted_assignment",
            category="API_KEY",
            pattern=re.compile(
                r"(?:访问密钥|私有密钥|接口密钥|应用密钥|签名密钥|密钥|秘钥|私钥|令牌)"
                + _ZH_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{4,})(?P=q)"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
        ),
        SanitizeRule(
            name="zh_api_key_assignment",
            category="API_KEY",
            pattern=re.compile(
                r"(?:访问密钥|私有密钥|接口密钥|应用密钥|签名密钥|密钥|秘钥|私钥|令牌)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>[^\s#;,，。！!？?)'\"`\]\}\r\n]{4,})['\"`]?"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
        ),
        SanitizeRule(
            name="zh_id_card_assignment",
            category="ID_CARD",
            pattern=re.compile(
                r"(?:身份证号码|身份证号|身份证|证件号码|证件号|大马卡号|大马卡|护照号码|护照号|税号|社保号)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>[A-Za-z0-9\-]{6,20})['\"`]?"
            ),
            placeholder_template="[ID_CARD_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="zh_phone_assignment",
            category="PHONE",
            pattern=re.compile(
                r"(?:手机号码|手机号|联系电话|电话号码|手提电话|手提号码|电话|手提|座机)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>\+?[0-9][0-9\-]{6,15})['\"`]?"
            ),
            placeholder_template="[PHONE_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="zh_bank_card_assignment",
            category="BANK_CARD",
            pattern=re.compile(
                r"(?:银行卡号|银行卡|信用卡号|储蓄卡号|卡号)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>[0-9][0-9 \-]{10,22}[0-9])['\"`]?"
            ),
            placeholder_template="[BANK_CARD_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="zh_user_id_quoted_assignment",
            category="USER_ID",
            pattern=re.compile(
                r"(?:管理员账号|管理员帐号|登录账号|登录帐号|测试账号|测试帐号|银行账号|银行帐号|"
                r"银行户口|银行账户|银行帐户|户口号码|户口号|客户账号|商户号|客户号|员工号|会员号|学生号|"
                r"账号|帐号|户口|账户|帐户|用户名|登录名|户名|工号|学号|微信号)"
                + _ZH_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{2,})(?P=q)"
            ),
            placeholder_template="[USER_ID_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="zh_user_id_assignment",
            category="USER_ID",
            pattern=re.compile(
                r"(?:管理员账号|管理员帐号|登录账号|登录帐号|测试账号|测试帐号|银行账号|银行帐号|"
                r"银行户口|银行账户|银行帐户|户口号码|户口号|客户账号|商户号|客户号|员工号|会员号|学生号|"
                r"账号|帐号|户口|账户|帐户|用户名|登录名|户名|工号|学号|微信号)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>[^\s#;,，。！!？?)'\"`\]\}\r\n]{2,})['\"`]?"
            ),
            placeholder_template="[USER_ID_{index}]",
            target_group="secret",
        ),
        # --- 7. English Shorthand & Full Key-Value Assignments (Unified Quoted, JSON, CLI, ODBC, and Unquoted) ---
        # 7A. Password / Pass / PW / PWD / PIN / OTP / CVV (Quoted with spaces first, then unquoted)
        SanitizeRule(
            name="password_quoted_assignment",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)(?:--|'\"`|\b)(?:[a-z0-9_]*?(?:password|passwd|passphrase|pwd|pass|pw|pin|otp|cvv|cvc))\b['\"`]?"
                + _EN_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{3,})(?P=q)"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="password_shorthand_and_full_assignment",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)(?:--|'\"`|\b)(?:[a-z0-9_]*?(?:password|passwd|passphrase|pwd|pass|pw|pin|otp|cvv|cvc))\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>[^\s#;,)'\"`\]\}\r\n]{3,})['\"`]?"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
        ),
        # 7B. API Key / Secret / Token / AK / SK / PK / TK / Session / Cookie
        SanitizeRule(
            name="api_key_quoted_assignment",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)(?:--|'\"`|\b)(?:[a-z0-9_]*?(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
                r"refresh[_-]?token|client[_-]?secret|private[_-]?key|app[_-]?secret|access[_-]?key|"
                r"session[_-]?id|token|secret|apikey|cookie|jwt)|ak|sk|pk|tk)\b['\"`]?"
                + _EN_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{4,})(?P=q)"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
        ),
        SanitizeRule(
            name="api_key_shorthand_and_full_assignment",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)(?:--|'\"`|\b)(?:[a-z0-9_]*?(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
                r"refresh[_-]?token|client[_-]?secret|private[_-]?key|app[_-]?secret|access[_-]?key|"
                r"session[_-]?id|token|secret|apikey|cookie|jwt)|ak|sk|pk|tk)\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>[^\s#;,)'\"`\]\}\r\n]{4,})['\"`]?"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
        ),
        # 7C. Shorthand IC / NRIC / MyKad / SSN / TIN / SSM Assignments (e.g. ic = 900307145521)
        SanitizeRule(
            name="ic_nric_assignment",
            category="ID_CARD",
            pattern=re.compile(
                r"(?i)['\"`]?\b(?:ic|nric|mykad|id_no|ic_no|ssn|tin|tax_id|ssm|ssm_no)\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>[A-Za-z0-9\-]{6,20})['\"`]?"
            ),
            placeholder_template="[ID_CARD_{index}]",
            target_group="secret",
        ),
        # 7D. Shorthand Handphone / Tel Assignments (e.g. hp = 0123456789)
        SanitizeRule(
            name="hp_tel_assignment",
            category="PHONE",
            pattern=re.compile(
                r"(?i)['\"`]?\b(?:hp|tel|mobile|phone|handphone|whatsapp)\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>\+?[0-9][0-9\-]{6,15})['\"`]?"
            ),
            placeholder_template="[PHONE_{index}]",
            target_group="secret",
        ),
        # 7E. User / Account / ID Shorthand Assignments (e.g. id = abc1234, User Id=sa;, uid = ..., user = ...)
        SanitizeRule(
            name="user_id_quoted_assignment",
            category="USER_ID",
            pattern=re.compile(
                r"(?i)(?:--|'\"`|\b)(?:id|uid|uuid|sid|usr|user|uname|username|login|acct|account|"
                r"user[ _\-]?id|client[ _\-]?id|app[ _\-]?id|account[ _\-]?id|"
                r"[a-z0-9_]*?(?:user_id|userid|client_id|clientid|app_id|appid|account_id|"
                r"tenant_id|merchant_id|customer_id|member_id|secret_id))\b['\"`]?"
                + _EN_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{2,})(?P=q)"
            ),
            placeholder_template="[USER_ID_{index}]",
            target_group="secret",
        ),
        SanitizeRule(
            name="user_id_shorthand_and_full_assignment",
            category="USER_ID",
            pattern=re.compile(
                r"(?i)(?:--|'\"`|\b)(?:id|uid|uuid|sid|usr|user|uname|username|login|acct|account|"
                r"user[ _\-]?id|client[ _\-]?id|app[ _\-]?id|account[ _\-]?id|"
                r"[a-z0-9_]*?(?:user_id|userid|client_id|clientid|app_id|appid|account_id|"
                r"tenant_id|merchant_id|customer_id|member_id|secret_id))\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>[^\s#;,)'\"`\]\}\r\n]{2,})['\"`]?"
            ),
            placeholder_template="[USER_ID_{index}]",
            target_group="secret",
        ),
    ]


BUILTIN_RULES: List[SanitizeRule] = _compile_rules()


SAMPLE_TEST_PAYLOAD = """
# Production Incident Log - Acme Global Technologies Sdn Bhd (Acme Global)
Client: MegaCorp Bank Berhad (Contact: boss@client-a.com, backup: boss@client-a.com, ops@megacorp.com.my)
Project: Project-Hyperion-V2 / Project-Hyperion

DATABASE_URL="postgres://dbadmin:Sup3rS3cretDB!2026@10.52.18.9:5432/hyperion_prod"
REDIS_URL="redis://:R3disP@ssw0rd99@192.168.10.45:6379/0"
WEBHOOK_URL="https://deploy_user:WebhookPass!99@internal.api.org.my/v1/hook"
DB_PASSWORD=UnquotedEnvSecretPass!88
密码-123123
账号=asdasd
pass = abcd1234
pw = 998877
id = abc1234
user = admin_kl_01
password = "MyLocalRootPassword#88"
api_key = "custom_internal_api_token_abcdef123456"

OPENAI_KEY=sk-proj-abc123XYZ789def456GHI012jkl345MNO678
GITHUB_TOKEN=ghp_1234567890abcdefABCDEF1234567890abcd
AWS_KEY=AKIAIOSFODNN7EXAMPLE
GOOGLE_KEY=AIzaSyDa1234567890abcdefABCDEF123456789
SLACK_BOT=xoxb-123456789012-1234567890123-abcdefghijklmnopqrstuvwx
AUTH_HEADER="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"

-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0123456789abcdefABCDEF0123456789abcdefABCDEF
0123456789abcdefABCDEF0123456789abcdefABCDEF==
-----END RSA PRIVATE KEY-----

Upstream Gateway: 8.8.8.8, KL Worker Node: 10.52.18.9, Cyberjaya Backup Node: 172.20.0.15
Server MAC: 00:1A:2B:3C:4D:5E, IPv6: 2001:0db8:85a3:0000:0000:8a2e:0370:7334
On-call Engineer Phone (MY): +60 12-345 6789, Backup (MY): 011-2345 6789
MY NRIC: 900307-14-5521, Passport: A12345678
"""
