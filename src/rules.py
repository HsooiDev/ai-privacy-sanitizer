"""Built-in high-strength regex rule definitions, validators, metadata, and sample payloads."""

from dataclasses import dataclass
import math
from typing import Callable, List, Optional, Pattern, Tuple
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


def cn_id_valid(id_str: str) -> bool:
    """Validate Mainland China 18-digit Resident ID Card (real calendar date + GB 11643-1999 mod-11 checksum)."""
    raw = str(id_str or "").strip().upper()
    if not re.fullmatch(r"[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dX]", raw):
        return False
    year = int(raw[6:10])
    month = int(raw[10:12])
    day = int(raw[12:14])
    is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    max_days = {
        1: 31,
        2: 29 if is_leap else 28,
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
    if month not in max_days or not (1 <= day <= max_days[month]):
        return False
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    check_map = "10X98765432"
    checksum = sum(int(raw[i]) * weights[i] for i in range(17)) % 11
    return raw[17] == check_map[checksum]


@dataclass(frozen=True)
class SanitizeRule:
    """Represents a single regex sanitization rule with optional metadata and fast prefilter hints."""

    name: str
    category: str
    pattern: Pattern[str]
    placeholder_template: str = "[{category}_{index}]"
    target_group: str = ""  # If set, only sanitize this named group within the match
    validator: Optional[Callable[[str], bool]] = None
    enabled_by_default: bool = True
    label_zh: str = ""
    label_en: str = ""
    example: str = ""
    group: str = "other"  # credentials | network | pii | kv
    presets: Tuple[str, ...] = ("dev", "hr")
    # Fast C-level prefilters: if non-empty, at least one lowercase token must exist in text.
    fast_tokens: Tuple[str, ...] = ()
    require_non_ascii: bool = False
    require_quote: bool = False


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

# Fast zero-backtracking key boundary: either preceded by separator/word-boundary/underscore,
# OR preceded by explicit camelCase prefixes (prevents compass=, bypass=, spin= false positives
# while matching DB_PASSWORD, my_api_key, dbPass, apiKey, clientSecret in O(n) time).
_EN_KEY_BOUNDARY = (
    r"(?:(?<=^)|(?<=[\s'\"`(\[{,;_\-\.])|"
    r"(?<=\b(?:db|app|api|auth|user|usr|root|admin|client|access|secret|private|refresh|"
    r"session|jwt|mysql|pg|postgres|redis|mongo|smtp|ftp|ssh|aws|gcp|azure|login|"
    r"master|service|webhook|proxy|mail|email|token|key|site|store|server|host|acct|"
    r"account|tenant|merchant|customer|member)))"
)
# Notice Python re requires fixed-width lookbehind, so we match optional camelCase prefixes directly
# ONLY after a true word/delimiter boundary (zero [a-z0-9_]+ backtracking!).
_EN_CAMEL_PREFIX = (
    r"(?:db|app|api|auth|user|usr|root|admin|client|access|secret|private|refresh|"
    r"session|jwt|mysql|pg|postgres|redis|mongo|smtp|ftp|ssh|aws|gcp|azure|login|"
    r"master|service|webhook|proxy|mail|email|token|key|site|store|server|host|acct|"
    r"account|tenant|merchant|customer|member)"
)
_EN_DELIM_START = r"(?:(?<=^)|(?<=[\s'\"`(\[{,;_\-\.?&]))"
_EN_WORD_START = r"(?:(?<=^)|(?<=[\s'\"`(\[{,;\-\.?&]))"


def _compile_rules() -> List[SanitizeRule]:
    """Compile and return ordered regex sanitization rules."""
    return [
        # --- 0. Multi-line PEM / SSH / PGP Private Key Blocks ---
        SanitizeRule(
            name="pem_ssh_private_key",
            category="PRIVATE_KEY",
            pattern=re.compile(
                r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----"
                r"[\s\S]{1,32768}?"
                r"-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----"
            ),
            placeholder_template="<PRIVATE_KEY_{index}>",
            label_zh="SSH / PEM / PGP 私钥证书块",
            label_en="SSH / PEM / PGP Private Key Blocks",
            example="-----BEGIN RSA / PGP PRIVATE KEY-----",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("-----begin ",),
        ),
        # --- 1. Database, URL Basic Auth & CLI Auth Connection Strings ---
        SanitizeRule(
            name="db_connection_uri_password",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis(?:s)?|amqp|mssql)"
                r"://(?:[^:/@\s'\"`]*:)?(?P<secret>[^\s'\"`/]+)@(?=[^\s@/'\"`,;]+)"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
            label_zh="数据库连接串密码（支持含 @ 密码）",
            label_en="Database URI Password (supports '@' in password)",
            example="postgres://admin:p@ss@10.0.0.5:5432/db",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("://",),
        ),
        SanitizeRule(
            name="url_basic_auth_password",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)\b(?:https?|ftp)://[^:/@\s'\"`]+:(?P<secret>[^\s'\"`/]+)@(?=[^\s@/'\"`,;]+)"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
            label_zh="HTTP / FTP Basic Auth URL 密码",
            label_en="HTTP / FTP Basic Auth URL Password",
            example="https://deploy:Pass@word@api.internal/hook",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("://",),
        ),
        SanitizeRule(
            name="cli_curl_basic_auth",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)(?<!\S)(?:-u|--user)\s+['\"`]?[^:\s'\"`]+:(?P<secret>[^\s'\"`]+)['\"`]?"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
            label_zh="curl -u / --user 命令行密码",
            label_en="curl -u / --user CLI Password",
            example="curl -u admin:SecretPass https://...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("-u", "--user"),
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
            label_zh="Slack / Discord / 飞书 / 钉钉 / 企微 Webhook 令牌",
            label_en="Slack / Discord / Feishu / DingTalk / WeCom Webhook Token",
            example="hooks.slack.com/services/T00/B00/XXXX",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("webhooks/", "hooks.slack.com", "open.feishu.cn", "oapi.dingtalk.com", "qyapi.weixin.qq.com"),
        ),
        # --- 2. Explicit Signature API Keys & Cloud Tokens ---
        SanitizeRule(
            name="jwt_token",
            category="API_KEY",
            pattern=re.compile(
                r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"
            ),
            placeholder_template="<API_KEY_{index}>",
            label_zh="JWT 身份令牌",
            label_en="JSON Web Token (JWT)",
            example="eyJhbGciOi...eyJzdWIi...SflKxw...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("eyj",),
        ),
        SanitizeRule(
            name="openai_anthropic_sk_key",
            category="API_KEY",
            pattern=re.compile(
                r"\bsk-(?:proj-|ant-api\d{2}-|ant-|or-v\d+-|live-|test-)?[A-Za-z0-9_\-]{16,}\b"
            ),
            placeholder_template="<API_KEY_{index}>",
            label_zh="OpenAI / Anthropic / OpenRouter / DeepSeek 密钥",
            label_en="OpenAI / Anthropic / OpenRouter / DeepSeek API Key",
            example="sk-proj-abc123...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("sk-",),
        ),
        SanitizeRule(
            name="stripe_live_test_key",
            category="API_KEY",
            pattern=re.compile(r"\b(?:(?:sk|rk|pk)_(?:live|test)_[0-9a-zA-Z]{16,}|whsec_[0-9a-zA-Z]{24,})\b"),
            placeholder_template="<API_KEY_{index}>",
            label_zh="Stripe 支付与 Webhook 密钥",
            label_en="Stripe Live / Test / Webhook Key",
            example="sk_live_51Nz0123... / whsec_...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("_live_", "_test_", "whsec_"),
        ),
        SanitizeRule(
            name="github_token",
            category="API_KEY",
            pattern=re.compile(
                r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                r"glpat-[A-Za-z0-9_\-]{20,}|gldt-[A-Za-z0-9_\-]{20,}|glrt-[A-Za-z0-9_\-]{20,})\b"
            ),
            placeholder_template="<API_KEY_{index}>",
            label_zh="GitHub / GitLab 访问令牌",
            label_en="GitHub / GitLab Personal & Runner Token",
            example="ghp_1234..., glpat-...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_", "glpat-", "gldt-", "glrt-"),
        ),
        SanitizeRule(
            name="groq_hf_npm_pypi_key",
            category="API_KEY",
            pattern=re.compile(
                r"\b(?:gsk_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|npm_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_\-]{24,})\b"
            ),
            placeholder_template="<API_KEY_{index}>",
            label_zh="Groq / HuggingFace / npm / PyPI 密钥",
            label_en="Groq / HuggingFace / npm / PyPI Token",
            example="gsk_..., hf_..., npm_..., pypi-...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("gsk_", "hf_", "npm_", "pypi-"),
        ),
        SanitizeRule(
            name="aws_access_key",
            category="API_KEY",
            pattern=re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
            placeholder_template="<API_KEY_{index}>",
            label_zh="AWS Access Key ID",
            label_en="AWS Access Key ID",
            example="AKIAIOSFODNN7EXAMPLE",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("akia", "asia"),
        ),
        SanitizeRule(
            name="google_api_key",
            category="API_KEY",
            pattern=re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
            placeholder_template="<API_KEY_{index}>",
            label_zh="Google / Gemini / Firebase API Key",
            label_en="Google / Gemini / Firebase API Key",
            example="AIzaSyDa1234...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("aiza",),
        ),
        SanitizeRule(
            name="slack_token",
            category="API_KEY",
            pattern=re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b"),
            placeholder_template="<API_KEY_{index}>",
            label_zh="Slack Bot / User Token",
            label_en="Slack Bot / User Token",
            example="xoxb-123456...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("xoxb-", "xoxa-", "xoxp-", "xoxr-", "xoxs-"),
        ),
        SanitizeRule(
            name="telegram_bot_token",
            category="API_KEY",
            pattern=re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{32,35}\b"),
            placeholder_template="<API_KEY_{index}>",
            label_zh="Telegram Bot 令牌",
            label_en="Telegram Bot Token",
            example="123456789:AAHdqT...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=(":aa",),
        ),
        SanitizeRule(
            name="sendgrid_api_key",
            category="API_KEY",
            pattern=re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"),
            placeholder_template="<API_KEY_{index}>",
            label_zh="SendGrid 邮件密钥",
            label_en="SendGrid API Key",
            example="SG.xxxx.yyyy",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("sg.",),
        ),
        SanitizeRule(
            name="cloudflare_or_do_or_linear_or_supabase_token",
            category="API_KEY",
            pattern=re.compile(
                r"\b(?:dop_v1_[a-f0-9]{64}|lin_api_[A-Za-z0-9]{32,}|sbp_[a-f0-9]{40}|"
                r"PMAK-[a-f0-9]{24}-[a-f0-9]{34}|shpat_[a-fA-F0-9]{32})\b"
            ),
            placeholder_template="<API_KEY_{index}>",
            label_zh="DigitalOcean / Linear / Supabase / Postman / Shopify 令牌",
            label_en="DigitalOcean / Linear / Supabase / Postman / Shopify Token",
            example="dop_v1_..., lin_api_..., sbp_..., shpat_...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("dop_v1_", "lin_api_", "sbp_", "pmak-", "shpat_"),
        ),
        SanitizeRule(
            name="cloudflare_vercel_databricks_supabase_token",
            category="API_KEY",
            pattern=re.compile(
                r"\b(?:(?:cfut|cfat|cfrt)_[A-Za-z0-9_\-]{28,}|"
                r"v1\.0-[A-Fa-f0-9]{24}-[A-Fa-f0-9]{64,}|"
                r"sb_secret_[A-Za-z0-9_\-]{20,}|"
                r"vercel_(?:pat|tok|secret)_[A-Za-z0-9_\-]{20,}|"
                r"vc[pk]_[A-Za-z0-9_\-]{24,}|"
                r"dapi[0-9a-fA-F]{32}(?:-\d)?)\b"
            ),
            placeholder_template="<API_KEY_{index}>",
            label_zh="Cloudflare / Vercel / Databricks / Supabase 平台令牌",
            label_en="Cloudflare / Vercel / Databricks / Supabase Platform Token",
            example="cfut_..., sb_secret_..., vercel_pat_..., dapi...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("cfut_", "cfat_", "cfrt_", "v1.0-", "sb_secret_", "vercel_", "vcp_", "vck_", "dapi"),
        ),
        SanitizeRule(
            name="azure_connection_string_secret",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)\b(?:AccountKey|SharedAccessKey|SharedAccessSignature)=(?P<secret>[^\s;'\"`\]\}]{16,})"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="Azure 存储 / 服务总线连接串密钥",
            label_en="Azure Connection String AccountKey / SharedAccessKey",
            example="AccountKey=AbCdEf...==;EndpointSuffix=...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("accountkey=", "sharedaccesskey=", "sharedaccesssignature="),
        ),
        SanitizeRule(
            name="azure_sas_url",
            category="API_KEY",
            pattern=re.compile(r"(?i)[?&]sig=(?P<secret>[A-Za-z0-9%+/=]{24,})"),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="Azure SAS URL 签名参数",
            label_en="Azure SAS URL Signature",
            example="?sv=2022-11-02&sig=AbCdEf...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("sig=",),
        ),
        SanitizeRule(
            name="http_basic_auth",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)\bAuthorization\s*:\s*Basic\s+(?P<secret>[A-Za-z0-9+/=]{8,})"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="HTTP Authorization Basic 凭证头",
            label_en="HTTP Authorization Basic Credential",
            example="Authorization: Basic dXNlcjpwYXNz",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("basic",),
        ),
        SanitizeRule(
            name="bearer_token",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)\bBearer\s+(?P<secret>[A-Za-z0-9_\-\.~+/]{12,}=*)"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="HTTP Bearer Token 认证头",
            label_en="HTTP Bearer Authorization Token",
            example="Bearer eyJhbG...",
            group="credentials",
            presets=("dev", "hr", "strict"),
            fast_tokens=("bearer",),
        ),
        # --- 3. Email Addresses ---
        SanitizeRule(
            name="email_address",
            category="EMAIL",
            pattern=re.compile(
                r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
            ),
            placeholder_template="[EMAIL_{index}]",
            label_zh="电子邮箱地址",
            label_en="Email Address",
            example="boss@client-a.com",
            group="pii",
            presets=("dev", "hr"),
            fast_tokens=("@",),
        ),
        # --- 4. Network & Infrastructure ---
        SanitizeRule(
            name="mac_address",
            category="MAC_ADDR",
            pattern=re.compile(
                r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"
            ),
            placeholder_template="[MAC_{index}]",
            label_zh="网卡 MAC 地址",
            label_en="MAC Address",
            example="00:1A:2B:3C:4D:5E",
            group="network",
            presets=("dev", "hr"),
            fast_tokens=(":", "-"),
        ),
        SanitizeRule(
            name="ipv6_address",
            category="IPV6",
            pattern=re.compile(
                r"(?<![0-9A-Fa-f:])(?:"
                r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|"
                r"fe80:(?::[0-9A-Fa-f]{1,4}){0,4}%[0-9a-zA-Z]{1,}|"
                r"::(?:ffff(?::0{1,4})?:)?(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|"
                r"(?:[0-9A-Fa-f]{1,4}:){1,6}:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,5}|"
                r"(?:[0-9A-Fa-f]{1,4}:){1,7}:|"
                r"::(?:[0-9A-Fa-f]{1,4}:){0,5}[0-9A-Fa-f]{1,4}"
                r")(?![0-9A-Fa-f:])"
            ),
            placeholder_template="[IPV6_{index}]",
            label_zh="IPv6 地址（含压缩格式）",
            label_en="IPv6 Address (Full & Compressed)",
            example="2001:db8::8a2e:370:7334",
            group="network",
            presets=("dev", "hr"),
            fast_tokens=(":",),
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
            label_zh="内网 IPv4 地址 (10.x / 172.16-31.x / 192.168.x)",
            label_en="Private IPv4 Address (RFC 1918)",
            example="10.52.18.9 / 192.168.10.45",
            group="network",
            presets=("dev", "hr"),
            fast_tokens=("10.", "172.", "192.168."),
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
                r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
                r"(?![\d.])"
            ),
            placeholder_template="[PUBLIC_IP_{index}]",
            label_zh="公网 IPv4 地址（含 .0 网段）",
            label_en="Public IPv4 Address",
            example="8.8.8.8 / 45.33.32.0",
            group="network",
            presets=("dev", "hr"),
            fast_tokens=(".",),
        ),
        # --- 5. Personal Identifiable Information (PII - Malaysia Prioritized) & User Paths ---
        SanitizeRule(
            name="user_file_path",
            category="USER_PATH",
            pattern=re.compile(
                r"(?i)(?:[A-Za-z]:[\\/]+Users[\\/]+|(?<![A-Za-z0-9_])/Users/|(?<![A-Za-z0-9_])/home/)"
                r"(?!(?:Public|Default(?:\s+User)?|All\s+Users|Shared|root|ubuntu|admin|ec2-user|vagrant|docker|nobody|www-data|postgres|git|runner)(?:[\\/\s'\"`,;:\)\]\}]|$))"
                r"(?P<secret>[^\s\\/:'\"`<>|*?\[\]{}(),;]{2,64})(?=[\\/\s'\"`,;:\)\]\}]|$)"
            ),
            placeholder_template="[USER_PATH_{index}]",
            target_group="secret",
            label_zh="本机文件路径用户名（支持无尾斜杠与中文名）",
            label_en="OS File Path Username (Win / macOS / Linux)",
            example=r"C:\Users\alice_dev\... | /Users/bob",
            group="network",
            presets=("dev", "hr"),
            fast_tokens=("users\\", "users/", "/home/"),
        ),
        SanitizeRule(
            name="my_nric",
            category="ID_CARD",
            pattern=re.compile(r"\b\d{6}-\d{2}-\d{4}\b"),
            placeholder_template="[ID_CARD_{index}]",
            validator=my_nric_valid,
            label_zh="马来西亚身份证 (MyKad NRIC + 州属校验)",
            label_en="Malaysian MyKad NRIC (Date + PB Code)",
            example="900307-14-5521",
            group="pii",
            presets=("dev", "hr"),
            fast_tokens=("-",),
        ),
        SanitizeRule(
            name="cn_id_card",
            category="ID_CARD",
            pattern=re.compile(
                r"\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"
            ),
            placeholder_template="[ID_CARD_{index}]",
            validator=cn_id_valid,
            label_zh="中国大陆 18 位身份证（GB 11643 校验码）",
            label_en="Mainland China 18-Digit ID (Checksum Validated)",
            example="11010519491231002X",
            group="pii",
            presets=("dev", "hr"),
            fast_tokens=("18", "19", "20"),
        ),
        SanitizeRule(
            name="bank_card",
            category="BANK_CARD",
            pattern=re.compile(
                r"\b(?:"
                r"(?:4\d{3}|5[1-5]\d{2}|222[1-9]|22[3-9]\d|2[3-6]\d{2}|27[01]\d|2720)(?:[ -]?\d{4}){3}|"
                r"62\d{2}(?:[ -]?\d{4}){3}(?:[ -]?\d{1,3})?|"
                r"3[47]\d{2}[ -]?\d{6}[ -]?\d{5}"
                r")\b"
            ),
            placeholder_template="[BANK_CARD_{index}]",
            validator=luhn_checksum_valid,
            label_zh="银行卡 / 信用卡号（Visa/MC/Amex/银联 + Luhn 校验）",
            label_en="Bank / Credit Card (Visa/MC/Amex/UnionPay + Luhn)",
            example="4111-1111-1111-1111",
            group="pii",
            presets=("dev", "hr"),
            fast_tokens=("4", "5", "62", "34", "37", "22", "23", "24", "25", "26", "27"),
        ),
        SanitizeRule(
            name="passport_number",
            category="PASSPORT",
            pattern=re.compile(r"\b(?:[A-HK-NP-Z]\d{8}|[EGDSP]\d{8})\b"),
            placeholder_template="[PASSPORT_{index}]",
            label_zh="护照号码（大马 / 中国 / 常见国际格式）",
            label_en="Passport Number",
            example="A12345678 / E12345678",
            group="pii",
            presets=("dev", "hr"),
            fast_tokens=("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"),
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
            label_zh="手机与电话号码（马来西亚 +60 / 中国 +86 / 国际）",
            label_en="Phone Number (MY +60 / CN +86 / International)",
            example="+60 12-345 6789 / 011-2345 6789",
            group="pii",
            presets=("dev", "hr"),
            fast_tokens=("+", "01", "60", "86", "13", "14", "15", "16", "17", "18", "19"),
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
            label_zh="中文引号密码 / 口令 / 验证码赋值",
            label_en="Chinese Quoted Password / PIN Assignment",
            example='密码 = "我的 密码 888"',
            group="kv",
            presets=("dev", "hr", "strict"),
            require_non_ascii=True,
            fast_tokens=("密码", "口令", "安全码", "验证码", "动态码", "校验码", "pin码"),
        ),
        SanitizeRule(
            name="zh_password_assignment",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)(?:数据库密码|登录密码|管理员密码|管理密码|初始密码|默认密码|支付密码|交易密码|"
                r"无线密码|新密码|旧密码|原密码|密码|口令|安全码|验证码|动态码|校验码|PIN码)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>[^\s#;,&，。！!？?)'\"`\]\}\r\n]{3,})['\"`]?"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
            label_zh="中文密码 / 口令 / 验证码赋值",
            label_en="Chinese Password / PIN Assignment",
            example="密码-123123 / 登录密码 是 xxx",
            group="kv",
            presets=("dev", "hr", "strict"),
            require_non_ascii=True,
            fast_tokens=("密码", "口令", "安全码", "验证码", "动态码", "校验码", "pin码"),
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
            label_zh="中文引号密钥 / 令牌赋值",
            label_en="Chinese Quoted API Key / Token Assignment",
            example='密钥 = "my_secret_key"',
            group="kv",
            presets=("dev", "hr", "strict"),
            require_non_ascii=True,
            fast_tokens=("密钥", "秘钥", "私钥", "令牌"),
        ),
        SanitizeRule(
            name="zh_api_key_assignment",
            category="API_KEY",
            pattern=re.compile(
                r"(?:访问密钥|私有密钥|接口密钥|应用密钥|签名密钥|密钥|秘钥|私钥|令牌)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>[^\s#;,&，。！!？?)'\"`\]\}\r\n]{4,})['\"`]?"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="中文密钥 / 令牌赋值",
            label_en="Chinese API Key / Token Assignment",
            example="密钥=zh_secret_token_9988",
            group="kv",
            presets=("dev", "hr", "strict"),
            require_non_ascii=True,
            fast_tokens=("密钥", "秘钥", "私钥", "令牌"),
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
            label_zh="中文身份证 / 证件号 / 税号赋值",
            label_en="Chinese ID / Tax Number Assignment",
            example="身份证-900307145521",
            group="kv",
            presets=("dev", "hr"),
            require_non_ascii=True,
            fast_tokens=("身份证", "证件号", "大马卡", "护照号", "税号", "社保号"),
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
            label_zh="中文手机号 / 电话赋值",
            label_en="Chinese Phone Assignment",
            example="手机号=0123456789",
            group="kv",
            presets=("dev", "hr"),
            require_non_ascii=True,
            fast_tokens=("手机", "电话", "手提", "座机"),
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
            label_zh="中文银行卡号赋值",
            label_en="Chinese Bank Card Assignment",
            example="银行卡号：6222021234567890",
            group="kv",
            presets=("dev", "hr"),
            require_non_ascii=True,
            fast_tokens=("银行卡", "信用卡号", "储蓄卡号", "卡号"),
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
            label_zh="中文引号账号 / 户口 / 用户名赋值",
            label_en="Chinese Quoted Account / Username Assignment",
            example='账号 = "john doe kl"',
            group="kv",
            presets=("dev", "hr"),
            require_non_ascii=True,
            fast_tokens=("账号", "帐号", "户口", "账户", "帐户", "用户名", "登录名", "户名", "工号", "学号", "微信号", "商户号", "客户号", "员工号", "会员号", "学生号"),
        ),
        SanitizeRule(
            name="zh_user_id_assignment",
            category="USER_ID",
            pattern=re.compile(
                r"(?:管理员账号|管理员帐号|登录账号|登录帐号|测试账号|测试帐号|银行账号|银行帐号|"
                r"银行户口|银行账户|银行帐户|户口号码|户口号|客户账号|商户号|客户号|员工号|会员号|学生号|"
                r"账号|帐号|户口|账户|帐户|用户名|登录名|户名|工号|学号|微信号)"
                + _ZH_SEP
                + r"['\"`]?(?P<secret>[^\s#;,&，。！!？?)'\"`\]\}\r\n]{2,})['\"`]?"
            ),
            placeholder_template="[USER_ID_{index}]",
            target_group="secret",
            label_zh="中文账号 / 户口 / 用户名赋值",
            label_en="Chinese Account / Username Assignment",
            example="账号=asdasd / 户口=user_acc_7788",
            group="kv",
            presets=("dev", "hr"),
            require_non_ascii=True,
            fast_tokens=("账号", "帐号", "户口", "账户", "帐户", "用户名", "登录名", "户名", "工号", "学号", "微信号", "商户号", "客户号", "员工号", "会员号", "学生号"),
        ),
        # --- 7. English Shorthand & Full Key-Value Assignments (Zero-Backtracking Prefix Guard) ---
        # 7A. Password / Pass / PW / PWD / PIN / OTP / CVV
        SanitizeRule(
            name="password_quoted_assignment",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)" + _EN_DELIM_START + r"(?:" + _EN_CAMEL_PREFIX + r")?(?:password|passwd|passphrase|pwd|pass|pw|pin|otp|cvv|cvc)\b['\"`]?"
                + _EN_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{3,})(?P=q)"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
            label_zh="英文引号密码赋值 (password / pwd / pass)",
            label_en="English Quoted Password Assignment",
            example='password = "My Local Pass 2026"',
            group="kv",
            presets=("dev", "hr", "strict"),
            fast_tokens=("pass", "pwd", "pw", "pin", "otp", "cvv", "cvc"),
            require_quote=True,
        ),
        SanitizeRule(
            name="password_shorthand_and_full_assignment",
            category="DB_PASS",
            pattern=re.compile(
                r"(?i)" + _EN_DELIM_START + r"(?:" + _EN_CAMEL_PREFIX + r")?(?:password|passwd|passphrase|pwd|pass|pw|pin|otp|cvv|cvc)\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>[^\s#;,&)'\"`\]\}\r\n]{3,})['\"`]?"
            ),
            placeholder_template="[DB_PASS_{index}]",
            target_group="secret",
            label_zh="英文密码 / 简写赋值（防 compass/bypass 误报）",
            label_en="English Password / Shorthand Assignment",
            example="DB_PASSWORD=xxx / pass = abcd1234",
            group="kv",
            presets=("dev", "hr", "strict"),
            fast_tokens=("pass", "pwd", "pw", "pin", "otp", "cvv", "cvc"),
        ),
        # 7B. API Key / Secret / Token / AK / SK / PK / TK / Session / Cookie
        SanitizeRule(
            name="api_key_quoted_assignment",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)" + _EN_DELIM_START + r"(?:(?:" + _EN_CAMEL_PREFIX + r")?(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
                r"refresh[_-]?token|client[_-]?secret|private[_-]?key|app[_-]?secret|access[_-]?key|"
                r"session[_-]?id|token|secret|apikey|cookie|jwt)|ak|sk|pk|tk)\b['\"`]?"
                + _EN_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{4,})(?P=q)"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="英文引号密钥 / Token 赋值",
            label_en="English Quoted API Key / Token Assignment",
            example='api_key = "custom_token_123456"',
            group="kv",
            presets=("dev", "hr", "strict"),
            fast_tokens=("key", "secret", "token", "session", "cookie", "jwt", "ak", "sk", "pk", "tk"),
            require_quote=True,
        ),
        SanitizeRule(
            name="api_key_shorthand_and_full_assignment",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)" + _EN_DELIM_START + r"(?:(?:" + _EN_CAMEL_PREFIX + r")?(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
                r"refresh[_-]?token|client[_-]?secret|private[_-]?key|app[_-]?secret|access[_-]?key|"
                r"session[_-]?id|token|secret|apikey|cookie|jwt)|ak|sk|pk|tk)\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>[^\s#;,&)'\"`\]\}\r\n]{4,})['\"`]?"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="英文密钥 / Token / URL 参数赋值",
            label_en="English API Key / Token / Query Assignment",
            example="CUSTOM_API_KEY=xxx | ?api_key=xxx&page=2",
            group="kv",
            presets=("dev", "hr", "strict"),
            fast_tokens=("key", "secret", "token", "session", "cookie", "jwt", "ak", "sk", "pk", "tk"),
        ),
        # 7B-2. Structured .env / JSON / YAML / URL Query Platform Secret Keys
        SanitizeRule(
            name="structured_config_quoted_secret",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)" + _EN_DELIM_START + r"(?:"
                r"(?:service[_-]?role|anon|signing|encryption|decrypt|master|hmac|webhook|"
                r"cloudflare|supabase|vercel|databricks|telegram|resend|twilio|stripe|"
                r"openai|anthropic|gemini|github|gitlab|aws|gcp|azure)[_-]?"
                r"(?:api[_-]?|auth[_-]?|access[_-]?|bot[_-]?|pat[_-]?|client[_-]?|private[_-]?|admin[_-]?)?"
                r"(?:key|secret|token|pass(?:word)?|pwd|dsn|cred(?:ential)?s?)|"
                r"x[-_]api[-_]key|connection[_-]?string|conn[_-]?str|auth[_-]?secret|"
                r"signing[_-]?secret|webhook[_-]?secret|api[_-]?secret|signature"
                r")\b['\"`]?"
                + _EN_SEP
                + r"(?P<q>['\"`])(?![\$\{])(?P<secret>[^'\"`\r\n]{6,})(?P=q)"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="结构化配置引号密钥 (.env / JSON / YAML)",
            label_en="Structured Config Quoted Secret (.env / JSON / YAML)",
            example='signing_secret: "wh_sec_..."',
            group="kv",
            presets=("dev", "hr", "strict"),
            fast_tokens=("key", "secret", "token", "pass", "pwd", "dsn", "cred", "conn", "signature"),
            require_quote=True,
        ),
        SanitizeRule(
            name="structured_config_unquoted_secret",
            category="API_KEY",
            pattern=re.compile(
                r"(?i)" + _EN_DELIM_START + r"(?:"
                r"(?:service[_-]?role|anon|signing|encryption|decrypt|master|hmac|webhook|"
                r"cloudflare|supabase|vercel|databricks|telegram|resend|twilio|stripe|"
                r"openai|anthropic|gemini|github|gitlab|aws|gcp|azure)[_-]?"
                r"(?:api[_-]?|auth[_-]?|access[_-]?|bot[_-]?|pat[_-]?|client[_-]?|private[_-]?|admin[_-]?)?"
                r"(?:key|secret|token|pass(?:word)?|pwd|dsn|cred(?:ential)?s?)|"
                r"x[-_]api[-_]key|connection[_-]?string|conn[_-]?str|auth[_-]?secret|"
                r"signing[_-]?secret|webhook[_-]?secret|api[_-]?secret|signature"
                r")\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>[^\s#;,&)'\"`\]\}\r\n]{6,})['\"`]?"
            ),
            placeholder_template="<API_KEY_{index}>",
            target_group="secret",
            label_zh="结构化配置无引号密钥 (.env / YAML / URL)",
            label_en="Structured Config Secret (.env / YAML / URL Query)",
            example="SUPABASE_SERVICE_ROLE_KEY=eyJ... | ?signature=...",
            group="kv",
            presets=("dev", "hr", "strict"),
            fast_tokens=("key", "secret", "token", "pass", "pwd", "dsn", "cred", "conn", "signature"),
        ),
        # 7C. Shorthand IC / NRIC / MyKad / SSN / TIN / SSM Assignments
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
            label_zh="英文证件号 / IC / SSN / SSM 简写赋值",
            label_en="English IC / NRIC / SSN / Tax ID Assignment",
            example="ic = 900307145521",
            group="kv",
            presets=("dev", "hr"),
            fast_tokens=("ic", "nric", "mykad", "id_no", "ssn", "tin", "tax_id", "ssm"),
        ),
        # 7D. Shorthand Handphone / Tel Assignments
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
            label_zh="英文电话 / 手机简写赋值 (hp / tel / mobile)",
            label_en="English Phone / HP / Mobile Assignment",
            example="hp = 0123456789",
            group="kv",
            presets=("dev", "hr"),
            fast_tokens=("hp", "tel", "mobile", "phone", "whatsapp"),
        ),
        # 7E. User / Account / ID Shorthand Assignments
        SanitizeRule(
            name="user_id_quoted_assignment",
            category="USER_ID",
            pattern=re.compile(
                r"(?i)(?:"
                + _EN_WORD_START
                + r"(?:id|uid|uuid|sid|usr|user|uname|username|login|acct|account|"
                r"user[ _\-]?id|client[ _\-]?id|app[ _\-]?id|account[ _\-]?id)|"
                + _EN_DELIM_START
                + r"(?:" + _EN_CAMEL_PREFIX + r")?(?:user_id|userid|client_id|clientid|app_id|appid|account_id|"
                r"tenant_id|merchant_id|customer_id|member_id|secret_id))\b['\"`]?"
                + _EN_SEP
                + r"(?P<q>['\"`])(?P<secret>[^'\"`\r\n]{2,})(?P=q)"
            ),
            placeholder_template="[USER_ID_{index}]",
            target_group="secret",
            label_zh="英文引号账号 / 用户 ID 赋值",
            label_en="English Quoted User / Account ID Assignment",
            example='username = "admin_kl_01"',
            group="kv",
            presets=("dev", "hr"),
            fast_tokens=("id", "uid", "usr", "user", "uname", "login", "acct", "account"),
            require_quote=True,
        ),
        SanitizeRule(
            name="user_id_shorthand_and_full_assignment",
            category="USER_ID",
            pattern=re.compile(
                r"(?i)(?:"
                + _EN_WORD_START
                + r"(?:id|uid|uuid|sid|usr|user|uname|username|login|acct|account|"
                r"user[ _\-]?id|client[ _\-]?id|app[ _\-]?id|account[ _\-]?id)|"
                + _EN_DELIM_START
                + r"(?:" + _EN_CAMEL_PREFIX + r")?(?:user_id|userid|client_id|clientid|app_id|appid|account_id|"
                r"tenant_id|merchant_id|customer_id|member_id|secret_id))\b['\"`]?"
                + _EN_SEP
                + r"['\"`]?"
                + _NON_SECRET_LOOKAHEAD
                + r"(?P<secret>[^\s#;,&)'\"`\]\}\r\n]{2,})['\"`]?"
            ),
            placeholder_template="[USER_ID_{index}]",
            target_group="secret",
            label_zh="英文账号 / ID 简写赋值（排查 SQL 时可关闭）",
            label_en="English User / Account / ID Shorthand Assignment",
            example="User Id=sa_admin / id = abc1234",
            group="kv",
            presets=("hr",),
            fast_tokens=("id", "uid", "usr", "user", "uname", "login", "acct", "account"),
        ),
    ]


BUILTIN_RULES: List[SanitizeRule] = _compile_rules()

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]{32,128}$")


def shannon_entropy(value: str) -> float:
    """Compute Shannon entropy in bits per character."""
    if not value:
        return 0.0
    length = len(value)
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def is_high_entropy_secret(value: str) -> bool:
    """Return True when an assignment RHS token looks like a random high-entropy secret."""
    if not value or not (20 <= len(value) <= 128):
        return False
    if any(ch.isspace() for ch in value):
        return False
    if "://" in value or "/" in value or "\\" in value:
        return False
    if _UUID_RE.fullmatch(value):
        return False
    if len(set(value)) < 8:
        return False
    if _HEX_RE.fullmatch(value):
        return shannon_entropy(value) >= 3.0
    has_alpha = any(ch.isascii() and ch.isalpha() for ch in value)
    has_digit = any(ch.isascii() and ch.isdigit() for ch in value)
    if not (has_alpha and has_digit):
        return False
    return shannon_entropy(value) >= 3.6


HIGH_ENTROPY_ASSIGNMENT_RULE = SanitizeRule(
    name="high_entropy_assignment_secret",
    category="HIGH_ENTROPY",
    pattern=re.compile(
        r"(?i)(?:^|(?<=[\s'\"`(\[{,;?&]))"
        r"(?!(?:commit|sha|sha1|sha256|md5|hash|etag|version|uuid|guid|"
        r"trace[_-]?id|request[_-]?id|correlation[_-]?id|span[_-]?id|url|uri|path|href|src|"
        r"checksum|digest|integrity|class|type|id|name)\b['\"`]?[ \t]*[:=])"
        r"[A-Za-z_][A-Za-z0-9_.\-]{1,63}['\"`]?[ \t]*[:=][ \t]*['\"`]?"
        r"(?P<secret>[A-Za-z0-9+/=_\-]{20,128})['\"`]?(?=[\s#;,&)'\"`\]\}\r\n]|$)"
    ),
    placeholder_template="<HIGH_ENTROPY_{index}>",
    target_group="secret",
    validator=is_high_entropy_secret,
    enabled_by_default=False,
    label_zh="高信息熵随机密钥兜底检测（赋值语句右侧）",
    label_en="High-Entropy Random Secret Fallback (Assignment RHS)",
    example="custom_opaque_cred = xK9mPq2vLz8nRt4wYb7cJd5h",
    group="credentials",
    presets=(),
    fast_tokens=("=", ":"),
)

RULE_PRESETS = {
    "dev": [r.name for r in BUILTIN_RULES if "dev" in r.presets],
    "hr": [r.name for r in BUILTIN_RULES if "hr" in r.presets and r.name not in ("mac_address", "ipv6_address")],
    "strict": [r.name for r in BUILTIN_RULES],
}


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
