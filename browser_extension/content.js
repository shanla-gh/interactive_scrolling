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
    if (sender.id !== chrome.runtime.id || !message) return false;
    if (message.kind === "report_request") {
      // The service worker dropped this tab's state after a URL change; send it again even if
      // it looks unchanged from here.
      report(true);
      return false;
    }
    if (message.kind !== "command") return false;
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
  window.addEventListener("resize", () => report(false));
  // Shorts navigation is a single-page transition: report the new Short as soon as the URL
  // changes instead of waiting for the next periodic check.
  let lastPath = location.pathname;
  setInterval(() => {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      report(true);
    }
  }, 100);
  report(true);
})();
