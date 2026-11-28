"use strict";

const LABELS = {
  connected: "Connected to the desktop app",
  connecting: "Connecting...",
  offline: "Desktop app not reachable (is it running?)",
  rejected: "Pairing code not accepted",
  unpaired: "Not paired yet",
  starting: "Starting...",
};

let currentTab = null;
let previewTab = null;
let first = true;

async function refresh() {
  const status = await chrome.runtime.sendMessage({ kind: "popup_status" });
  const element = document.getElementById("status");
  element.textContent = LABELS[status.status] || status.status;
  element.className = status.status === "connected" ? "connected" : "problem";
  if (!document.getElementById("port").value) document.getElementById("port").value = status.port;
  if (first) document.getElementById("pairing").open = status.status !== "connected";
  first = false;

  [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  previewTab = status.preview_tab;
  const onShort = !!(currentTab && currentTab.url && currentTab.url.startsWith("https://www.youtube.com/shorts/"));
  const button = document.getElementById("preview");
  const info = document.getElementById("preview-status");
  if (previewTab !== null) {
    button.textContent = "Stop the preview";
    button.className = "";
    button.disabled = false;
    info.textContent = currentTab && previewTab === currentTab.id ? "This tab is shown in the app." : "Another tab is shown in the app.";
    info.className = "connected";
  } else {
    button.textContent = "Show this Short in the app";
    button.className = "primary";
    button.disabled = status.status !== "connected" || !onShort;
    info.className = status.preview_detail ? "problem" : "";
    info.textContent = status.preview_detail
      ? `Preview stopped: ${status.preview_detail}`
      : onShort
        ? ""
        : "Open a YouTube Short in this tab first.";
  }
}

document.getElementById("preview").addEventListener("click", async () => {
  const button = document.getElementById("preview");
  button.disabled = true;
  let response;
  if (previewTab !== null) {
    response = await chrome.runtime.sendMessage({ kind: "popup_preview_stop" });
  } else if (currentTab) {
    response = await chrome.runtime.sendMessage({ kind: "popup_preview_start", tab_id: currentTab.id });
  }
  if (response && response.ok === false) {
    const info = document.getElementById("preview-status");
    info.textContent = response.reason;
    info.className = "problem";
  }
  setTimeout(refresh, 300);
});

document.getElementById("save").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({
    kind: "popup_save",
    token: document.getElementById("token").value,
    port: document.getElementById("port").value,
  });
  setTimeout(refresh, 600);
});

refresh();
setInterval(refresh, 1000);
