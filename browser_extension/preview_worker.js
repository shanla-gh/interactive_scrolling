// Worker of the offscreen preview document: crops, encodes and sends the frames.
//
// Encoding runs here because the offscreen document itself is a hidden page whose tasks the
// browser throttles (measured: about one encoded frame per second on the main thread).
"use strict";

const QUALITY = 0.72;
const MAX_BUFFERED = 768 * 1024;

let ws = null;
let canvas = null;
let ctx = null;
let frameNumber = 0;

function post(message) {
  self.postMessage(message);
}

function connect(port, token, protocol) {
  ws = new WebSocket(`ws://127.0.0.1:${port}/preview`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => ws.send(JSON.stringify({ type: "preview_hello", protocol, token }));
  ws.onmessage = (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return;
    }
    if (message.type === "preview_welcome") post({ kind: "welcome" });
    else if (message.type === "preview_stop") post({ kind: "app_stop" });
  };
  ws.onclose = (event) => {
    ws = null;
    post({ kind: "closed", code: event.code });
  };
  ws.onerror = () => {};
}

async function encode(frame, crop, height) {
  try {
    if (!ws || ws.readyState !== WebSocket.OPEN || ws.bufferedAmount > MAX_BUFFERED) return false;
    const width = Math.max(2, Math.round((crop.sw * height) / crop.sh));
    if (!canvas) {
      canvas = new OffscreenCanvas(width, height);
      ctx = canvas.getContext("2d", { alpha: false });
    } else if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    ctx.drawImage(frame, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, width, height);
    const capturedMs = performance.timeOrigin + performance.now();
    frame.close();
    frame = null;
    const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: QUALITY });
    const jpeg = new Uint8Array(await blob.arrayBuffer());
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const packet = new Uint8Array(12 + jpeg.length);
    const view = new DataView(packet.buffer);
    view.setFloat64(0, capturedMs, true);
    view.setUint32(8, ++frameNumber, true);
    packet.set(jpeg, 12);
    ws.send(packet.buffer);
    return true;
  } finally {
    if (frame) frame.close();
  }
}

self.onmessage = (event) => {
  const message = event.data;
  if (message.kind === "connect") {
    frameNumber = 0;
    connect(message.port, message.token, message.protocol);
  } else if (message.kind === "frame") {
    encode(message.frame, message.crop, message.height)
      .catch(() => false)
      .then((sent) => post({ kind: "encoded", sent }));
  } else if (message.kind === "text") {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message.payload));
  } else if (message.kind === "close") {
    if (ws) ws.close(1000, "preview stopped");
  }
};
