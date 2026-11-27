/* Sanitizer Paste Guard Content Script — Synchronous paste interception with zero race window */
(function () {
  "use strict";
  if (!window.SanitizerExtCore) return;

  var engine = window.SanitizerExtCore.createSessionEngine();
  var guardEnabled = true;
  var activeBanner = null;

  function insertTextAtTarget(target, text) {
    if (!target) return;
    target.focus();
    if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") {
      var start = target.selectionStart || 0;
      var end = target.selectionEnd || 0;
      var before = target.value.slice(0, start);
      var after = target.value.slice(end);
      target.value = before + text + after;
      target.selectionStart = target.selectionEnd = start + text.length;
      target.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (target.isContentEditable) {
      document.execCommand("insertText", false, text);
    }
  }

  function dismissBanner() {
    if (activeBanner && activeBanner.parentNode) {
      activeBanner.parentNode.removeChild(activeBanner);
    }
    activeBanner = null;
  }

  function showInterceptBar(target, rawText, result) {
    dismissBanner();
    var host = document.createElement("div");
    host.style.cssText = "position:fixed; bottom:24px; right:24px; z-index:2147483647;";
    var shadow = host.attachShadow({ mode: "closed" });
    var cats = Object.keys(result.categories).map(function (k) { return k + ":" + result.categories[k]; }).join(", ");

    var card = document.createElement("div");
    card.style.cssText = [
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif",
      "background:#111827", "color:#f8fafc", "border:1.5px solid #10b981",
      "border-radius:12px", "padding:12px 16px", "box-shadow:0 12px 32px rgba(0,0,0,0.45)",
      "max-width:380px", "font-size:13px", "line-height:1.45"
    ].join(";");

    var title = document.createElement("div");
    title.style.cssText = "font-weight:700; color:#34d399; margin-bottom:4px;";
    title.textContent = "🛡️ Sanitizer 拦截到 " + result.count + " 处敏感信息";

    var detail = document.createElement("div");
    detail.style.cssText = "font-size:12px; color:#cbd5e1; margin-bottom:10px;";
    detail.textContent = cats + " — 建议脱敏后再发送给 AI。";

    var row = document.createElement("div");
    row.style.cssText = "display:flex; gap:8px; flex-wrap:wrap;";

    var btnSafe = document.createElement("button");
    btnSafe.textContent = "🛡️ 脱敏后粘贴";
    btnSafe.style.cssText = "background:#059669; color:#fff; border:none; border-radius:7px; padding:6px 12px; font-weight:700; cursor:pointer; font-size:12px;";
    btnSafe.addEventListener("click", function () {
      insertTextAtTarget(target, result.text);
      dismissBanner();
    });

    var btnRaw = document.createElement("button");
    btnRaw.textContent = "仍粘贴原文";
    btnRaw.style.cssText = "background:#334155; color:#f8fafc; border:none; border-radius:7px; padding:6px 10px; font-weight:600; cursor:pointer; font-size:12px;";
    btnRaw.addEventListener("click", function () {
      insertTextAtTarget(target, rawText);
      dismissBanner();
    });

    var btnCancel = document.createElement("button");
    btnCancel.textContent = "取消";
    btnCancel.style.cssText = "background:transparent; color:#94a3b8; border:1px solid #475569; border-radius:7px; padding:6px 10px; cursor:pointer; font-size:12px;";
    btnCancel.addEventListener("click", dismissBanner);

    row.appendChild(btnSafe);
    row.appendChild(btnRaw);
    row.appendChild(btnCancel);
    card.appendChild(title);
    card.appendChild(detail);
    card.appendChild(row);
    shadow.appendChild(card);
    document.documentElement.appendChild(host);
    activeBanner = host;
  }

  document.addEventListener("paste", function (event) {
    if (!guardEnabled) return;
    var target = event.target;
    var isEditable = target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable);
    if (!isEditable) return;
    var text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
    if (!text) return;
    var res = engine.sanitize(text);
    if (res.count > 0) {
      event.preventDefault();
      event.stopPropagation();
      showInterceptBar(target, text, res);
    }
  }, true);

  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
      if (!msg || !msg.type) return;
      if (msg.type === "APS_STATUS") {
        sendResponse({ enabled: guardEnabled, vaultSize: engine.size() });
      } else if (msg.type === "APS_TOGGLE") {
        guardEnabled = Boolean(msg.enabled);
        sendResponse({ enabled: guardEnabled, vaultSize: engine.size() });
      } else if (msg.type === "APS_CLEAR") {
        engine.clear();
        dismissBanner();
        sendResponse({ enabled: guardEnabled, vaultSize: 0 });
      } else if (msg.type === "APS_RESTORE_TEXT") {
        sendResponse(engine.restore(String(msg.text || "")));
      }
    });
  }
})();
