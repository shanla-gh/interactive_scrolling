// YouTube Shorts page logic: read the state of the active Short and perform one action with
// confirmation. Loaded as a content script on www.youtube.com only. No data leaves the page
// except the small state/result objects passed to the extension's service worker.
//
// Selectors verified against the live YouTube Shorts page (Chrome 158, Nov 2026). YouTube
// changes its markup over time; every action therefore confirms its effect from page state
// and reports "unknown" or "failed" rather than assuming success.
(function () {
  "use strict";

  const SHORTS_PATH = /^\/shorts\/([A-Za-z0-9_-]{6,})/;

  function videoIdFromLocation() {
    const match = SHORTS_PATH.exec(window.location.pathname);
    return match ? match[1] : null;
  }

  function isVisible(element) {
    return !!element && element.getClientRects().length > 0 && element.offsetParent !== null;
  }

  function activeVideo() {
    const candidates = [
      ...document.querySelectorAll("ytd-reel-video-renderer[is-active] video"),
      ...document.querySelectorAll("#shorts-player video"),
    ];
    return candidates.find((v) => v.clientWidth > 0 && v.clientHeight > 0) || null;
  }

  function likeButton() {
    const scoped = document.querySelector(
      "ytd-reel-video-renderer[is-active] like-button-view-model button[aria-pressed]"
    );
    if (scoped) return scoped;
    const all = [...document.querySelectorAll("like-button-view-model button[aria-pressed]")];
    return all.find(isVisible) || all[0] || null;
  }

  function navigationButton(direction) {
    const host = document.querySelector(`#navigation-button-${direction}`);
    return host ? host.querySelector("button") : null;
  }

  function signedIn() {
    if (document.querySelector("#avatar-btn, button#avatar-btn")) return true;
    if (document.querySelector('a[aria-label="Sign in"], a[href*="accounts.google.com/ServiceLogin"]'))
      return false;
    return null;
  }

  function readState() {
    const id = videoIdFromLocation();
    const video = id ? activeVideo() : null;
    const like = id ? likeButton() : null;
    return {
      is_shorts: id !== null,
      video_id: id,
      visible: document.visibilityState === "visible",
      has_video: video !== null,
      // YouTube ignores navigation until the active video has loaded (verified on the live
      // site), so actions wait for HAVE_CURRENT_DATA.
      video_ready: video !== null && video.readyState >= 2,
      paused: video ? video.paused : null,
      liked: like ? like.getAttribute("aria-pressed") === "true" : null,
      signed_in: id ? signedIn() : null,
    };
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function waitFor(predicate, timeoutMs, stepMs = 40) {
    const deadline = performance.now() + timeoutMs;
    while (performance.now() < deadline) {
      const value = predicate();
      if (value) return value;
      await sleep(stepMs);
    }
    return predicate();
  }

  function result(outcome, reason, extra) {
    return Object.assign({ outcome, reason: reason || "" }, extra || {});
  }

  function isDisabled(button) {
    return button.disabled || button.getAttribute("aria-disabled") === "true";
  }

  async function navigate(direction, timeoutMs) {
    const before = videoIdFromLocation();
    const button = navigationButton(direction);
    if (!button || !isVisible(button)) {
      return result(
        "rejected",
        direction === "up" ? "no previous Short available" : "no next Short available"
      );
    }
    if (isDisabled(button)) {
      return result(
        "rejected",
        direction === "up" ? "already at the first Short" : "no next Short available"
      );
    }
    button.click();
    const changed = await waitFor(() => {
      const now = videoIdFromLocation();
      return now && now !== before ? now : null;
    }, timeoutMs);
    if (changed) return result("succeeded", "", { video_id_before: before, video_id_after: changed });
    return result("failed", "the active Short did not change", { video_id_before: before });
  }

  function dismissSignInDialog() {
    const dialog = [...document.querySelectorAll("ytd-modal-with-title-and-button-renderer, [role=dialog]")]
      .find((el) => isVisible(el) && /sign in/i.test(el.innerText || ""));
    if (!dialog) return false;
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    const backdrop = document.querySelector("tp-yt-iron-overlay-backdrop.opened");
    if (backdrop) backdrop.click();
    return true;
  }

  async function like(timeoutMs) {
    const button = await waitFor(likeButton, Math.min(1000, timeoutMs));
    if (!button) return result("failed", "like button not found");
    if (button.getAttribute("aria-pressed") === "true") {
      return result("no_change", "already liked");
    }
    if (signedIn() === false) {
      // Clicking would only open YouTube's sign-in prompt; never attempt authentication.
      return result("rejected", "not signed in to YouTube");
    }
    button.click();
    const liked = await waitFor(() => button.isConnected && button.getAttribute("aria-pressed") === "true", timeoutMs);
    if (liked) return result("succeeded", "", { liked: true });
    if (dismissSignInDialog()) return result("rejected", "YouTube asked to sign in");
    return result("unknown", "like state did not confirm within the time limit");
  }

  async function togglePlayback(timeoutMs) {
    const video = activeVideo();
    if (!video) return result("rejected", "no active video");
    const wasPaused = video.paused;
    try {
      if (wasPaused) await video.play();
      else video.pause();
    } catch (error) {
      return result("failed", `the browser blocked playback (${error && error.name})`);
    }
    const flipped = await waitFor(() => video.paused !== wasPaused, timeoutMs);
    if (flipped) return result("succeeded", "", { paused: video.paused });
    return result("failed", "playback state did not change", { paused: video.paused });
  }

  const ACTIONS = {
    next_short: (t) => navigate("down", t),
    previous_short: (t) => navigate("up", t),
    like_short: (t) => like(t),
    toggle_playback: (t) => togglePlayback(t),
  };

  async function perform(action, expectedVideoId, timeoutMs) {
    const handler = ACTIONS[action];
    if (!handler) return result("rejected", "unsupported action");
    const state = readState();
    if (!state.is_shorts) return result("rejected", "the active tab is not a YouTube Short");
    if (!state.visible) return result("rejected", "the Shorts tab is not visible");
    if (expectedVideoId && state.video_id !== expectedVideoId) {
      return result("rejected", "the active Short changed before the action");
    }
    if (action !== "like_short" && !state.video_ready) {
      return result("rejected", "the Short is still loading");
    }
    return handler(Math.max(200, Math.min(timeoutMs || 2500, 5000)));
  }

  globalThis.InteractiveScrollingShorts = { readState, perform, videoIdFromLocation };
})();
