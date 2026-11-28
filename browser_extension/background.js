// Service worker: connects to the local Interactive Scrolling desktop app over a loopback
// WebSocket, reports which YouTube Shorts tab (if any) is the current target and whether the
// browser is the active application, relays Shorts commands to that tab's content script and
// performs tab navigation itself.
//
// Security model:
// * Connects only to ws://127.0.0.1:<port>/bridge and authenticates with the pairing code
//   shown in the desktop app. The app accepts only this extension's origin.
// * Accepts exactly six commands. The four Shorts commands (next/previous/like/toggle
//   playback) run only in the active tab of the last focused browser window, and only if that
//   tab is a visible YouTube Shorts page showing the Short the app expects.
// * The two tab commands activate the neighbouring tab of the focused browser window only:
//   never another window, never a wrap-around at the first or last tab, and only while a
//   window of this browser has the operating-system focus.
// * Host access is limited to https://www.youtube.com/*; other tabs' URLs and titles are not
//   readable and are never needed (tab navigation uses tab positions only).
//
// Live preview (protocol 3):
// * Started only by the user from this extension's popup on a YouTube Shorts tab (the
//   browser requires that click before a tab can be captured). That tab becomes the single
//   authorized preview tab until the preview stops.
// * The offscreen document (preview.js) sends only the video area of the Short, and only
//   while that tab shows a Short. No audio is captured.
// * While the preview runs, the app may address the four Shorts commands to the authorized
//   preview tab (field tab_id), so gestures work while the desktop app is in front. Any
//   other tab id is refused, and tab switching still needs the browser to be the active
//   window. Stopping the preview revokes this.
"use strict";

const DEFAULT_PORT = 47815;
const PROTOCOL = 3;
const SHORTS_ACTIONS = new Set(["next_short", "previous_short", "like_short", "toggle_playback"]);
const TAB_ACTIONS = new Set(["next_browser_tab", "previous_browser_tab"]);

const tabStates = new Map(); // tabId -> { state, ts }
let socket = null;
let status = "starting";
let statusDetail = "";
let config = { token: "", port: DEFAULT_PORT };
let browserFocused = true;
let lastFocusTs = Date.now();
let reconnectTimer = null;
let lastContext = "";
let preview = null; // { tabId, sinceTs } while a live preview is authorized
let previewDetail = "";

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

async function lastFocusedWindow(populate) {
  try {
    return (await chrome.windows.getLastFocused({ windowTypes: ["normal"], populate })) || null;
  } catch {
    return null;
  }
}

async function targetTab() {
  const win = await lastFocusedWindow(false);
  if (!win) return null;
  const [tab] = await chrome.tabs.query({ active: true, windowId: win.id });
  return tab || null;
}

async function currentContext() {
  // Whether a normal window of this browser has the operating-system focus right now. Read
  // from the window itself rather than only from focus events, which a restarted service
  // worker would have missed.
  const win = await lastFocusedWindow(false);
  browserFocused = !!(win && win.focused);
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
    preview: await previewContext(tab),
  };
}

function shortsStateOf(tab) {
  const entry = tab ? tabStates.get(tab.id) : null;
  if (!tab || !entry || !entry.state.is_shorts || !tab.url || !tab.url.startsWith("https://www.youtube.com/shorts/")) {
    return null;
  }
  return Object.assign({ tab_id: tab.id, age_ms: Date.now() - entry.ts }, entry.state);
}

async function previewTab() {
  if (!preview) return null;
  try {
    return await chrome.tabs.get(preview.tabId);
  } catch {
    return null;
  }
}

async function previewContext(activeTab) {
  if (!preview) return null;
  const tab = await previewTab();
  if (!tab) return null;
  return {
    tab_id: tab.id,
    in_front: !!(activeTab && activeTab.id === tab.id),
    shorts: shortsStateOf(tab),
  };
}

function tellPreview(message) {
  return chrome.runtime.sendMessage(Object.assign({ target: "preview" }, message)).catch(() => null);
}

async function forwardPreviewContext(urlChanged) {
  // The offscreen document sends frames only while the authorized tab shows a Short.
  if (!preview) return;
  const tab = await previewTab();
  const state = urlChanged ? null : shortsStateOf(tab);
  tellPreview({ kind: "context", shorts: !!state, rect: state ? state.video_rect || null : null });
}

async function ensureOffscreen() {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
  if (contexts.length) return;
  await chrome.offscreen.createDocument({
    url: "preview.html",
    reasons: ["USER_MEDIA"],
    justification: "Shows the playing YouTube Short in the Interactive Scrolling app on this computer.",
  });
}

async function closeOffscreen() {
  const contexts = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
  if (contexts.length) await chrome.offscreen.closeDocument().catch(() => {});
}

async function startPreview(tabId) {
  if (status !== "connected") return { ok: false, reason: "not connected to the desktop app" };
  let tab;
  try {
    tab = await chrome.tabs.get(tabId);
  } catch {
    return { ok: false, reason: "the tab is gone" };
  }
  if (!tab.active || !tab.url || !tab.url.startsWith("https://www.youtube.com/shorts/")) {
    return { ok: false, reason: "open a YouTube Short in this tab first" };
  }
  if (preview) await stopPreview("replaced by a new preview");
  let streamId;
  try {
    streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
  } catch (error) {
    return { ok: false, reason: `the browser did not allow the capture (${String(error).slice(0, 80)})` };
  }
  await ensureOffscreen();
  preview = { tabId, sinceTs: Date.now() };
  await chrome.storage.session.set({ previewTabId: tabId }).catch(() => {});
  await forwardPreviewContext(false);
  const result = await tellPreview({ kind: "start", streamId, port: config.port, token: config.token });
  if (!result || !result.ok) {
    preview = null;
    await chrome.storage.session.remove("previewTabId").catch(() => {});
    await closeOffscreen();
    previewDetail = (result && result.reason) || "the preview could not start";
    sendContext(true);
    return { ok: false, reason: previewDetail };
  }
  previewDetail = "";
  await forwardPreviewContext(false);
  sendContext(true);
  return { ok: true };
}

async function stopPreview(reason) {
  if (!preview) return;
  preview = null;
  previewDetail = reason || "";
  await chrome.storage.session.remove("previewTabId").catch(() => {});
  await tellPreview({ kind: "stop", reason });
  await closeOffscreen();
  sendContext(true);
}

async function sendContext(force) {
  if (status !== "connected") return;
  const context = await currentContext();
  const key = JSON.stringify(Object.assign({}, context, { shorts: context.shorts && Object.assign({}, context.shorts, { age_ms: 0 }) }));
  if (!force && key === lastContext) return;
  lastContext = key;
  send(context);
}

const handledCommands = new Set();

async function switchTab(action, reply) {
  const win = await lastFocusedWindow(true);
  if (!win || !win.focused || !Array.isArray(win.tabs)) {
    return reply("rejected", "the browser window is not active");
  }
  const tabs = win.tabs.slice().sort((a, b) => a.index - b.index);
  const current = tabs.find((t) => t.active);
  if (!current) return reply("rejected", "no active tab in the browser window");
  const step = action === "next_browser_tab" ? 1 : -1;
  const position = tabs.indexOf(current);
  const target = tabs[position + step];
  const counts = { tab_index_before: position, tab_count: tabs.length };
  if (!target) {
    const reason = step > 0 ? "already at the last tab" : "already at the first tab";
    return reply("rejected", reason, counts);
  }
  try {
    await chrome.tabs.update(target.id, { active: true });
  } catch (error) {
    return reply("failed", `the tab could not be activated (${String(error).slice(0, 60)})`, counts);
  }
  const [now] = await chrome.tabs.query({ active: true, windowId: win.id });
  if (now && now.id === target.id) {
    sendContext(true);
    return reply("succeeded", "", Object.assign(counts, { tab_index_after: position + step }));
  }
  return reply("failed", "the tab did not become active", counts);
}

async function executeCommand(message) {
  const { id, action, video_id: videoId, timeout_ms: timeoutMs } = message;
  const reply = (outcome, reason, extra) =>
    send(Object.assign({ type: "result", id, outcome, reason: reason || "" }, extra || {}));
  const known = SHORTS_ACTIONS.has(action) || TAB_ACTIONS.has(action);
  if (typeof id !== "string" || !known) return reply("rejected", "invalid command");
  if (handledCommands.has(id)) return reply("rejected", "duplicate command");
  handledCommands.add(id);
  if (handledCommands.size > 200) handledCommands.delete(handledCommands.values().next().value);
  if (TAB_ACTIONS.has(action)) return switchTab(action, reply);
  let tab;
  if (message.tab_id !== undefined && message.tab_id !== null) {
    // Preview session: only the one tab the user authorized from the popup.
    if (!preview || message.tab_id !== preview.tabId) {
      return reply("rejected", "not the tab shown in the live preview");
    }
    tab = await previewTab();
    if (!tab) return reply("rejected", "the previewed tab was closed");
  } else {
    tab = await targetTab();
  }
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
    if (preview && sender.tab.id === preview.tabId) forwardPreviewContext(false);
    sendContext(false);
    return false;
  }
  if (message && message.kind === "popup_status") {
    sendResponse({
      status,
      detail: statusDetail,
      port: config.port,
      paired: !!config.token,
      preview_tab: preview ? preview.tabId : null,
      preview_detail: previewDetail,
    });
    return false;
  }
  if (message && message.kind === "popup_preview_start" && Number.isInteger(message.tab_id)) {
    startPreview(message.tab_id).then(sendResponse);
    return true;
  }
  if (message && message.kind === "popup_preview_stop") {
    stopPreview("stopped in the browser").then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message && message.kind === "preview_ended" && !sender.tab) {
    // From the offscreen document: the capture ended (tab closed, stopped in the app,
    // app disconnected).
    if (preview) {
      preview = null;
      previewDetail = String(message.reason || "");
      chrome.storage.session.remove("previewTabId").catch(() => {});
      closeOffscreen();
      sendContext(true);
    }
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
  if (preview && tabId === preview.tabId) stopPreview("the previewed tab was closed");
  sendContext(false);
});
chrome.tabs.onActivated.addListener(() => sendContext(false));
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  // A tab that navigates away must not keep its previous Shorts state until its new page
  // reports (the new page may not run the content script at all).
  if (changeInfo.url !== undefined || changeInfo.status === "loading") {
    tabStates.delete(tabId);
    // Stop sending preview frames at once; they resume when the page reports a Short again.
    if (preview && tabId === preview.tabId) forwardPreviewContext(true);
    // The page's content script may already have reported its new state before this event
    // arrived (Shorts navigation is a single-page transition); ask it to report again so the
    // app does not see "no Shorts tab" until something else changes.
    chrome.tabs.sendMessage(tabId, { kind: "report_request" }).catch(() => {});
  }
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

// A restarted service worker forgets the preview; restore it while its capture still runs.
chrome.storage.session
  .get("previewTabId")
  .then(async (stored) => {
    if (!Number.isInteger(stored.previewTabId)) return;
    const contexts = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
    if (contexts.length) {
      preview = { tabId: stored.previewTabId, sinceTs: Date.now() };
      chrome.tabs.sendMessage(stored.previewTabId, { kind: "report_request" }).catch(() => {});
    } else {
      chrome.storage.session.remove("previewTabId");
    }
  })
  .catch(() => {});

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
connect();
