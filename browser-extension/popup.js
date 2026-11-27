(function () {
  "use strict";
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
    document.getElementById("lblVault").textContent = "当前标签页内存映射: " + (resp.vaultSize || 0) + " 组";
  }

  send({ type: "APS_STATUS" }, updateUi);

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
