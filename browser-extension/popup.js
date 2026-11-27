(function () {
  "use strict";
  var lang = (typeof navigator !== "undefined" && String(navigator.language || "").toLowerCase().indexOf("zh") === 0)
    ? "zh"
    : "en";
  var lastVaultSize = 0;

  var I18N = {
    zh: {
      guard: "粘贴瞬间敏感拦截",
      vault: "当前标签页内存映射: {n} 组",
      restoreTitle: "🔄 还原 AI 回复中的占位符",
      restorePh: "粘贴含占位符的 AI 回复，或直接在网页代码块/选区点击「一键还原复制」...",
      btnRestore: "还原真实数据（仅本机内存）",
      btnClear: "🔥 清空当前标签页映射",
      footer: "零网络权限 · 零持久化落盘 · 关闭标签页即焚"
    },
    en: {
      guard: "Intercept Secrets on Paste",
      vault: "Active tab RAM mappings: {n}",
      restoreTitle: "🔄 Restore Placeholders in AI Reply",
      restorePh: "Paste AI reply with placeholders, or click 'Restore & Copy' directly on the page...",
      btnRestore: "Restore Originals (RAM Only)",
      btnClear: "🔥 Clear Tab Mappings",
      footer: "Zero Permissions · Zero Storage · Wipes on Tab Close"
    }
  };

  function applyLang() {
    var dict = I18N[lang] || I18N.en;
    document.getElementById("lblGuard").textContent = dict.guard;
    document.getElementById("lblVault").textContent = dict.vault.replace("{n}", String(lastVaultSize));
    document.getElementById("lblRestoreTitle").textContent = dict.restoreTitle;
    document.getElementById("txtRestore").placeholder = dict.restorePh;
    document.getElementById("btnRestore").textContent = dict.btnRestore;
    document.getElementById("btnClear").textContent = dict.btnClear;
    document.getElementById("lblFooter").textContent = dict.footer;
  }

  function queryActive(cb) {
    if (typeof chrome === "undefined" || !chrome.tabs) return;
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (tabs && tabs[0]) cb(tabs[0].id);
    });
  }

  function send(payload, cb) {
    queryActive(function (tabId) {
      chrome.tabs.sendMessage(tabId, payload, function (resp) {
        if (chrome.runtime.lastError || !resp) return;
        if (cb) cb(resp);
      });
    });
  }

  function updateUi(resp) {
    document.getElementById("chkGuard").checked = Boolean(resp.enabled);
    lastVaultSize = resp.vaultSize || 0;
    if (resp.lang === "en" || resp.lang === "zh") {
      lang = resp.lang;
    }
    applyLang();
  }

  applyLang();
  send({ type: "APS_STATUS" }, updateUi);

  document.getElementById("btnLang").addEventListener("click", function () {
    lang = lang === "zh" ? "en" : "zh";
    applyLang();
    send({ type: "APS_SET_LANG", lang: lang }, updateUi);
  });
  document.getElementById("chkGuard").addEventListener("change", function (ev) {
    send({ type: "APS_TOGGLE", enabled: ev.target.checked }, updateUi);
  });
  document.getElementById("btnClear").addEventListener("click", function () {
    send({ type: "APS_CLEAR" }, updateUi);
  });
  document.getElementById("btnRestore").addEventListener("click", function () {
    var box = document.getElementById("txtRestore");
    send({ type: "APS_RESTORE_TEXT", text: box.value }, function (res) {
      if (res && typeof res.text === "string") box.value = res.text;
    });
  });
})();
