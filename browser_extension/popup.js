"use strict";

const LABELS = {
  connected: "Connected to the desktop app",
  connecting: "Connecting...",
  offline: "Desktop app not reachable (is it running?)",
  rejected: "Pairing code not accepted",
  unpaired: "Not paired yet",
  starting: "Starting...",
};

async function refresh() {
  const status = await chrome.runtime.sendMessage({ kind: "popup_status" });
  const element = document.getElementById("status");
  element.textContent = LABELS[status.status] || status.status;
  element.className = status.status === "connected" ? "connected" : "problem";
  if (!document.getElementById("port").value) document.getElementById("port").value = status.port;
}

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
