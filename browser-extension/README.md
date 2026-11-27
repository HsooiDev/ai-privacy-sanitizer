# Sanitizer — Browser Paste Guard (Chrome / Edge MV3)

**Zero permissions (`permissions: []`) · Zero network requests · 100% tab-RAM only**

Intercepts `paste` events synchronously before sensitive text ever enters ChatGPT, Claude, Gemini, DeepSeek, or Poe chat inputs — eliminating the OS clipboard polling race window completely.

## Quick Local Install (Developer Mode)
1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **Developer mode** (top-right).
3. Click **Load unpacked** and select this `browser-extension/` directory.
4. Paste any secret (e.g. `sk-proj-...`, `postgres://...`, `Authorization: Basic ...`) into ChatGPT / Claude / DeepSeek — a floating confirmation bar appears immediately allowing you to paste sanitized text, keep raw text, or cancel.
5. Closing or refreshing the tab wipes all in-memory mappings automatically.
