// Service worker: connects to the local Interactive Scrolling desktop app over a loopback
// WebSocket, reports which YouTube Shorts tab (if any) is the current target, and relays the
// app's commands to that tab's content script.
//
// Security model:
// * Connects only to ws://127.0.0.1:<port>/bridge and authenticates with the pairing code
//   shown in the desktop app. The app accepts only this extension's origin.
// * Accepts exactly four commands (next/previous/like/toggle playback) and executes them only
//   in the active tab of the last focused browser window, and only if that tab is a visible
//   YouTube Shorts page showing the Short the app expects.
// * Host access is limited to https://www.youtube.com/*; other tabs' URLs are not readable.
"use strict";

const DEFAULT_PORT = 47815;
const PROTOCOL = 1;
const ACTIONS = new Set(["next_short", "previous_short", "like_short", "toggle_playback"]);

const tabStates = new Map(); // tabId -> { state, ts }
let socket = null;
let status = "starting";
let statusDetail = "";
let config = { token: "", port: DEFAULT_PORT };
let browserFocused = true;
let lastFocusTs = Date.now();
let reconnectTimer = null;
let lastContext = "";

function brand() {
  const brands = (navigator.userAgentData && navigator.userAgentData.brands) || [];
  const names = brands.map((b) => b.brand);
  if (names.includes("Microsoft Edge")) return "edge";
  if (names.includes("Google Chrome")) return "chrome";
  return "chromium";
}

function setStatus(value, detail) {
  status = value;
  statusDetail = detail || "";
  chrome.action.setBadgeText({ text: value === "connected" ? "ON" : "" }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ color: "#1f6b47" }).catch(() => {});
}

async function loadConfig() {
  const stored = await chrome.storage.local.get(["token", "port"]);
  config = {
    token: typeof stored.token === "string" ? stored.token : "",
    port: Number.isInteger(stored.port) ? stored.port : DEFAULT_PORT,
  };
}

function scheduleReconnect(delayMs) {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(connect, delayMs);
}

function send(message) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

async function connect() {
  clearTimeout(reconnectTimer);
  await loadConfig();
  if (!config.token) {
    setStatus("unpaired", "Enter the pairing code from the desktop app.");
    return;
  }
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
  setStatus("connecting");
  let ws;
  try {
    ws = new WebSocket(`ws://127.0.0.1:${config.port}/bridge`);
  } catch (error) {
    setStatus("offline", String(error));
    scheduleReconnect(5000);
    return;
  }
  socket = ws;
  ws.onopen = () => {
    send({
      type: "hello",
      protocol: PROTOCOL,
      token: config.token,
      browser: brand(),
      extension_version: chrome.runtime.getManifest().version,
    });
  };
  ws.onmessage = (event) => handleMessage(event.data);
  ws.onclose = (event) => {
    if (socket === ws) socket = null;
    if (event.code === 4001) {
      setStatus("rejected", "Pairing code not accepted by the desktop app.");
      scheduleReconnect(15000);
    } else {
      setStatus("offline", "Desktop app not reachable.");
      scheduleReconnect(3000);
    }
  };
  ws.onerror = () => {};
}

function handleMessage(raw) {
  let message;
  try {
    message = JSON.parse(raw);
  } catch {
    return;
  }
  if (!message || typeof message.type !== "string") return;
  switch (message.type) {
    case "welcome":
      setStatus("connected");
      lastContext = "";
      sendContext(true);
      break;
    case "ping":
      send({ type: "pong" });
      break;
    case "command":
      executeCommand(message);
      break;
    default:
      break;
  }
}

async function targetTab() {
  let win;
  try {
    win = await chrome.windows.getLastFocused({ windowTypes: ["normal"] });
  } catch {
    return null;
  }
  if (!win) return null;
  const [tab] = await chrome.tabs.query({ active: true, windowId: win.id });
  return tab || null;
}

async function currentContext() {
  const tab = await targetTab();
  const entry = tab ? tabStates.get(tab.id) : null;
  const shorts =
    tab && entry && entry.state.is_shorts && tab.url && tab.url.startsWith("https://www.youtube.com/shorts/")
      ? Object.assign({ tab_id: tab.id, age_ms: Date.now() - entry.ts }, entry.state)
      : null;
  return {
    type: "context",
    browser_focused: browserFocused,
    focus_ts: lastFocusTs,
    shorts,
  };
}

async function sendContext(force) {
  if (status !== "connected") return;
  const context = await currentContext();
  const key = JSON.stringify(Object.assign({}, context, { shorts: context.shorts && Object.assign({}, context.shorts, { age_ms: 0 }) }));
  if (!force && key === lastContext) return;
  lastContext = key;
  send(context);
}

async function executeCommand(message) {
  const { id, action, video_id: videoId, timeout_ms: timeoutMs } = message;
  const reply = (outcome, reason, extra) =>
    send(Object.assign({ type: "result", id, outcome, reason: reason || "" }, extra || {}));
  if (typeof id !== "string" || !ACTIONS.has(action)) return reply("rejected", "invalid command");
  const tab = await targetTab();
  const entry = tab ? tabStates.get(tab.id) : null;
  if (!tab || !entry || !entry.state.is_shorts || !tab.url || !tab.url.startsWith("https://www.youtube.com/shorts/")) {
    return reply("rejected", "no YouTube Shorts tab is active in the browser");
  }
  if (typeof videoId === "string" && entry.state.video_id !== videoId) {
    return reply("rejected", "the active Short changed before the action");
  }
  const timeout = Math.max(200, Math.min(Number(timeoutMs) || 2500, 5000));
  try {
    const response = await chrome.tabs.sendMessage(tab.id, {
      kind: "command",
      id,
      action,
      video_id: videoId,
      timeout_ms: timeout,
    });
    if (!response || typeof response.outcome !== "string") return reply("unknown", "no response from the page");
    reply(response.outcome, response.reason, {
      video_id_before: response.video_id_before || null,
      video_id_after: response.video_id_after || null,
      paused: typeof response.paused === "boolean" ? response.paused : null,
      liked: typeof response.liked === "boolean" ? response.liked : null,
    });
  } catch (error) {
    reply("unknown", `page did not answer (${String(error).slice(0, 80)})`);
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  if (message && message.kind === "shorts_state" && sender.tab) {
    tabStates.set(sender.tab.id, { state: message.state, ts: Date.now() });
    sendContext(false);
    return false;
  }
  if (message && message.kind === "popup_status") {
    sendResponse({ status, detail: statusDetail, port: config.port, paired: !!config.token });
    return false;
  }
  if (message && message.kind === "popup_save") {
    const token = String(message.token || "").trim();
    const port = Number.parseInt(message.port, 10);
    chrome.storage.local
      .set({ token, port: Number.isInteger(port) && port > 1023 && port < 65536 ? port : DEFAULT_PORT })
      .then(() => {
        if (socket) socket.close();
        socket = null;
        connect();
        sendResponse({ ok: true });
      });
    return true;
  }
  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => {
  tabStates.delete(tabId);
  sendContext(false);
});
chrome.tabs.onActivated.addListener(() => sendContext(false));
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  // A tab that navigates away must not keep its previous Shorts state until its new page
  // reports (the new page may not run the content script at all).
  if (changeInfo.url !== undefined || changeInfo.status === "loading") tabStates.delete(tabId);
  sendContext(false);
});
chrome.windows.onFocusChanged.addListener((windowId) => {
  browserFocused = windowId !== chrome.windows.WINDOW_ID_NONE;
  if (browserFocused) lastFocusTs = Date.now();
  sendContext(false);
});

// Heartbeat: keeps the context fresh on the app side and the service worker alive while
// connected (WebSocket activity extends the service worker lifetime).
setInterval(() => {
  if (status === "connected") sendContext(true);
  else if (!socket) connect();
}, 2000);

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();
