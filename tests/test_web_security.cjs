// Execute the single-file edition in a minimal DOM stub, with no browser or screenshots.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadWeb() {
  const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const elements = new Map();
  const intervals = [];
  function element(tagName = 'div') {
    let text = '', html = '';
    const node = { tagName, value: '', style: {}, checked: false, children: [], listeners: {},
      appendChild(child) { this.children.push(child); return child; },
      addEventListener(name, callback) { this.listeners[name] = callback; },
    };
    Object.defineProperties(node, {
      textContent: {
        get() { return text + this.children.map(child => child.textContent).join(''); },
        set(value) { text = String(value); html = ''; this.children = []; },
      },
      innerHTML: {
        get() { return html; },
        set(value) { html = String(value); text = ''; this.children = []; },
      },
    });
    return node;
  }
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement(tagName) { return element(tagName); },
    createTextNode(value) { const node = element('#text'); node.textContent = value; return node; },
    addEventListener() {},
    documentElement: { setAttribute() {} },
  };
  const context = vm.createContext({ document, window: { addEventListener() {} }, setInterval(callback) { intervals.push(callback); }, intervals, navigator: {} });
  vm.runInContext(script, context, { timeout: 1000 });
  return context;
}

test('diff tooltips obey masking and remove revealed originals when masked again', () => {
  const web = loadWeb();
  const secret = 'fake-credential-only';
  const ph = web.getOrCreatePlaceholder(secret, 'API_KEY', '<API_KEY_{index}>');
  web.document.getElementById('txtOutput').value = ph;
  web.renderDiffPreview(ph);
  const box = web.document.getElementById('diffPreviewBox');
  assert(!box.innerHTML.includes(secret));
  assert(box.innerHTML.includes('••••••'));
  web.toggleVaultMask();
  assert(box.innerHTML.includes(secret));
  web.toggleVaultMask();
  assert(!box.innerHTML.includes(secret));
});

test('fuzzy restore accepts paired variants and rejects malformed or unknown tags', () => {
  const web = loadWeb();
  web.placeholderToOriginal['<API_KEY_1>'] = 'fake-credential-only';
  for (const token of ['<API_KEY_1>', '[API_KEY_1]', '{api_key_1}', '`API_KEY_1`', '&lt;API_KEY_1&gt;', '[ \tAPI_KEY_1\t ]']) {
    const result = web.restoreText(token);
    assert.equal(result.text, 'fake-credential-only', token);
    assert.equal(result.count, 1);
  }
  for (const token of ['<API_KEY_1]', '{API_KEY_1\'', '[API_KEY_10]', 'API_KEY_1', '<API_KEY_1_extra>', '[tAPI_KEY_1t]']) {
    const result = web.restoreText(token);
    assert.equal(result.text, token);
    assert.equal(result.count, 0);
  }
});

test('semantic restore only replaces complete values and preserves a normal roundtrip', () => {
  const web = loadWeb();
  web.document.getElementById('chkSemanticIp').checked = true;
  const raw = '10.5.6.7 boss@fictional.test /Users/fake_operator/code.py';
  const masked = web.sanitizeText(raw).text;
  assert.equal(web.restoreText(masked).text, raw);
  const ordinary = '192.0.2.1010 xuser1@example.com user1@example.com.evil dev_user_10 https://192.0.2.101.evil.test !user1@example.com dev_user_1-other dev_user_1.other 中dev_user_1';
  assert.equal(web.restoreText(ordinary).text, ordinary);
  assert.equal(web.restoreText('192.0.2.101.').text, '10.5.6.7.');
});

test('restore is explicit and labels restored output as original sensitive data', () => {
  const web = loadWeb();
  web.placeholderToOriginal['<API_KEY_1>'] = 'fake-credential-only';
  web.document.getElementById('txtOutput').value = '<API_KEY_1>';
  web.runRestorePreview();
  assert.equal(web.document.getElementById('txtOutput').value, 'fake-credential-only');
  assert(web.document.getElementById('lblStatus').textContent.includes('真实数据'));
});

test('semantic IP exhaustion preserves distinct mappings and reversibility', () => {
  const web = loadWeb();
  web.document.getElementById('chkSemanticIp').checked = true;
  const originals = Array.from({ length: 152 }, (_, index) => '10.1.0.' + (index + 1));
  const masked = web.sanitizeText(originals.join(' ')).text;
  assert(masked.includes('[PRIVATE_IP_151]'));
  assert.equal(Object.keys(web.placeholderToOriginal).length, 152);
  assert.equal(web.restoreText(masked).text, originals.join(' '));
});

test('untrusted dictionary and allowlist words stay text and remove exact values', () => {
  const payloads = ['&#39)-globalThis.__syntheticProbe++-(&#39', '"><svg onload=globalThis.__syntheticProbe++>', '虚构 "company" \\ path'];
  for (const kind of ['dictionary', 'allowlist']) {
    for (const payload of payloads) {
      const web = loadWeb();
      const input = web.document.getElementById(kind === 'dictionary' ? 'inpCustomWord' : 'inpAllowlist');
      const container = web.document.getElementById(kind === 'dictionary' ? 'customWordsContainer' : 'allowlistContainer');
      web.document.getElementById('selCategory').value = 'COMPANY';
      input.value = payload;
      if (kind === 'dictionary') web.addCustomWords(); else web.addAllowlistWords();
      assert(container.textContent.includes(payload));
      assert.equal(container.innerHTML, ''); // raw user data never reaches an HTML parser
      const chip = container.children.find(child => child.textContent.includes(payload));
      assert.deepEqual(chip.children.map(child => child.tagName), ['#text', 'a']);
      const remove = chip.children[1];
      assert.equal(remove.onclick, undefined);
      let prevented = false;
      remove.listeners.click({ preventDefault() { prevented = true; } });
      assert(prevented);
      assert(!container.textContent.includes(payload));
      assert(!web.__syntheticProbe);
    }
  }
});

test('marker-shaped input cannot bypass masking or corrupt the original text', () => {
  for (const marker of ['\x00\x01__WEB_PH_spoof', '\x00\x01__WEB_PH_1__\x01\x00']) {
    const web = loadWeb();
    web.customDict = {};
    const raw = 'password="fake-credential-' + marker + '"';
    const result = web.sanitizeText(raw);
    assert(!result.text.includes('fake-credential-'));
    assert.equal(web.restoreText(result.text).text, raw);
    assert.equal(web.sanitizeText(result.text).text, result.text);
  }
});

test('a password containing an existing placeholder is masked as a whole value', () => {
  const web = loadWeb();
  web.customDict = {};
  const first = web.sanitizeText('password=synthetic-first').text.split('=')[1];
  for (const value of [first + ' synthetic-second', 'synthetic-second' + first + 'tail', 'left ' + first + ' synthetic-tail']) {
    const raw = 'password="' + value + '"';
    const result = web.sanitizeText(raw);
    assert(!result.text.includes('synthetic-second') && !result.text.includes('synthetic-tail'));
    assert.equal(web.restoreText(result.text).text, raw);
    assert.equal(web.sanitizeText(result.text).text, result.text);
  }
});

test('short dictionary words cannot rewrite internal marker fragments', () => {
  const web = loadWeb();
  web.customDict = { COMPANY: ['X', 'WEB', 'PH', '_'] };
  const raw = 'X';
  const result = web.sanitizeText(raw);
  assert.equal(web.restoreText(result.text).text, raw);
  assert(!result.text.includes('\x00'));
});

test('dictionary terms that match Object prototype keys are ordinary reversible strings', () => {
  const web = loadWeb();
  web.customDict = { CUSTOM_SECRET: ['__proto__', 'constructor'] };
  const raw = '__proto__ constructor';
  const result = web.sanitizeText(raw);
  assert.equal(web.restoreText(result.text).text, raw);
  web.renderVaultTable();
  assert.equal(Object.keys(web.originalToPlaceholder).length, 2);
});

test('allocated placeholders differ from literal originals and internal aliases stay ordinary text', () => {
  const web = loadWeb();
  web.customDict = { COMPANY: ['[COMPANY_1]'] };
  assert.equal(web.sanitizeText('[COMPANY_1]').text, '[COMPANY_2]');
  assert.equal(web.restoreText('[COMPANY_2]').text, '[COMPANY_1]');
  const restoreSpoof = '\x00\x02__WEB_RES_0__\x02\x00';
  const mixed = '[COMPANY_2] ' + restoreSpoof;
  assert.equal(web.restoreText(mixed).text, '[COMPANY_1] ' + restoreSpoof);
  const chipSpoof = '\x00\x03__CHIP_0__\x03\x00';
  web.renderDiffPreview('[COMPANY_2] ' + chipSpoof);
  assert(web.document.getElementById('diffPreviewBox').innerHTML.includes(chipSpoof));
});

test('semantic protection observes complete tokens and literal semantic originals still mask', () => {
  const web = loadWeb();
  web.customDict = {};
  web.document.getElementById('chkSemanticIp').checked = true;
  web.sanitizeText('/home/fake_operator/file');
  for (const raw of ['/home/dev_user_1suffix/file', '/home/dev_user_1-other/file']) {
    const result = web.sanitizeText(raw);
    assert.equal(result.count, 1);
    assert.notEqual(result.text, raw);
    assert.equal(web.restoreText(result.text).text, raw);
  }
  for (const raw of ['/home/dev_user_1/file', 'user1@example.com']) {
    const fresh = loadWeb();
    fresh.document.getElementById('chkSemanticIp').checked = true;
    const result = fresh.sanitizeText(raw);
    assert.notEqual(result.text, raw);
    assert.equal(fresh.restoreText(result.text).text, raw);
  }
});

test('manual and idle wipe clear secret terms, drafts, allowlist and revealed DOM', () => {
  const web = loadWeb();
  web.customDict = { COMPANY: [], CUSTOM_SECRET: ['synthetic-secret-term'] };
  web.allowlistItems = ['synthetic-sensitive-exception'];
  web.document.getElementById('inpCustomWord').value = 'synthetic draft';
  web.document.getElementById('inpAllowlist').value = 'synthetic exception draft';
  const ph = web.getOrCreatePlaceholder('synthetic-secret-term', 'CUSTOM_SECRET', '[{category}_{index}]');
  web.document.getElementById('txtOutput').value = ph;
  web.toggleVaultMask();
  assert(web.document.getElementById('diffPreviewBox').innerHTML.includes('synthetic-secret-term'));
  web.idleSecondsLeft = 1;
  web.intervals[0](); // Idle and manual wipe use the same shared clearing boundary.
  assert.equal(Object.keys(web.placeholderToOriginal).length, 0);
  assert.equal(web.customDict.CUSTOM_SECRET.length, 0);
  assert.equal(web.allowlistItems.length, 0);
  assert(web.vaultMasked);
  for (const id of ['inpCustomWord', 'inpAllowlist', 'txtInput', 'txtOutput']) assert.equal(web.document.getElementById(id).value, '');
  for (const id of ['customWordsContainer', 'allowlistContainer', 'diffPreviewBox', 'vaultTableBody']) {
    const node = web.document.getElementById(id);
    assert(!node.innerHTML.includes('synthetic') && !node.textContent.includes('synthetic'));
  }
  web.document.getElementById('selCategory').value = 'CUSTOM_SECRET';
  web.document.getElementById('inpCustomWord').value = 'fresh-term';
  web.addCustomWords();
  assert.equal(web.customDict.CUSTOM_SECRET[0], 'fresh-term');
});

test('clipboard changes cancel writeback; successful writes wait for API completion', async () => {
  const web = loadWeb();
  let reads = 0, writes = 0;
  web.navigator.clipboard = {
    readText() { return Promise.resolve(reads++ === 0 ? 'password=synthetic-only' : 'new content'); },
    writeText() { writes++; return Promise.resolve(); },
  };
  await web.sanitizeClipboardDirect();
  assert.equal(writes, 0);
  assert(web.document.getElementById('lblStatus').textContent.includes('取消'));
  web.navigator.clipboard.readText = () => Promise.resolve('password=synthetic-only');
  web.navigator.clipboard.writeText = value => { writes++; assert(!value.includes('synthetic-only')); return Promise.resolve(); };
  await web.sanitizeClipboardDirect();
  assert.equal(writes, 1);
  assert(web.document.getElementById('lblStatus').textContent.includes('已写回'));
});

test('wipe invalidates pending clipboard reads and errors do not claim success', async () => {
  const web = loadWeb();
  let resolveRead, writes = 0;
  web.navigator.clipboard = {
    readText() { return new Promise(resolve => { resolveRead = resolve; }); },
    writeText() { writes++; return Promise.resolve(); },
  };
  const pending = web.sanitizeClipboardDirect();
  web.wipeAllMemory();
  resolveRead('password=synthetic-only');
  await pending;
  assert.equal(writes, 0);
  assert.equal(web.document.getElementById('txtInput').value, '');
  assert.equal(Object.keys(web.placeholderToOriginal).length, 0);
  web.navigator.clipboard.readText = () => Promise.resolve('password=synthetic-only');
  web.navigator.clipboard.writeText = () => Promise.reject(new Error('synthetic-error-value'));
  await web.sanitizeClipboardDirect();
  const status = web.document.getElementById('lblStatus').textContent;
  assert(status.includes('失败') && !status.includes('synthetic-error-value'));
});

test('Copy Output waits for completion and reports asynchronous and legacy failures', async () => {
  const web = loadWeb();
  const output = web.document.getElementById('txtOutput');
  const status = web.document.getElementById('lblStatus');
  output.value = 'synthetic output';
  status.textContent = 'waiting';
  let finish;
  web.navigator.clipboard = { writeText() { return new Promise(resolve => { finish = resolve; }); } };
  const pending = web.copyOutputText();
  assert.equal(status.textContent, 'waiting');
  finish();
  await pending;
  assert(status.textContent.includes('已复制'));
  web.navigator.clipboard.writeText = () => Promise.reject(new Error('synthetic-private-error'));
  await web.copyOutputText();
  assert(status.textContent.includes('失败') && !status.textContent.includes('synthetic-private-error'));
  web.navigator.clipboard = undefined;
  output.style.display = 'none';
  output.select = () => {};
  web.document.execCommand = () => false;
  web.copyOutputText();
  assert(status.textContent.includes('失败'));
  assert.equal(output.style.display, 'none');
  web.document.execCommand = () => true;
  web.copyOutputText();
  assert(status.textContent.includes('已复制'));
  assert.equal(output.style.display, 'none');
});
