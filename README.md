# 🤖 Browser Jarvis — AI Developer Assistant

> A Chrome browser extension that makes your daily development work faster and smarter using AI.

---

## ✨ Features

| Feature | What it does |
|---|---|
| **💬 Dev Chat** | Ask any development question in natural language |
| **🔍 Code Explainer** | Paste a code snippet and get a clear, step-by-step explanation |
| **🐛 Error Analyzer** | Paste an error message or stack trace and get the root cause + fix |
| **⚡ Command Generator** | Describe a task in plain English, get the exact terminal command |
| **Right-click menu** | Select text on any webpage → right-click → use Jarvis directly |

---

## 🚀 Installation

### Option 1 — Load as unpacked extension (Developer Mode)

1. Clone or download this repository:
   ```bash
   git clone https://github.com/SanketHarde7/browser-jarvis.git
   ```

2. Open Chrome and navigate to:
   ```
   chrome://extensions
   ```

3. Enable **Developer mode** (toggle in the top-right corner).

4. Click **"Load unpacked"** and select the `browser-jarvis` folder.

5. The Jarvis icon will appear in your Chrome toolbar. Click it to open.

### Option 2 — Chrome Web Store
Coming soon.

---

## ⚙️ Setup

1. Get your OpenAI API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
2. Click the Jarvis extension icon → go to **Settings (⚙️)**.
3. Paste your API key and click **Save Settings**.

> **Privacy:** Your API key is stored only in your browser's local storage (`chrome.storage.sync`) and is sent only directly to OpenAI. It is never shared with any third party.

---

## 🧑‍💻 How to Use

### 💬 Chat
Ask any development question — React hooks, algorithms, system design, best practices — anything.

### 🔍 Explain Code
Paste a function, class, or snippet and get a plain-English breakdown of what it does.

### 🐛 Error Analyzer
Paste an error message or full stack trace. Jarvis will tell you the root cause and how to fix it.

### ⚡ Command Generator
Describe what you want to do:
- *"Undo last git commit but keep changes"*
- *"Find all files modified in the last 7 days"*
- *"Install npm packages and skip peer dependency errors"*

### 📋 Use Page Selection
On any tab, select text (code, an error, a task description), then either:
- Click **"📋 Use page selection"** in any Jarvis tab, or
- Right-click the selection → choose a Jarvis action from the context menu

### ⌨️ Keyboard Shortcut
Press **Ctrl+Enter** (or **Cmd+Enter** on Mac) inside any input box to submit.

---

## 🛠️ Project Structure

```
browser-jarvis/
├── manifest.json       # Chrome Extension Manifest V3
├── background.js       # Service worker — AI API calls & context menus
├── content.js          # Content script — captures page text selections
├── popup/
│   ├── popup.html      # Extension popup UI
│   ├── popup.css       # Dark-theme styles
│   └── popup.js        # UI logic & AI request handling
├── icons/
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── package.json
```

---

## 🔒 Permissions

| Permission | Why it's needed |
|---|---|
| `contextMenus` | Right-click menu on selected text |
| `storage` | Save your API key and model preference locally |
| `activeTab` | Read selected text from the current tab |
| `scripting` | Execute script to get selected text from the page |
| `https://api.openai.com/*` | Make API calls to OpenAI |

---

## 🤝 Contributing

Pull requests are welcome! Please open an issue first to discuss major changes.

---

## 📄 License

MIT © [SanketHarde7](https://github.com/SanketHarde7)