// Browser Jarvis - Content Script
// Listens for messages from the background/popup and interacts with the page

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "JARVIS_GET_SELECTION") {
    const selection = window.getSelection()?.toString()?.trim() || "";
    sendResponse({ selection });
  }
  return true;
});
