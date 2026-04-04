// Browser Jarvis - Popup Script

// ─── Chrome API Guard (graceful degradation outside extension context) ────────

const isExtension = typeof chrome !== "undefined" && chrome.runtime?.id;

const chromeStorage = {
  get: (keys, cb) => {
    if (isExtension) {
      chrome.storage.sync.get(keys, cb);
    } else {
      const result = {};
      keys.forEach((k) => { result[k] = localStorage.getItem(`jarvis_${k}`) || undefined; });
      cb(result);
    }
  },
  set: (data, cb) => {
    if (isExtension) {
      chrome.storage.sync.set(data, cb);
    } else {
      Object.entries(data).forEach(([k, v]) => localStorage.setItem(`jarvis_${k}`, v));
      if (cb) cb();
    }
  },
};

const chromeSessionStorage = {
  get: (keys, cb) => {
    if (isExtension && chrome.storage.session) {
      chrome.storage.session.get(keys, cb);
    } else {
      cb({});
    }
  },
  remove: (keys) => {
    if (isExtension && chrome.storage.session) chrome.storage.session.remove(keys);
  },
};

// ─── State ───────────────────────────────────────────────────────────────────

let settings = { apiKey: "", model: "gpt-4o-mini" };

// ─── DOM Helpers ──────────────────────────────────────────────────────────────

const $ = (id) => document.getElementById(id);
const TABS = ["chat", "explain", "error", "command", "settings"];

// ─── Initialisation ──────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  setupTabs();
  setupFeatureButtons();
  setupSettings();
  await handleContextMenuTrigger();
  checkApiKeyWarning();
});

// ─── Settings ────────────────────────────────────────────────────────────────

async function loadSettings() {
  return new Promise((resolve) => {
    chromeStorage.get(["jarvisApiKey", "jarvisModel"], (data) => {
      settings.apiKey = data.jarvisApiKey || "";
      settings.model = data.jarvisModel || "gpt-4o-mini";
      if ($("api-key-input")) $("api-key-input").value = settings.apiKey;
      if ($("model-select")) $("model-select").value = settings.model;
      resolve();
    });
  });
}

function setupSettings() {
  // Save settings button
  $("save-settings").addEventListener("click", () => {
    const key = $("api-key-input").value.trim();
    const model = $("model-select").value;

    if (!key) {
      showStatus("settings-status", "API key cannot be empty.", "error");
      return;
    }
    if (!key.startsWith("sk-")) {
      showStatus("settings-status", "API key should start with 'sk-'. Please check.", "error");
      return;
    }

    chromeStorage.set({ jarvisApiKey: key, jarvisModel: model }, () => {
      settings.apiKey = key;
      settings.model = model;
      showStatus("settings-status", "✅ Settings saved successfully!", "success");
      checkApiKeyWarning();
    });
  });

  // Toggle API key visibility
  $("toggle-key-visibility").addEventListener("click", () => {
    const input = $("api-key-input");
    input.type = input.type === "password" ? "text" : "password";
  });

  // Go to settings from warning banner
  $("go-to-settings").addEventListener("click", () => switchTab("settings"));
}

function checkApiKeyWarning() {
  const banner = $("api-key-warning");
  if (!settings.apiKey) {
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────

function setupTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}

function switchTab(tabName) {
  document.querySelectorAll(".tab").forEach((btn) => {
    const active = btn.dataset.tab === tabName;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active);
  });

  TABS.forEach((t) => {
    const panel = $(`tab-${t}`);
    if (t === tabName) {
      panel.classList.add("active");
      panel.removeAttribute("hidden");
    } else {
      panel.classList.remove("active");
      panel.setAttribute("hidden", "");
    }
  });
}

// ─── Context Menu Trigger ─────────────────────────────────────────────────────

async function handleContextMenuTrigger() {
  return new Promise((resolve) => {
    chromeSessionStorage.get(["contextSelection", "contextAction"], (data) => {
      if (data.contextSelection && data.contextAction) {
        const textareaId = `${data.contextAction}-input`;
        const textarea = $(textareaId);
        if (textarea) {
          textarea.value = data.contextSelection;
          switchTab(data.contextAction);
        }
        // Clear so it doesn't re-trigger on next open
        chromeSessionStorage.remove(["contextSelection", "contextAction"]);
      }
      resolve();
    });
  });
}

// ─── Feature Buttons ─────────────────────────────────────────────────────────

function setupFeatureButtons() {
  const features = ["chat", "explain", "error", "command"];

  features.forEach((feature) => {
    // Submit button
    $(`${feature}-submit`).addEventListener("click", () => {
      const input = $(`${feature}-input`).value.trim();
      if (!input) {
        showOutput(`${feature}-output`, "Please enter some text first.", "error");
        return;
      }
      runFeature(feature, input);
    });

    // "Use page selection" button
    $(`${feature}-fetch-selection`).addEventListener("click", async () => {
      const selection = await getPageSelection();
      if (selection) {
        $(`${feature}-input`).value = selection;
      } else {
        showOutput(`${feature}-output`, "No text selected on the current page.", "error");
      }
    });

    // Allow Ctrl+Enter / Cmd+Enter to submit
    $(`${feature}-input`).addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        $(`${feature}-submit`).click();
      }
    });
  });
}

// ─── AI Request ───────────────────────────────────────────────────────────────

async function runFeature(feature, userInput) {
  if (!settings.apiKey) {
    showOutput(
      `${feature}-output`,
      "⚠️ API key not set. Go to Settings to add your OpenAI API key.",
      "error"
    );
    return;
  }

  const outputId = `${feature}-output`;
  setLoading(outputId, true);

  try {
    let response;
    if (isExtension) {
      response = await chrome.runtime.sendMessage({
        type: "JARVIS_AI_REQUEST",
        payload: { feature, userInput, apiKey: settings.apiKey, model: settings.model },
      });
    } else {
      // Fallback: call OpenAI directly from popup (dev/preview only)
      response = await callOpenAIDirect({ feature, userInput, apiKey: settings.apiKey, model: settings.model });
    }

    setLoading(outputId, false);
    if (response.success) {
      showOutput(outputId, response.data, "success");
    } else {
      showOutput(outputId, `❌ ${response.error}`, "error");
    }
  } catch (err) {
    setLoading(outputId, false);
    showOutput(outputId, `❌ ${err.message}`, "error");
  }
}

async function callOpenAIDirect({ feature, userInput, apiKey, model }) {
  const systemPrompts = {
    chat: "You are Browser Jarvis, an expert AI developer assistant. Answer dev questions concisely using markdown.",
    explain: "You are Browser Jarvis. Explain the given code snippet clearly with key steps and any issues.",
    error: "You are Browser Jarvis. Diagnose the error and provide root cause, fix, and prevention tips.",
    command: "You are Browser Jarvis. Generate the exact terminal command(s) for the described task with explanation.",
  };
  try {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
      body: JSON.stringify({
        model: model || "gpt-4o-mini",
        messages: [
          { role: "system", content: systemPrompts[feature] || systemPrompts.chat },
          { role: "user", content: userInput },
        ],
        max_tokens: 1500,
        temperature: 0.3,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { success: false, error: err?.error?.message || `HTTP ${res.status}` };
    }
    const data = await res.json();
    return { success: true, data: data.choices?.[0]?.message?.content || "No response." };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

// ─── Page Selection ───────────────────────────────────────────────────────────

async function getPageSelection() {
  if (!isExtension) return window.getSelection()?.toString()?.trim() || "";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return "";

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection()?.toString()?.trim() || "",
    });

    return results?.[0]?.result || "";
  } catch {
    return "";
  }
}

// ─── Output Rendering ─────────────────────────────────────────────────────────

function setLoading(outputId, isLoading) {
  const el = $(outputId);
  if (isLoading) {
    el.innerHTML = `<div class="spinner"></div><span>Jarvis is thinking…</span>`;
    el.className = "output loading";
  } else {
    el.className = "output";
  }
}

function showOutput(outputId, content, type = "success") {
  const el = $(outputId);

  if (type === "error") {
    el.innerHTML = escapeHtml(content);
    el.className = "output error-state";
  } else {
    el.innerHTML = renderMarkdown(content);
    el.className = "output";
    addCopyButtonsToCodeBlocks(el);
  }
}

// ─── Simple Markdown Renderer ─────────────────────────────────────────────────
// Handles the most common patterns in AI responses without an external library.

function renderMarkdown(text) {
  let html = escapeHtml(text);

  // Fenced code blocks (``` lang\n...\n```)
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, lang, code) => {
    return `<pre><code class="lang-${lang}">${code.trimEnd()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Italic
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");

  // Headings (### ## #)
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Use unique null-byte delimited markers to avoid ordered/unordered list confusion.
  // \x00 cannot appear in HTML-escaped user text so it is safe as a marker.
  html = html.replace(/^\d+\. (.+)$/gm, "\x00OL\x00$1\x00/OL\x00");
  html = html.replace(/^[-*] (.+)$/gm, "\x00UL\x00$1\x00/UL\x00");

  // Wrap consecutive OL markers into <ol>
  html = html.replace(/(\x00OL\x00[^\x00]*\x00\/OL\x00\n?)+/g, (m) =>
    "<ol>" + m.replace(/\x00OL\x00([^\x00]*)\x00\/OL\x00\n?/g, "<li>$1</li>") + "</ol>"
  );

  // Wrap consecutive UL markers into <ul>
  html = html.replace(/(\x00UL\x00[^\x00]*\x00\/UL\x00\n?)+/g, (m) =>
    "<ul>" + m.replace(/\x00UL\x00([^\x00]*)\x00\/UL\x00\n?/g, "<li>$1</li>") + "</ul>"
  );

  // Horizontal rule
  html = html.replace(/^---$/gm, "<hr/>");

  // Paragraphs (double newlines)
  html = html.replace(/\n\n+/g, "</p><p>");
  html = `<p>${html}</p>`;

  // Clean up empty paragraphs and paragraph-wrapped block elements
  html = html
    .replace(/<p><\/p>/g, "")
    .replace(/<p>(<(?:h[123]|pre|ul|ol|hr)[^>]*>)/g, "$1")
    .replace(/(<\/(?:h[123]|pre|ul|ol|hr)>)<\/p>/g, "$1");

  // Single newlines that are between text (not adjacent to HTML tags) → <br>
  html = html.replace(/([^>])\n([^<])/g, "$1<br>$2");

  return html;
}

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ─── Copy buttons for code blocks ────────────────────────────────────────────

function addCopyButtonsToCodeBlocks(container) {
  container.querySelectorAll("pre").forEach((pre) => {
    const btn = document.createElement("button");
    btn.textContent = "Copy";
    btn.className = "copy-btn";
    btn.addEventListener("click", () => {
      const code = pre.querySelector("code")?.textContent || pre.textContent;
      navigator.clipboard.writeText(code).then(() => {
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = "Copy"; }, 1500);
      });
    });
    pre.style.position = "relative";
    pre.appendChild(btn);
  });
}

// ─── Utility ─────────────────────────────────────────────────────────────────

function showStatus(elementId, message, type) {
  const el = $(elementId);
  el.textContent = message;
  el.className = `status-message ${type}`;
}
