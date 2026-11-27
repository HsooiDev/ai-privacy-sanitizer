/* Sanitizer Paste Guard Content Script — Synchronous paste interception + In-Page Restore & Copy */
(function () {
  "use strict";
  if (!window.SanitizerExtCore) return;

  var engine = window.SanitizerExtCore.createSessionEngine();
  var guardEnabled = true;
  var activeBanner = null;
  var activeRestorePill = null;
  var isSyntheticPaste = false;
  var currentLang = (typeof navigator !== "undefined" && String(navigator.language || "").toLowerCase().indexOf("zh") === 0)
    ? "zh"
    : "en";

  var COPY_TEXT = {
    zh: {
      interceptTitle: "🛡️ Sanitizer 拦截到 {count} 处敏感信息",
      interceptDetail: "{cats} — 建议脱敏后再发送给 AI。",
      btnSafe: "🛡️ 脱敏后粘贴",
      btnRaw: "仍粘贴原文",
      btnCancel: "取消",
      btnRestoreCopy: "🔄 一键还原复制",
      btnRestoredOk: "✅ 已还原 {count} 处并复制"
    },
    en: {
      interceptTitle: "🛡️ Sanitizer blocked {count} secret(s)",
      interceptDetail: "{cats} — Sanitize before sending to AI.",
      btnSafe: "🛡️ Sanitize & Paste",
      btnRaw: "Paste Raw",
      btnCancel: "Cancel",
      btnRestoreCopy: "🔄 Restore & Copy",
      btnRestoredOk: "✅ Restored {count} & Copied"
    }
  };

  function msg(key) {
    return (COPY_TEXT[currentLang] || COPY_TEXT.en)[key] || key;
  }

  function setNativeInputValue(target, value) {
    var proto = target.tagName === "TEXTAREA"
      ? (typeof HTMLTextAreaElement !== "undefined" ? HTMLTextAreaElement.prototype : null)
      : (typeof HTMLInputElement !== "undefined" ? HTMLInputElement.prototype : null);
    var desc = proto ? Object.getOwnPropertyDescriptor(proto, "value") : null;
    if (desc && typeof desc.set === "function") {
      desc.set.call(target, value);
    } else {
      target.value = value;
    }
  }

  function dispatchModernInputEvents(target, text) {
    try {
      if (typeof InputEvent === "function") {
        target.dispatchEvent(new InputEvent("input", {
          bubbles: true,
          cancelable: false,
          inputType: "insertFromPaste",
          data: text
        }));
        return;
      }
    } catch (_err) {}
    target.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function captureSavedSelection(target) {
    if (!target) return null;
    if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") {
      return {
        kind: "input",
        start: typeof target.selectionStart === "number" ? target.selectionStart : String(target.value || "").length,
        end: typeof target.selectionEnd === "number" ? target.selectionEnd : String(target.value || "").length
      };
    }
    if (target.isContentEditable && window.getSelection) {
      try {
        var sel = window.getSelection();
        if (sel && sel.rangeCount > 0) {
          return { kind: "range", range: sel.getRangeAt(0).cloneRange() };
        }
      } catch (_err) {}
    }
    return null;
  }

  function applySavedRange(target, savedSelection) {
    if (!savedSelection || savedSelection.kind !== "range" || !savedSelection.range) return;
    if (!window.getSelection) return;
    try {
      if (typeof target.focus === "function") target.focus();
      var sel = window.getSelection();
      if (sel) {
        if (typeof sel.removeAllRanges === "function") sel.removeAllRanges();
        if (typeof sel.addRange === "function") sel.addRange(savedSelection.range);
      }
    } catch (_err) {}
  }

  function insertTextAtTarget(target, text, savedSelection) {
    if (!target) return;
    if (typeof target.focus === "function") target.focus();

    if (target.tagName === "TEXTAREA" || target.tagName === "INPUT") {
      var cur = String(target.value || "");
      var start = (savedSelection && savedSelection.kind === "input" && typeof savedSelection.start === "number")
        ? Math.min(savedSelection.start, cur.length)
        : (typeof target.selectionStart === "number" ? target.selectionStart : cur.length);
      var end = (savedSelection && savedSelection.kind === "input" && typeof savedSelection.end === "number")
        ? Math.min(Math.max(start, savedSelection.end), cur.length)
        : (typeof target.selectionEnd === "number" ? target.selectionEnd : start);
      var nextVal = cur.slice(0, start) + text + cur.slice(end);
      setNativeInputValue(target, nextVal);
      if (typeof target.selectionStart === "number") {
        target.selectionStart = target.selectionEnd = start + text.length;
      }
      dispatchModernInputEvents(target, text);
      return;
    }

    if (target.isContentEditable) {
      applySavedRange(target, savedSelection);
      var beforeText = String(target.textContent || "");
      // Strategy 1: Synthetic ClipboardEvent('paste') for ProseMirror / Lexical / Slate editors
      if (typeof ClipboardEvent === "function" && typeof DataTransfer === "function") {
        try {
          var dt = new DataTransfer();
          dt.setData("text/plain", text);
          isSyntheticPaste = true;
          try {
            var pasteEv = new ClipboardEvent("paste", {
              bubbles: true,
              cancelable: true,
              clipboardData: dt
            });
            target.dispatchEvent(pasteEv);
          } finally {
            isSyntheticPaste = false;
          }
          if (String(target.textContent || "") !== beforeText) {
            return;
          }
        } catch (_err) {
          isSyntheticPaste = false;
        }
      }

      // Strategy 2: Modern DOM Selection Range + InputEvent (avoids deprecated execCommand)
      applySavedRange(target, savedSelection);
      try {
        var sel = window.getSelection ? window.getSelection() : null;
        if (sel && sel.rangeCount > 0) {
          if (typeof InputEvent === "function") {
            target.dispatchEvent(new InputEvent("beforeinput", {
              bubbles: true,
              cancelable: true,
              inputType: "insertFromPaste",
              data: text
            }));
          }
          var range = sel.getRangeAt(0);
          range.deleteContents();
          var textNode = document.createTextNode(text);
          range.insertNode(textNode);
          range.setStartAfter(textNode);
          range.collapse(true);
          sel.removeAllRanges();
          sel.addRange(range);
          dispatchModernInputEvents(target, text);
          return;
        }
      } catch (_err2) {}

      // Strategy 3: Last-resort fallback when Selection Range is unavailable
      if (typeof document.execCommand === "function") {
        document.execCommand("insertText", false, text);
      }
    }
  }

  function dismissBanner() {
    if (activeBanner && activeBanner.parentNode) {
      activeBanner.parentNode.removeChild(activeBanner);
    }
    activeBanner = null;
  }

  function dismissRestorePill() {
    if (activeRestorePill && activeRestorePill.parentNode) {
      activeRestorePill.parentNode.removeChild(activeRestorePill);
    }
    activeRestorePill = null;
  }

  function copyTextToClipboard(text) {
    if (typeof navigator !== "undefined" && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      return navigator.clipboard.writeText(text).then(function () { return true; }).catch(function () { return false; });
    }
    return Promise.resolve(false);
  }

  function showRestorePill(rawTextWithPlaceholders, anchorRect) {
    dismissRestorePill();
    var host = document.createElement("div");
    var topPx = (anchorRect && typeof anchorRect.top === "number")
      ? Math.max(8, Math.min(anchorRect.top + 6, (window.innerHeight || 600) - 48))
      : 24;
    var posStyle = (anchorRect && typeof anchorRect.right === "number")
      ? "top:" + Math.round(topPx) + "px; left:" + Math.max(12, Math.round(anchorRect.right - 166)) + "px;"
      : "bottom:76px; right:24px;";
    host.style.cssText = "position:fixed; " + posStyle + " z-index:2147483647;";

    var shadow = host.attachShadow({ mode: "closed" });
    var btn = document.createElement("button");
    btn.textContent = msg("btnRestoreCopy");
    btn.style.cssText = [
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif",
      "background:#1e293b", "color:#f8fafc", "border:1.5px solid #3b82f6",
      "border-radius:999px", "padding:6px 14px", "font-size:12px", "font-weight:700",
      "cursor:pointer", "box-shadow:0 8px 24px rgba(0,0,0,0.35)"
    ].join(";");

    btn.addEventListener("click", function () {
      var restored = engine.restore(rawTextWithPlaceholders);
      if (restored.count > 0) {
        copyTextToClipboard(restored.text).then(function (ok) {
          btn.textContent = msg("btnRestoredOk").replace("{count}", String(restored.count));
          btn.style.background = ok ? "#059669" : "#2563eb";
          btn.style.borderColor = ok ? "#34d399" : "#60a5fa";
          setTimeout(dismissRestorePill, 1500);
        });
      } else {
        dismissRestorePill();
      }
    });

    shadow.appendChild(btn);
    document.documentElement.appendChild(host);
    activeRestorePill = host;
  }

  function showInterceptBar(target, rawText, result, savedSelection) {
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
    title.textContent = msg("interceptTitle").replace("{count}", String(result.count));

    var detail = document.createElement("div");
    detail.style.cssText = "font-size:12px; color:#cbd5e1; margin-bottom:10px;";
    detail.textContent = msg("interceptDetail").replace("{cats}", cats);

    var row = document.createElement("div");
    row.style.cssText = "display:flex; gap:8px; flex-wrap:wrap;";

    function keepFocusOnMouseDown(ev) {
      if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
    }

    var btnSafe = document.createElement("button");
    btnSafe.textContent = msg("btnSafe");
    btnSafe.style.cssText = "background:#059669; color:#fff; border:none; border-radius:7px; padding:6px 12px; font-weight:700; cursor:pointer; font-size:12px;";
    btnSafe.addEventListener("mousedown", keepFocusOnMouseDown);
    btnSafe.addEventListener("click", function () {
      insertTextAtTarget(target, result.text, savedSelection);
      dismissBanner();
    });

    var btnRaw = document.createElement("button");
    btnRaw.textContent = msg("btnRaw");
    btnRaw.style.cssText = "background:#334155; color:#f8fafc; border:none; border-radius:7px; padding:6px 10px; font-weight:600; cursor:pointer; font-size:12px;";
    btnRaw.addEventListener("mousedown", keepFocusOnMouseDown);
    btnRaw.addEventListener("click", function () {
      insertTextAtTarget(target, rawText, savedSelection);
      dismissBanner();
    });

    var btnCancel = document.createElement("button");
    btnCancel.textContent = msg("btnCancel");
    btnCancel.style.cssText = "background:transparent; color:#94a3b8; border:1px solid #475569; border-radius:7px; padding:6px 10px; cursor:pointer; font-size:12px;";
    btnCancel.addEventListener("mousedown", keepFocusOnMouseDown);
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
    if (!guardEnabled || isSyntheticPaste) return;
    var target = event.target;
    var isEditable = target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable);
    if (!isEditable) return;
    var text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
    if (!text) return;
    var res = engine.sanitize(text);
    if (res.count > 0) {
      var savedSelection = captureSavedSelection(target);
      event.preventDefault();
      event.stopPropagation();
      showInterceptBar(target, text, res, savedSelection);
    }
  }, true);

  function checkSelectionForRestore() {
    if (engine.size() === 0 || !window.getSelection) return;
    var sel = window.getSelection();
    var text = sel ? String(sel.toString() || "") : "";
    if (!text || !engine.hasPlaceholders(text) || engine.restore(text).count === 0) {
      return;
    }
    var rect = null;
    try {
      if (sel.rangeCount > 0) rect = sel.getRangeAt(0).getBoundingClientRect();
    } catch (_err) {}
    showRestorePill(text, rect);
  }

  document.addEventListener("mouseup", checkSelectionForRestore, true);
  document.addEventListener("keyup", checkSelectionForRestore, true);
  document.addEventListener("mouseover", function (event) {
    if (engine.size() === 0) return;
    var t = event.target;
    if (!t || typeof t.closest !== "function") return;
    var block = t.closest("pre, code");
    if (!block) return;
    var txt = String(block.textContent || "");
    if (txt && engine.hasPlaceholders(txt) && engine.restore(txt).count > 0) {
      var rect = typeof block.getBoundingClientRect === "function" ? block.getBoundingClientRect() : null;
      showRestorePill(txt, rect);
    }
  }, true);
  document.addEventListener("keydown", function (event) {
    if (event && event.key === "Escape") {
      dismissBanner();
      dismissRestorePill();
    }
  }, true);
  document.addEventListener("scroll", dismissRestorePill, true);
  document.addEventListener("mousedown", function (event) {
    if (activeRestorePill && event && event.target !== activeRestorePill) {
      dismissRestorePill();
    }
  }, true);

  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener(function (msgIn, _sender, sendResponse) {
      if (!msgIn || !msgIn.type) return;
      if (msgIn.type === "APS_STATUS") {
        sendResponse({ enabled: guardEnabled, vaultSize: engine.size(), lang: currentLang });
      } else if (msgIn.type === "APS_TOGGLE") {
        guardEnabled = Boolean(msgIn.enabled);
        sendResponse({ enabled: guardEnabled, vaultSize: engine.size(), lang: currentLang });
      } else if (msgIn.type === "APS_SET_LANG") {
        currentLang = msgIn.lang === "en" ? "en" : "zh";
        sendResponse({ enabled: guardEnabled, vaultSize: engine.size(), lang: currentLang });
      } else if (msgIn.type === "APS_CLEAR") {
        engine.clear();
        dismissBanner();
        dismissRestorePill();
        sendResponse({ enabled: guardEnabled, vaultSize: 0, lang: currentLang });
      } else if (msgIn.type === "APS_RESTORE_TEXT") {
        sendResponse(engine.restore(String(msgIn.text || "")));
      }
    });
  }

  if (typeof globalScope !== "undefined") {
    globalScope.__SanitizerContentTestHooks = {
      insertTextAtTarget: insertTextAtTarget,
      engine: engine,
      getLang: function () { return currentLang; },
      setLang: function (l) { currentLang = l === "en" ? "en" : "zh"; }
    };
  }
})(typeof window !== "undefined" ? window : globalThis);
