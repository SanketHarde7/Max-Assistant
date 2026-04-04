// Browser Jarvis - Background Service Worker
// Handles AI API calls, context menus, and message routing

const OPENAI_API_URL = "https://api.openai.com/v1/chat/completions";

// ─── Context Menu Setup ──────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "jarvis-explain-code",
    title: "🤖 Jarvis: Explain this code",
    contexts: ["selection"],
  });

  chrome.contextMenus.create({
    id: "jarvis-analyze-error",
    title: "🐛 Jarvis: Analyze this error",
    contexts: ["selection"],
  });

  chrome.contextMenus.create({
    id: "jarvis-generate-command",
    title: "⚡ Jarvis: Generate command for this",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const selectedText = info.selectionText || "";
  if (!selectedText.trim()) return;

  const actionMap = {
    "jarvis-explain-code": "explain",
    "jarvis-analyze-error": "error",
    "jarvis-generate-command": "command",
  };

  const action = actionMap[info.menuItemId];
  if (!action) return;

  // Store the selected text and open the popup with the right tab
  chrome.storage.session.set({ contextSelection: selectedText, contextAction: action }, () => {
    chrome.action.openPopup();
  });
});

// ─── Message Router ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "JARVIS_AI_REQUEST") {
    handleAIRequest(message.payload)
      .then((result) => sendResponse({ success: true, data: result }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // Keep channel open for async response
  }
});

// ─── AI Request Handler ──────────────────────────────────────────────────────

async function handleAIRequest({ feature, userInput, apiKey, model }) {
  if (!apiKey || !apiKey.trim()) {
    throw new Error("API key not set. Please add your OpenAI API key in Settings.");
  }

  const systemPrompts = {
    chat: `You are Browser Jarvis, an expert AI developer assistant built into the browser. 
You help developers with coding questions, architecture decisions, debugging, and best practices.
Keep responses concise but complete. Use markdown formatting with code blocks where appropriate.`,

    explain: `You are Browser Jarvis, an expert code explainer. 
Given a code snippet, explain what it does clearly and concisely:
1. What the code does (1-2 sentences)
2. Key logic/steps
3. Any potential issues or improvements
Use markdown with syntax-highlighted code blocks.`,

    error: `You are Browser Jarvis, an expert debugger and error analyst.
Given an error message or stack trace, provide:
1. What caused the error (root cause)
2. Step-by-step fix
3. How to prevent it in the future
Be direct and actionable. Use code examples where helpful.`,

    command: `You are Browser Jarvis, an expert in terminal commands, shell scripting, and developer tools.
Given a task description, provide:
1. The exact command(s) to run (in a code block)
2. Brief explanation of what each part does
3. Common variations/flags if relevant
Focus on practical, ready-to-use commands for git, npm/yarn/pnpm, Docker, Linux/macOS, and common CLI tools.`,
  };

  const systemPrompt = systemPrompts[feature] || systemPrompts.chat;

  const response = await fetch(OPENAI_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model: model || "gpt-4o-mini",
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userInput },
      ],
      max_tokens: 1500,
      temperature: 0.3,
    }),
  });

  if (!response.ok) {
    const errData = await response.json().catch(() => ({}));
    const errMsg = errData?.error?.message || `HTTP ${response.status}`;
    throw new Error(`OpenAI API error: ${errMsg}`);
  }

  const data = await response.json();
  return data.choices?.[0]?.message?.content || "No response received.";
}
