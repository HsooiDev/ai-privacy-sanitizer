/* Sanitizer Paste Guard — 100% RAM-Only JS Sanitization & Fuzzy Restoration Engine (Zero Network, Zero Storage) */
(function (globalScope) {
  "use strict";

  var MAX_CHARS = 1500000;
  var VALID_MY_PB_CODES = {
    1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1, 10: 1, 11: 1, 12: 1, 13: 1, 14: 1, 15: 1, 16: 1,
    21: 1, 22: 1, 23: 1, 24: 1, 25: 1, 26: 1, 27: 1, 28: 1, 29: 1, 30: 1, 31: 1, 32: 1, 33: 1, 34: 1, 35: 1,
    36: 1, 37: 1, 38: 1, 39: 1, 40: 1, 41: 1, 42: 1, 43: 1, 44: 1, 45: 1, 46: 1, 47: 1, 48: 1, 49: 1, 50: 1,
    51: 1, 52: 1, 53: 1, 54: 1, 55: 1, 56: 1, 57: 1, 58: 1, 59: 1,
    60: 1, 61: 1, 62: 1, 63: 1, 64: 1, 65: 1, 66: 1, 67: 1, 68: 1,
    71: 1, 72: 1, 73: 1, 74: 1, 75: 1, 76: 1, 77: 1, 78: 1, 79: 1,
    82: 1, 83: 1, 98: 1, 99: 1
  };

  function isValidLuhn(cardStr) {
    var digits = (cardStr || "").replace(/[ \-]/g, "");
    if (!/^\d{13,19}$/.test(digits)) return false;
    if (/^(\d)\1+$/.test(digits)) return false;
    var sum = 0, dbl = false;
    for (var i = digits.length - 1; i >= 0; i--) {
      var d = parseInt(digits.charAt(i), 10);
      if (dbl) { d *= 2; if (d > 9) d -= 9; }
      sum += d;
      dbl = !dbl;
    }
    return sum % 10 === 0;
  }

  function isValidMyNric(nricStr) {
    var digits = (nricStr || "").replace(/[\s\-]/g, "");
    if (!/^\d{12}$/.test(digits)) return false;
    var month = parseInt(digits.substring(2, 4), 10);
    var day = parseInt(digits.substring(4, 6), 10);
    var pb = parseInt(digits.substring(6, 8), 10);
    var maxDays = { 1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31 };
    if (!maxDays[month] || day < 1 || day > maxDays[month]) return false;
    return Boolean(VALID_MY_PB_CODES[pb]);
  }

  function isValidCnId(idStr) {
    var raw = (idStr || "").trim().toUpperCase();
    if (!/^[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dX]$/.test(raw)) return false;
    var year = parseInt(raw.substring(6, 10), 10);
    var month = parseInt(raw.substring(10, 12), 10);
    var day = parseInt(raw.substring(12, 14), 10);
    var isLeap = (year % 4 === 0 && year % 100 !== 0) || (year % 400 === 0);
    var maxDays = { 1: 31, 2: isLeap ? 29 : 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31 };
    if (!maxDays[month] || day < 1 || day > maxDays[month]) return false;
    var weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
    var checkMap = "10X98765432";
    var total = 0;
    for (var i = 0; i < 17; i++) total += parseInt(raw.charAt(i), 10) * weights[i];
    return raw.charAt(17) === checkMap.charAt(total % 11);
  }

  function createSessionEngine() {
    var origToPh = Object.create(null);
    var phToOrig = Object.create(null);
    var origToCat = Object.create(null);
    var counters = Object.create(null);
    var allowlist = ["127.0.0.1", "0.0.0.0", "localhost", "example.com"];

    function isAllowlisted(val) {
      if (!val) return false;
      var lower = val.trim().toLowerCase();
      for (var i = 0; i < allowlist.length; i++) {
        if (allowlist[i].toLowerCase() === lower) return true;
      }
      return false;
    }

    function alloc(original, category, tpl) {
      if (Object.prototype.hasOwnProperty.call(origToPh, original)) {
        return origToPh[original];
      }
      var idx = (counters[category] || 0) + 1;
      var ph;
      while (true) {
        ph = tpl.replace("{category}", category).replace("{index}", idx);
        if (ph !== original && !Object.prototype.hasOwnProperty.call(phToOrig, ph)) break;
        idx += 1;
      }
      counters[category] = idx;
      origToPh[original] = ph;
      phToOrig[ph] = original;
      origToCat[original] = category;
      return ph;
    }

    function escapeRe(s) {
      return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function makeSentinelPrefix(text, stage) {
      var nonce = Math.random().toString(36).slice(2);
      if (typeof crypto !== "undefined" && crypto.getRandomValues) {
        var rand = new Uint32Array(2);
        crypto.getRandomValues(rand);
        nonce = rand[0] + "_" + rand[1];
      }
      var prefix = "\x00" + stage + "_" + nonce + "_";
      while (text.indexOf(prefix) !== -1) prefix += "\x00";
      return prefix;
    }

    function sanitize(rawText) {
      if (!rawText || rawText.length > MAX_CHARS) {
        return { text: rawText || "", count: 0, categories: {}, oversize: Boolean(rawText && rawText.length > MAX_CHARS) };
      }
      var working = rawText;
      var sentToPh = Object.create(null);
      var phToSent = Object.create(null);
      var seq = 0, count = 0;
      var categories = Object.create(null);
      var prefix = makeSentinelPrefix(rawText, "\x01__EXT");
      var sentinelRx = new RegExp(escapeRe(prefix) + "[0-9]+__\x01\x00", "g");

      function unprotect(val) {
        return val.replace(sentinelRx, function (tok) {
          return Object.prototype.hasOwnProperty.call(sentToPh, tok) ? sentToPh[tok] : tok;
        });
      }

      function makeSent(ph) {
        if (Object.prototype.hasOwnProperty.call(phToSent, ph)) return phToSent[ph];
        seq += 1;
        var s = prefix + seq + "__\x01\x00";
        sentToPh[s] = ph;
        phToSent[ph] = s;
        return s;
      }

      function hit(cat) {
        count += 1;
        categories[cat] = (categories[cat] || 0) + 1;
      }

      function protectedReplace(regex, replacer) {
        var spans = [], token;
        sentinelRx.lastIndex = 0;
        while ((token = sentinelRx.exec(working)) !== null) spans.push([token.index, sentinelRx.lastIndex]);
        working = working.replace(regex, function () {
          var args = arguments, start = args[args.length - 2], end = start + args[0].length;
          var lo = 0, hi = spans.length;
          while (lo < hi) {
            var mid = (lo + hi) >>> 1;
            if (spans[mid][1] <= start) lo = mid + 1; else hi = mid;
          }
          var first = lo;
          lo = 0; hi = spans.length;
          while (lo < hi) {
            var middle = (lo + hi) >>> 1;
            if (spans[middle][0] < end) lo = middle + 1; else hi = middle;
          }
          var last = lo - 1;
          if (first <= last && (start > spans[first][0] || end < spans[last][1])) return args[0];
          return replacer.apply(null, args);
        });
      }

      function full(rx, cat, tpl, valFn) {
        protectedReplace(rx, function (m) {
          if (Object.prototype.hasOwnProperty.call(sentToPh, m) || isAllowlisted(m)) return m;
          var orig = unprotect(m);
          if (valFn && !valFn(orig)) return m;
          hit(cat);
          return makeSent(alloc(orig, cat, tpl));
        });
      }

      function pss(rx, cat, tpl) {
        protectedReplace(rx, function (fullM, pre, sec, suf) {
          if (!sec || Object.prototype.hasOwnProperty.call(sentToPh, sec)) return fullM;
          var orig = unprotect(sec);
          if (isAllowlisted(orig) || isAllowlisted(fullM)) return fullM;
          hit(cat);
          return (pre || "") + makeSent(alloc(orig, cat, tpl)) + (suf || "");
        });
      }

      function qss(rx, cat, tpl) {
        protectedReplace(rx, function (fullM, pre, q, sec, endQ) {
          if (!sec || Object.prototype.hasOwnProperty.call(sentToPh, sec)) return fullM;
          var orig = unprotect(sec);
          if (isAllowlisted(orig) || isAllowlisted(fullM)) return fullM;
          hit(cat);
          return (pre || "") + (q || "") + makeSent(alloc(orig, cat, tpl)) + (endQ || "");
        });
      }

      // Protect existing placeholders
      Object.keys(phToOrig).sort(function (a, b) { return b.length - a.length; }).forEach(function (eph) {
        if (working.indexOf(eph) !== -1) {
          working = working.split(eph).join(makeSent(eph));
        }
      });

      // 0. PEM / SSH / PGP Private Keys
      full(/-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----[\s\S]{1,32768}?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----/g, "PRIVATE_KEY", "<PRIVATE_KEY_{index}>");

      // 1. Database, Basic Auth, curl -u & Webhook URLs
      pss(/(\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis(?:s)?|amqp|mssql):\/\/(?:[^:\/@\s'"`]*:)?)([^\s'"`\/]+)(@(?=[^\s@\/'"`,;]+))/gi, "DB_PASS", "[DB_PASS_{index}]");
      pss(/(\b(?:https?|ftp):\/\/[^:\/@\s'"`]+:)([^\s'"`\/]+)(@(?=[^\s@\/'"`,;]+))/gi, "DB_PASS", "[DB_PASS_{index}]");
      pss(/((?:^|\s)(?:-u|--user)\s+['"`]?[^:\s'"`]+:)([^\s'"`]+)(['"`]?)/gi, "DB_PASS", "[DB_PASS_{index}]");
      pss(/((?:discord(?:app)?\.com\/api\/webhooks\/\d+\/|hooks\.slack\.com\/services\/|open\.feishu\.cn\/open-apis\/bot\/v2\/hook\/|oapi\.dingtalk\.com\/robot\/send\?access_token=|qyapi\.weixin\.qq\.com\/cgi-bin\/webhook\/send\?key=))([A-Za-z0-9_\-\/]{16,})()/gi, "API_KEY", "<API_KEY_{index}>");

      // 2. Explicit Signature API Keys, Cloud Tokens & Auth Headers
      full(/\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\bsk-(?:proj-|ant-api\d{2}-|ant-|or-v\d+-|live-|test-)?[A-Za-z0-9_\-]{16,}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b(?:(?:sk|rk|pk)_(?:live|test)_[0-9a-zA-Z]{16,}|whsec_[0-9a-zA-Z]{24,})\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_\-]{20,}|gldt-[A-Za-z0-9_\-]{20,}|glrt-[A-Za-z0-9_\-]{20,})\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b(?:gsk_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|npm_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_\-]{24,})\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\bAIza[0-9A-Za-z_\-]{35}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\bxox[baprs]-[0-9A-Za-z\-]{10,}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b\d{8,10}:AA[A-Za-z0-9_\-]{32,35}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b(?:dop_v1_[a-f0-9]{64}|lin_api_[A-Za-z0-9]{32,}|sbp_[a-f0-9]{40}|PMAK-[a-f0-9]{24}-[a-f0-9]{34}|shpat_[a-fA-F0-9]{32})\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b(?:(?:cfut|cfat|cfrt)_[A-Za-z0-9_\-]{28,}|v1\.0-[A-Fa-f0-9]{24}-[A-Fa-f0-9]{64,}|sb_secret_[A-Za-z0-9_\-]{20,}|vercel_(?:pat|tok|secret)_[A-Za-z0-9_\-]{20,}|vc[pk]_[A-Za-z0-9_\-]{24,}|dapi[0-9a-fA-F]{32}(?:-\d)?)\b/g, "API_KEY", "<API_KEY_{index}>");
      pss(/(\b(?:AccountKey|SharedAccessKey|SharedAccessSignature)=)([^\s;'"`\]\}]{16,})()/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/([?&]sig=)([A-Za-z0-9%+\/=]{24,})()/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/(\bAuthorization\s*:\s*Basic\s+)([A-Za-z0-9+\/=]{8,})()/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/(\bBearer\s+)([A-Za-z0-9_\-\.~+\/]{12,}=*)()/gi, "API_KEY", "<API_KEY_{index}>");

      // 3. Emails & Network (MAC, IPv6, Private IPv4, Public IPv4)
      full(/\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g, "EMAIL", "[EMAIL_{index}]");
      full(/\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b/g, "MAC_ADDR", "[MAC_{index}]");
      full(/(?<![0-9A-Fa-f:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|fe80:(?::[0-9A-Fa-f]{1,4}){0,4}%[0-9a-zA-Z]{1,}|::(?:ffff(?::0{1,4})?:)?(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|(?:[0-9A-Fa-f]{1,4}:){1,6}:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,5}|(?:[0-9A-Fa-f]{1,4}:){1,7}:|::(?:[0-9A-Fa-f]{1,4}:){0,5}[0-9A-Fa-f]{1,4})(?![0-9A-Fa-f:])/g, "IPV6", "[IPV6_{index}]");
      full(/(?<![\d.])(?:10\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|172\.(?:1[6-9]|2\d|3[01])\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|192\.168\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d))(?![\d.])/g, "PRIVATE_IP", "[PRIVATE_IP_{index}]");
      full(/(?<![\d.vV])(?!0\.)(?!10\.)(?!127\.)(?!192\.168\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)(?!192\.0\.2\.)(?!198\.51\.100\.)(?!203\.0\.113\.)(?:25[0-4]|2[0-4]\d|1\d\d|[1-9]\d?)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])/g, "PUBLIC_IP", "[PUBLIC_IP_{index}]");

      // 4. OS Path Usernames & PII
      pss(/((?:[A-Za-z]:[\\\/]+Users[\\\/]+|(?<![A-Za-z0-9_])\/Users\/|(?<![A-Za-z0-9_])\/home\/))(?!(?:Public|Default(?:\s+User)?|All\s+Users|Shared|root|ubuntu|admin|ec2-user|vagrant|docker|nobody|www-data|postgres|git|runner)(?:[\\\/\s'"`,;:\)\]\}]|$))([^\s\\\/:'"`<>|*?\[\]{}(),;]{2,64})()(?=[\\\/\s'"`,;:\)\]\}]|$)/gi, "USER_PATH", "[USER_PATH_{index}]");
      full(/\b\d{6}-\d{2}-\d{4}\b/g, "ID_CARD", "[ID_CARD_{index}]", isValidMyNric);
      full(/\b[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b/g, "ID_CARD", "[ID_CARD_{index}]", isValidCnId);
      full(/\b(?:(?:4\d{3}|5[1-5]\d{2}|222[1-9]|22[3-9]\d|2[3-6]\d{2}|27[01]\d|2720)(?:[ -]?\d{4}){3}|62\d{2}(?:[ -]?\d{4}){3}(?:[ -]?\d{1,3})?|3[47]\d{2}[ -]?\d{6}[ -]?\d{5})\b/g, "BANK_CARD", "[BANK_CARD_{index}]", isValidLuhn);
      full(/\b(?:[A-HK-NP-Z]\d{8}|[EGDSP]\d{8})\b/g, "PASSPORT", "[PASSPORT_{index}]");
      full(/(?<!\d)(?:(?:(?:\+|00)60[\s\-]?|0)1(?:1[\s\-]?\d{4}[\s\-]?\d{4}|[02-9][\s\-]?\d{3}[\s\-]?\d{4})|(?:\+|00)60[\s\-]?[3-9][\s\-]?\d{3,4}[\s\-]?\d{4}|\+(?:65|1|44|61|81|82|852|853|886)[\s\-]?\d{3,4}[\s\-]?\d{4,6}|(?:(?:\+|00)86[\s\-]?)?1[3-9]\d[\s\-]?\d{4}[\s\-]?\d{4})(?!\d)/g, "PHONE", "[PHONE_{index}]");

      // 5. Chinese Key-Value Assignments
      qss(/((?:数据库密码|登录密码|管理员密码|管理密码|初始密码|默认密码|支付密码|交易密码|无线密码|新密码|旧密码|原密码|密码|口令|安全码|验证码|动态码|校验码|PIN码)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+))(['"`])([^'"`\r\n]{3,})(\2)/gi, "DB_PASS", "[DB_PASS_{index}]");
      pss(/((?:数据库密码|登录密码|管理员密码|管理密码|初始密码|默认密码|支付密码|交易密码|无线密码|新密码|旧密码|原密码|密码|口令|安全码|验证码|动态码|校验码|PIN码)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+)['"`]?)([^\s#;,&，。！!？?)'"`\]\}\r\n]{3,})(['"`]?)/gi, "DB_PASS", "[DB_PASS_{index}]");
      qss(/((?:访问密钥|私有密钥|接口密钥|应用密钥|签名密钥|密钥|秘钥|私钥|令牌)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+))(['"`])([^'"`\r\n]{4,})(\2)/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/((?:访问密钥|私有密钥|接口密钥|应用密钥|签名密钥|密钥|秘钥|私钥|令牌)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+)['"`]?)([^\s#;,&，。！!？?)'"`\]\}\r\n]{4,})(['"`]?)/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/((?:身份证号码|身份证号|身份证|证件号码|证件号|大马卡号|大马卡|护照号码|护照号|税号|社保号)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+)['"`]?)([A-Za-z0-9\-]{6,20})(['"`]?)/gi, "ID_CARD", "[ID_CARD_{index}]");
      pss(/((?:手机号码|手机号|联系电话|电话号码|手提电话|手提号码|电话|手提|座机)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+)['"`]?)(\+?[0-9][0-9\-]{6,15})(['"`]?)/gi, "PHONE", "[PHONE_{index}]");
      pss(/((?:银行卡号|银行卡|信用卡号|储蓄卡号|卡号)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+)['"`]?)([0-9][0-9 \-]{10,22}[0-9])(['"`]?)/gi, "BANK_CARD", "[BANK_CARD_{index}]");
      qss(/((?:管理员账号|管理员帐号|登录账号|登录帐号|测试账号|测试帐号|银行账号|银行帐号|银行户口|银行账户|银行帐户|户口号码|户口号|客户账号|商户号|客户号|员工号|会员号|学生号|账号|帐号|户口|账户|帐户|用户名|登录名|户名|工号|学号|微信号)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+))(['"`])([^'"`\r\n]{2,})(\2)/gi, "USER_ID", "[USER_ID_{index}]");
      pss(/((?:管理员账号|管理员帐号|登录账号|登录帐号|测试账号|测试帐号|银行账号|银行帐号|银行户口|银行账户|银行帐户|户口号码|户口号|客户账号|商户号|客户号|员工号|会员号|学生号|账号|帐号|户口|账户|帐户|用户名|登录名|户名|工号|学号|微信号)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+)['"`]?)([^\s#;,&，。！!？?)'"`\]\}\r\n]{2,})(['"`]?)/gi, "USER_ID", "[USER_ID_{index}]");

      // 6. English Prefix-Guarded & Structured Key-Value Assignments
      qss(/((?:^|(?<=[\s'"`(\[{,;_\-\.?&]))(?:db|app|api|auth|user|usr|root|admin|client|access|secret|private|refresh|session|jwt|mysql|pg|postgres|redis|mongo|smtp|ftp|ssh|aws|gcp|azure|login|master|service|webhook|proxy|mail|email|token|key)?(?:password|passwd|passphrase|pwd|pass|pw|pin|otp|cvv|cvc)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d)))(['"`])([^'"`\r\n]{3,})(\2)/gi, "DB_PASS", "[DB_PASS_{index}]");
      pss(/((?:^|(?<=[\s'"`(\[{,;_\-\.?&]))(?:db|app|api|auth|user|usr|root|admin|client|access|secret|private|refresh|session|jwt|mysql|pg|postgres|redis|mongo|smtp|ftp|ssh|aws|gcp|azure|login|master|service|webhook|proxy|mail|email|token|key)?(?:password|passwd|passphrase|pwd|pass|pw|pin|otp|cvv|cvc)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d))['"`]?)(?![\$\{\(\[])(?!(?:true|false|null|none|nil|undefined|nan|yes|no|pass)\b)(?!\w+\()([^\s#;,&)'"`\]\}\r\n]{3,})(['"`]?)/gi, "DB_PASS", "[DB_PASS_{index}]");
      qss(/((?:^|(?<=[\s'"`(\[{,;_\-\.?&]))(?:(?:db|app|api|auth|user|usr|root|admin|client|access|secret|private|refresh|session|jwt|mysql|pg|postgres|redis|mongo|smtp|ftp|ssh|aws|gcp|azure|login|master|service|webhook|proxy|mail|email|token|key)?(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|app[_-]?secret|access[_-]?key|session[_-]?id|token|secret|apikey|cookie|jwt)|ak|sk|pk|tk)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d)))(['"`])([^'"`\r\n]{4,})(\2)/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/((?:^|(?<=[\s'"`(\[{,;_\-\.?&]))(?:(?:db|app|api|auth|user|usr|root|admin|client|access|secret|private|refresh|session|jwt|mysql|pg|postgres|redis|mongo|smtp|ftp|ssh|aws|gcp|azure|login|master|service|webhook|proxy|mail|email|token|key)?(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|app[_-]?secret|access[_-]?key|session[_-]?id|token|secret|apikey|cookie|jwt)|ak|sk|pk|tk)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d))['"`]?)(?![\$\{\(\[])(?!(?:true|false|null|none|nil|undefined)\b)(?!\w+\()([^\s#;,&)'"`\]\}\r\n]{4,})(['"`]?)/gi, "API_KEY", "<API_KEY_{index}>");
      qss(/((?:^|(?<=[\s'"`(\[{,;_\-\.?&]))(?:(?:service[_-]?role|anon|signing|encryption|decrypt|master|hmac|webhook|cloudflare|supabase|vercel|databricks|telegram|resend|twilio|stripe|openai|anthropic|gemini|github|gitlab|aws|gcp|azure)[_-]?(?:api[_-]?|auth[_-]?|access[_-]?|bot[_-]?|pat[_-]?|client[_-]?|private[_-]?|admin[_-]?)?(?:key|secret|token|pass(?:word)?|pwd|dsn|cred(?:ential)?s?)|x[-_]api[-_]key|connection[_-]?string|conn[_-]?str|auth[_-]?secret|signing[_-]?secret|webhook[_-]?secret|api[_-]?secret|signature)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d)))(['"`])(?![\$\{])([^'"`\r\n]{6,})(\2)/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/((?:^|(?<=[\s'"`(\[{,;_\-\.?&]))(?:(?:service[_-]?role|anon|signing|encryption|decrypt|master|hmac|webhook|cloudflare|supabase|vercel|databricks|telegram|resend|twilio|stripe|openai|anthropic|gemini|github|gitlab|aws|gcp|azure)[_-]?(?:api[_-]?|auth[_-]?|access[_-]?|bot[_-]?|pat[_-]?|client[_-]?|private[_-]?|admin[_-]?)?(?:key|secret|token|pass(?:word)?|pwd|dsn|cred(?:ential)?s?)|x[-_]api[-_]key|connection[_-]?string|conn[_-]?str|auth[_-]?secret|signing[_-]?secret|webhook[_-]?secret|api[_-]?secret|signature)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d))['"`]?)(?![\$\{\(\[])(?!(?:true|false|null|none|nil|undefined|nan|yes|no|int|str|string|bool|float|number|object|array|auto|default|void|return|break|continue|pass)\b)(?!\w+\()([^\s#;,&)'"`\]\}\r\n]{6,})(['"`]?)/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/(['"`]?\b(?:ic|nric|mykad|id_no|ic_no|no_kp|ssn|tin|tax_id|ssm|ssm_no)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d))['"`]?)([A-Za-z0-9\-]{6,20})(['"`]?)/gi, "ID_CARD", "[ID_CARD_{index}]");
      pss(/(['"`]?\b(?:hp|tel|mobile|phone|handphone|whatsapp)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d))['"`]?)(\+?[0-9][0-9\-]{6,15})(['"`]?)/gi, "PHONE", "[PHONE_{index}]");
      qss(/((?:^|(?<=[\s'"`(\[{,;\-\.?&]))(?:id|uid|uuid|sid|usr|user|uname|username|login|acct|account|user[ _\-]?id|client[ _\-]?id|app[ _\-]?id|account[ _\-]?id)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d)))(['"`])([^'"`\r\n]{2,})(\2)/gi, "USER_ID", "[USER_ID_{index}]");
      pss(/((?:^|(?<=[\s'"`(\[{,;\-\.?&]))(?:id|uid|uuid|sid|usr|user|uname|username|login|acct|account|user[ _\-]?id|client[ _\-]?id|app[ _\-]?id|account[ _\-]?id)\b['"`]?(?:[ \t]*[:=：][ \t]*|[ \t]+\-[ \t]+|-(?=[A-Za-z0-9_]*\d))['"`]?)(?![\$\{\(\[])(?!(?:true|false|null|none|nil|undefined)\b)(?!\w+\()([^\s#;,&)'"`\]\}\r\n]{2,})(['"`]?)/gi, "USER_ID", "[USER_ID_{index}]");

      Object.keys(sentToPh).forEach(function (k) {
        working = working.split(k).join(sentToPh[k]);
      });
      return { text: working, count: count, categories: categories, oversize: false };
    }

    function restore(text) {
      if (!text || text.length > MAX_CHARS) return { text: text || "", count: 0 };
      var working = text, count = 0;
      var phs = Object.keys(phToOrig).sort(function (a, b) { return b.length - a.length; });
      if (phs.length === 0) return { text: working, count: 0 };
      var resPrefix = makeSentinelPrefix(working, "\x02__EXT_RES");
      var sentToOrig = Object.create(null);

      phs.forEach(function (ph, idx) {
        var s = resPrefix + idx + "__\x02\x00";
        var core = /^[\[<{]([A-Z0-9_]+_\d+)[\]>\}]$/.exec(ph);
        if (core) {
          var tok = escapeRe(core[1]);
          var rx = new RegExp("(?:&lt;[ \\t]*" + tok + "[ \\t]*&gt;|\\[[ \\t]*" + tok + "[ \\t]*\\]|<[ \\t]*" + tok + "[ \\t]*>|\\{[ \\t]*" + tok + "[ \\t]*\\}|`[ \\t]*" + tok + "[ \\t]*`)", "gi");
          working = working.replace(rx, function () {
            count += 1;
            sentToOrig[s] = phToOrig[ph];
            return s;
          });
        } else if (working.indexOf(ph) !== -1) {
          var exactRx = new RegExp(escapeRe(ph), "g");
          working = working.replace(exactRx, function () {
            count += 1;
            sentToOrig[s] = phToOrig[ph];
            return s;
          });
        }
      });

      Object.keys(sentToOrig).forEach(function (sKey) {
        working = working.split(sKey).join(sentToOrig[sKey]);
      });
      return { text: working, count: count };
    }

    function hasPlaceholders(text) {
      if (!text) return false;
      var phs = Object.keys(phToOrig);
      for (var i = 0; i < phs.length; i++) {
        var ph = phs[i];
        if (text.indexOf(ph) !== -1) return true;
        var core = /^[\[<{]([A-Z0-9_]+_\d+)[\]>\}]$/.exec(ph);
        if (core) {
          var tok = escapeRe(core[1]);
          var rx = new RegExp("(?:&lt;[ \\t]*" + tok + "[ \\t]*&gt;|\\[[ \\t]*" + tok + "[ \\t]*\\]|<[ \\t]*" + tok + "[ \\t]*>|\\{[ \\t]*" + tok + "[ \\t]*\\}|`[ \\t]*" + tok + "[ \\t]*`)", "i");
          if (rx.test(text)) return true;
        }
      }
      return false;
    }

    function clear() {
      origToPh = Object.create(null);
      phToOrig = Object.create(null);
      origToCat = Object.create(null);
      counters = Object.create(null);
    }

    function size() {
      return Object.keys(phToOrig).length;
    }

    return {
      sanitize: sanitize,
      restore: restore,
      hasPlaceholders: hasPlaceholders,
      clear: clear,
      size: size
    };
  }

  globalScope.SanitizerExtCore = {
    createSessionEngine: createSessionEngine,
    isValidLuhn: isValidLuhn,
    isValidMyNric: isValidMyNric,
    isValidCnId: isValidCnId
  };
})(typeof window !== "undefined" ? window : globalThis);
