/* Sanitizer Paste Guard — 100% RAM-Only JS Sanitization & Fuzzy Restoration Engine (Zero Network, Zero Storage) */
(function (globalScope) {
  "use strict";

  var MAX_CHARS = 1500000;

  function createSessionEngine() {
    var origToPh = Object.create(null);
    var phToOrig = Object.create(null);
    var origToCat = Object.create(null);
    var counters = Object.create(null);

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

    function sanitize(rawText) {
      if (!rawText || rawText.length > MAX_CHARS) {
        return { text: rawText || "", count: 0, categories: {}, oversize: rawText && rawText.length > MAX_CHARS };
      }
      var working = rawText;
      var sentToPh = Object.create(null);
      var phToSent = Object.create(null);
      var seq = 0, count = 0;
      var categories = Object.create(null);
      var rand = new Uint32Array(2);
      if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(rand);
      var prefix = "\x00\x01__EXT_" + rand[0] + "_" + rand[1] + "_";

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
      function full(rx, cat, tpl, val) {
        working = working.replace(rx, function (m) {
          if (m.indexOf(prefix) !== -1) return m;
          if (val && !val(m)) return m;
          hit(cat);
          return makeSent(alloc(m, cat, tpl));
        });
      }
      function pss(rx, cat, tpl) {
        working = working.replace(rx, function (fullM, pre, sec, suf) {
          if (!sec || sec.indexOf(prefix) !== -1) return fullM;
          hit(cat);
          return (pre || "") + makeSent(alloc(sec, cat, tpl)) + (suf || "");
        });
      }

      // High-confidence credentials, keys, network & PII
      full(/-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----[\s\S]{1,32768}?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY(?: BLOCK)?-----/g, "PRIVATE_KEY", "<PRIVATE_KEY_{index}>");
      pss(/(\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis(?:s)?|amqp|mssql):\/\/(?:[^:\/@\s'"`]*:)?)([^\s'"`\/]+)(@(?=[^\s@\/'"`,;]+))/gi, "DB_PASS", "[DB_PASS_{index}]");
      pss(/(\b(?:https?|ftp):\/\/[^:\/@\s'"`]+:)([^\s'"`\/]+)(@(?=[^\s@\/'"`,;]+))/gi, "DB_PASS", "[DB_PASS_{index}]");
      pss(/(\bAuthorization\s*:\s*Basic\s+)([A-Za-z0-9+\/=]{8,})()/gi, "API_KEY", "<API_KEY_{index}>");
      pss(/(\bBearer\s+)([A-Za-z0-9_\-\.~+\/]{12,}=*)()/gi, "API_KEY", "<API_KEY_{index}>");
      full(/\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\bsk-(?:proj-|ant-api\d{2}-|ant-|or-v\d+-|live-|test-)?[A-Za-z0-9_\-]{16,}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b(?:sk|rk|pk)_(?:live|test)_[0-9a-zA-Z]{16,}\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_\-]{20,}|gsk_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|npm_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{35}|xox[baprs]-[0-9A-Za-z\-]{10,}|SG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,})\b/g, "API_KEY", "<API_KEY_{index}>");
      full(/\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g, "EMAIL", "[EMAIL_{index}]");
      full(/(?<![\d.])(?:10\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|172\.(?:1[6-9]|2\d|3[01])\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)|192\.168\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d))(?![\d.])/g, "PRIVATE_IP", "[PRIVATE_IP_{index}]");
      pss(/((?:[A-Za-z]:[\\\/]+Users[\\\/]+|\/Users\/|\/home\/))(?!(?:Public|Default|root|ubuntu|admin|docker)(?:[\\\/\s'"]|$))([^\s\\\/:'"`<>|*?\[\]{}(),;]{2,64})()(?=[\\\/\s'"`,;:\)\]\}]|$)/gi, "USER_PATH", "[USER_PATH_{index}]");
      full(/\b(?:(?:4\d{3}|5[1-5]\d{2}|222[1-9]|22[3-9]\d|2[3-6]\d{2}|27[01]\d|2720)(?:[ -]?\d{4}){3}|62\d{2}(?:[ -]?\d{4}){3}(?:[ -]?\d{1,3})?|3[47]\d{2}[ -]?\d{6}[ -]?\d{5})\b/g, "BANK_CARD", "[BANK_CARD_{index}]", isValidLuhn);
      pss(/((?:^|(?<=[\s'"`(\[{,;_\-\.?&]))(?:db|app|api|auth|user|root|admin|client|access|secret|private|redis|mysql|pg)?(?:password|passwd|passphrase|pwd|pass|pw|pin|otp)\b['"`]?[ \t]*[:=：][ \t]*['"`]?)(?!(?:true|false|null|none|pass)\b)([^\s#;,&)'"`\]\}\r\n]{3,})(['"`]?)/gi, "DB_PASS", "[DB_PASS_{index}]");
      pss(/((?:数据库密码|登录密码|管理员密码|密码|口令|密钥|秘钥|令牌)(?:[ \t]*[:=：\-—~][ \t]*|[ \t]*(?:是|为)[ \t]*|[ \t]+)['"`]?)([^\s#;,&，。！!？?)'"`\]\}\r\n]{3,})(['"`]?)/gi, "DB_PASS", "[DB_PASS_{index}]");

      Object.keys(sentToPh).forEach(function (k) {
        working = working.split(k).join(sentToPh[k]);
      });
      return { text: working, count: count, categories: categories, oversize: false };
    }

    function restore(text) {
      if (!text || text.length > MAX_CHARS) return { text: text || "", count: 0 };
      var working = text, count = 0;
      var phs = Object.keys(phToOrig).sort(function (a, b) { return b.length - a.length; });
      phs.forEach(function (ph) {
        var core = /^[\[<]([A-Z0-9_]+_\d+)[\]>]$/.exec(ph);
        if (core) {
          var tok = escapeRe(core[1]);
          var rx = new RegExp("(?:&lt;[ \\t]*" + tok + "[ \\t]*&gt;|\\[[ \\t]*" + tok + "[ \\t]*\\]|<[ \\t]*" + tok + "[ \\t]*>|\\{[ \\t]*" + tok + "[ \\t]*\\}|`[ \\t]*" + tok + "[ \\t]*`)", "gi");
          working = working.replace(rx, function () { count += 1; return phToOrig[ph]; });
        }
      });
      return { text: working, count: count };
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

    return { sanitize: sanitize, restore: restore, clear: clear, size: size };
  }

  globalScope.SanitizerExtCore = { createSessionEngine: createSessionEngine };
})(typeof window !== "undefined" ? window : globalThis);
