// Offscreen document for the live Shorts preview.
//
// It receives the video of ONE tab that the user chose (tab capture started from the extension
// popup) and hands frames, with the crop rectangle of the playing Short, to a worker
// (preview_worker.js) that encodes them as small JPEG images and sends them to the desktop app
// over the loopback WebSocket. Nothing is recorded or stored.
//
// Privacy rules:
// * Only the rectangle of the Shorts video is sent, never the rest of the page.
// * Frames are sent only while the service worker reports that the captured tab shows a
//   YouTube Short; on any navigation away from Shorts sending stops immediately.
// * No audio is captured (the tab keeps playing its sound normally).
// * The capture ends when the user stops it (popup or app), the tab closes, the app
//   disconnects or the pairing code is not accepted.
"use strict";

const PROTOCOL = 3;
const MAX_HEIGHT = 640; // output height in pixels (the app shows the preview at about this size)
const MAX_FPS = 30;

let stream = null;
let reader = null;
let worker = null;
let welcomed = false;
let context = { shorts: false, rect: null };
let lastSentMs = 0;
let busy = false;
let lastState = "";
let stopped = true;
let pendingStart = null;

function sendText(payload) {
  if (worker) worker.postMessage({ kind: "text", payload });
}

function setState(state, reason) {
  const key = state + "|" + (reason || "");
  if (key === lastState) return;
  lastState = key;
  sendText({ type: "preview_state", state, reason: reason || "" });
}

function stop(reason) {
  if (stopped) return;
  stopped = true;
  setState("stopped", reason);
  if (reader) reader.cancel().catch(() => {});
  reader = null;
  if (stream) stream.getTracks().forEach((t) => t.stop());
  stream = null;
  if (worker) worker.postMessage({ kind: "close" });
  welcomed = false;
  if (pendingStart) {
    pendingStart({ ok: false, reason });
    pendingStart = null;
  }
  chrome.runtime.sendMessage({ kind: "preview_ended", reason }).catch(() => {});
}

function cropRect(frame) {
  // The page reports the video rectangle in CSS pixels of its viewport; the captured frame
  // shows the same viewport scaled to the frame size.
  // The browser fits the viewport into the requested capture size keeping its shape, with
  // black bars on two sides when the shapes differ (measured: a 1280x900 viewport arrives
  // pillarboxed in a 1280x720 frame).
  const r = context.rect;
  const fw = frame.displayWidth;
  const fh = frame.displayHeight;
  if (!r || !(r.vw > 0) || !(r.vh > 0)) return null;
  const scale = Math.min(fw / r.vw, fh / r.vh);
  const ox = (fw - r.vw * scale) / 2;
  const oy = (fh - r.vh * scale) / 2;
  const sx = Math.max(0, Math.round(ox + r.x * scale));
  const sy = Math.max(0, Math.round(oy + r.y * scale));
  const sw = Math.min(fw - sx, Math.round(r.w * scale));
  const sh = Math.min(fh - sy, Math.round(r.h * scale));
  if (sw < 16 || sh < 16) return null;
  return { sx, sy, sw, sh };
}

async function pump(track) {
  const processor = new MediaStreamTrackProcessor({ track });
  reader = processor.readable.getReader();
  for (;;) {
    let item;
    try {
      item = await reader.read();
    } catch {
      break;
    }
    if (item.done) break;
    const frame = item.value;
    const now = performance.now();
    if (!welcomed || busy || now - lastSentMs < 1000 / MAX_FPS - 4) {
      frame.close();
      continue;
    }
    if (!context.shorts) {
      setState("hidden", "the tab is not showing a YouTube Short");
      frame.close();
      continue;
    }
    const crop = cropRect(frame);
    if (!crop) {
      setState("hidden", "the Short is not on screen in the tab");
      frame.close();
      continue;
    }
    lastSentMs = now;
    busy = true;
    worker.postMessage({ kind: "frame", frame, crop, height: Math.min(MAX_HEIGHT, crop.sh) }, [
      frame,
    ]);
  }
  stop("the captured tab closed or stopped sharing");
}

function ensureWorker() {
  if (worker) return;
  worker = new Worker("preview_worker.js");
  worker.onmessage = (event) => {
    const message = event.data;
    if (message.kind === "welcome") {
      welcomed = true;
      if (pendingStart) {
        pendingStart({ ok: true });
        pendingStart = null;
      }
    } else if (message.kind === "encoded") {
      busy = false;
      if (message.sent) setState("streaming", "");
    } else if (message.kind === "app_stop") {
      stop("stopped in the desktop app");
    } else if (message.kind === "closed") {
      const reason = message.code === 4001 ? "pairing code not accepted" : "the desktop app disconnected";
      if (pendingStart) {
        pendingStart({ ok: false, reason: message.code === 4001 ? reason : "desktop app not reachable" });
        pendingStart = null;
      }
      stop(reason);
    }
  };
}

async function start({ streamId, port, token }) {
  if (!stopped) stop("restarted");
  stopped = false;
  lastState = "";
  busy = false;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        mandatory: {
          chromeMediaSource: "tab",
          chromeMediaSourceId: streamId,
          maxWidth: 1280,
          maxHeight: 720,
          maxFrameRate: MAX_FPS,
        },
      },
    });
  } catch (error) {
    stopped = true;
    return { ok: false, reason: `the browser refused the tab capture (${error && error.name})` };
  }
  const [track] = stream.getVideoTracks();
  track.addEventListener("ended", () => stop("the captured tab closed or stopped sharing"));
  ensureWorker();
  const connected = new Promise((resolve) => {
    pendingStart = resolve;
  });
  worker.postMessage({ kind: "connect", port, token, protocol: PROTOCOL });
  const result = await connected;
  if (!result.ok) return result;
  pump(track);
  return { ok: true };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || !message || message.target !== "preview") return false;
  if (message.kind === "start") {
    start(message).then(sendResponse);
    return true;
  }
  if (message.kind === "context") {
    context = { shorts: !!message.shorts, rect: message.rect || null };
    if (!context.shorts && welcomed) setState("hidden", "the tab is not showing a YouTube Short");
    return false;
  }
  if (message.kind === "stop") {
    stop(message.reason || "stopped");
    sendResponse({ ok: true });
    return false;
  }
  return false;
});
