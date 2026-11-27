# Sanitizer — Browser Paste Guard (Chrome / Edge MV3)

**Zero permissions (`permissions: []`) · Zero network requests · 100% tab-RAM only**

Intercepts `paste` events synchronously before sensitive text ever enters **ChatGPT, Claude, Gemini, Google AI Studio, DeepSeek, Poe, Perplexity, Grok, Microsoft Copilot, GitHub Copilot, or Mistral Le Chat** — eliminating the OS clipboard polling race window completely.

## What's New in v0.6.0
- **Expanded International AI Platforms**: Added Perplexity (`perplexity.ai`), Grok (`grok.com` / `x.com`), Microsoft Copilot (`copilot.microsoft.com`), GitHub Copilot (`github.com/copilot`), Google AI Studio (`aistudio.google.com`), and Mistral Le Chat (`chat.mistral.ai`).
- **In-Page One-Click "🔄 Restore & Copy" Pill**: Hover any `<pre>`/`<code>` block or select AI output containing placeholders to reveal a floating Shadow DOM **🔄 Restore & Copy** pill — restores in tab RAM and copies directly to your clipboard without opening the popup.
- **Modern Rich-Text Editor Support**: Uses native value setters, synthetic `ClipboardEvent('paste')`, and DOM Selection `Range` + `InputEvent` for ProseMirror / Lexical / Slate inputs.
- **Bilingual EN / 简中 UI**: Automatically adapts to browser locale with a one-click in-memory toggle in the popup.

## Quick Local Install (Developer Mode)
1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **Developer mode** (top-right).
3. Click **Load unpacked** and select this `browser-extension/` directory.
4. Paste any secret (e.g. `sk-proj-...`, `cfut_...`, `sb_secret_...`, `postgres://...`, `AccountKey=...`) into a supported AI chat — a floating confirmation bar appears immediately allowing you to paste sanitized text, keep raw text, or cancel.
5. Closing or refreshing the tab wipes all in-memory mappings automatically.
