"""Verify cross-platform rule parity between Python (src/rules.py) and Web (web/index.html)."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.sanitizer import PrivacySanitizer


GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "rules_golden_cases.json"
WEB_PATH = REPO_ROOT / "web" / "index.html"


def verify_python_cases(cases: list) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="aps-parity-") as tmp:
        cfg = Path(tmp) / "config.json"
        ex = Path(tmp) / "example.json"
        ex.write_text(json.dumps({"language": "en", "custom_dictionary": {}}), encoding="utf-8")
        for case in cases:
            sanitizer = PrivacySanitizer(cfg, ex)
            raw = case["input"]
            san = sanitizer.sanitize(raw)
            restored = sanitizer.restore(san.sanitized_text)
            for forbidden in case.get("must_not_contain", []):
                if forbidden in san.sanitized_text:
                    errors.append(f"[Python] {case['name']}: leaked {forbidden!r} in {san.sanitized_text!r}")
            for required in case.get("must_contain", []):
                if required not in san.sanitized_text:
                    errors.append(f"[Python] {case['name']}: missing {required!r} in {san.sanitized_text!r}")
            if restored.restored_text != raw:
                errors.append(f"[Python] {case['name']}: roundtrip mismatch ({restored.restored_text!r} != {raw!r})")
    return errors


def verify_web_cases(cases: list) -> list[str]:
    node_script = r"""
const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync(process.argv[1], 'utf8');
const cases = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).cases;
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function makeWeb() {
  const elements = new Map();
  function element(tagName = 'div') {
    let text = '', htmlVal = '';
    return {
      tagName, value: '', style: {}, checked: false, children: [], listeners: {},
      appendChild(c) { this.children.push(c); return c; },
      addEventListener(n, cb) { this.listeners[n] = cb; },
      get textContent() { return text; }, set textContent(v) { text = String(v); },
      get innerHTML() { return htmlVal; }, set innerHTML(v) { htmlVal = String(v); },
    };
  }
  const document = {
    getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    createElement: element,
    createTextNode(v) { const n = element('#text'); n.textContent = v; return n; },
    addEventListener() {},
    documentElement: { setAttribute() {} },
  };
  const ctx = vm.createContext({ document, window: { addEventListener() {} }, setInterval() {}, navigator: {} });
  vm.runInContext(script, ctx, { timeout: 2000 });
  ctx.customDict = {};
  return ctx;
}

const errors = [];
for (const c of cases) {
  const web = makeWeb();
  const san = web.sanitizeText(c.input);
  const res = web.restoreText(san.text);
  for (const forbidden of (c.must_not_contain || [])) {
    if (san.text.includes(forbidden)) errors.push(`[Web] ${c.name}: leaked ${JSON.stringify(forbidden)} in ${JSON.stringify(san.text)}`);
  }
  for (const required of (c.must_contain || [])) {
    if (!san.text.includes(required)) errors.push(`[Web] ${c.name}: missing ${JSON.stringify(required)} in ${JSON.stringify(san.text)}`);
  }
  if (res.text !== c.input) errors.push(`[Web] ${c.name}: roundtrip mismatch`);
}
process.stdout.write(JSON.stringify(errors));
"""
    proc = subprocess.run(
        ["node", "-e", node_script, str(WEB_PATH), str(GOLDEN_PATH)],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Python & Web rule parity against shared golden cases.")
    parser.add_argument("--check", action="store_true", help="Exit nonzero if any rule parity drift is detected.")
    parser.parse_args()

    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["cases"]
    errors = verify_python_cases(cases) + verify_web_cases(cases)
    if errors:
        for err in errors:
            sys.stderr.write(f"FAIL: {err}\n")
        return 1
    sys.stdout.write(f"OK: {len(cases)} cross-platform golden cases verified identically in Python and Web.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
