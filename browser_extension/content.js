// Content script glue: reports the Shorts state to the service worker and executes commands
// it receives from the service worker (never from the page). Each command id runs at most once.
(function () {
  "use strict";
  const shorts = globalThis.InteractiveScrollingShorts;
  const handled = new Set();
  let lastSent = "";

  function report(force) {
    const state = shorts.readState();
    const serialized = JSON.stringify(state);
    if (!force && serialized === lastSent) return;
    lastSent = serialized;
    chrome.runtime.sendMessage({ kind: "shorts_state", state }).catch(() => {});
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (sender.id !== chrome.runtime.id || !message || message.kind !== "command") return false;
    const { id, action, video_id: expected, timeout_ms: timeout } = message;
    if (typeof id !== "string" || handled.has(id)) {
      sendResponse({ outcome: "rejected", reason: "duplicate command" });
      return false;
    }
    handled.add(id);
    if (handled.size > 200) handled.delete(handled.values().next().value);
    shorts
      .perform(action, expected, timeout)
      .then((res) => {
        sendResponse(res);
        report(true);
      })
      .catch((error) => sendResponse({ outcome: "unknown", reason: String(error) }));
    return true; // asynchronous response
  });

  document.addEventListener("visibilitychange", () => report(true));
  window.addEventListener("yt-navigate-finish", () => report(true));
  document.addEventListener("play", () => report(false), true);
  document.addEventListener("pause", () => report(false), true);
  setInterval(() => report(false), 1000);
  report(true);
})();
