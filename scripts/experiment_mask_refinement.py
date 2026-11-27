"""Brief 007 M29: compare transparent-background mask refinements on a SYNTHETIC scenario.

No recording of a real person is available (and private footage is not collected), so the
scenario is generated: a head-and-shoulders figure whose light shirt gets *low* model
confidence in a patch (the reported "light clothing disappears against a dark background"),
per-frame noise in the confidence, and an arm that sweeps quickly across the frame. Metrics:

* ``hole``    - share of the low-confidence clothing patch shown (alpha >= 0.5); higher is better;
* ``leak``    - share of the background with alpha > 0.1; lower is better;
* ``flicker`` - mean frame-to-frame alpha change inside the still figure; lower is better;
* ``ghost``   - background area (px) still shown 0.1 s after the arm left it; lower is better;
* ``ms``      - compositing time per frame at the overlay size.

These numbers compare candidates; they do not measure the real model's quality, which needs
the Director's visual check with a real person.

Usage:
    python scripts/experiment_mask_refinement.py
"""

from __future__ import annotations

import time

import numpy as np

import interactive_scrolling.vision.compositing as comp

W, H = 480, 270
FPS = 15  # the segmentation worker runs at up to 15 fps


def scene(
    t: float, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(image, model confidence, true foreground, clothing patch) at time ``t``."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    head = ((xx - W * 0.5) / (W * 0.085)) ** 2 + ((yy - H * 0.36) / (H * 0.17)) ** 2 <= 1
    torso = ((xx - W * 0.5) / (W * 0.26)) ** 2 + ((yy - H * 1.02) / (H * 0.5)) ** 2 <= 1
    arm_x = W * (0.15 + 0.7 * ((t * 1.5) % 1.0))  # a fast sweep every 0.67 s
    arm = (np.abs(xx - arm_x) < W * 0.03) & (yy > H * 0.45) & (yy < H * 0.75)
    truth = head | torso | arm
    patch = torso & (np.abs(xx - W * 0.42) < W * 0.07) & (yy > H * 0.68)
    conf = np.where(truth, 0.9, 0.05).astype(np.float32)
    conf[patch] = 0.3  # light shirt: the model is unsure
    conf += rng.normal(0, 0.08, conf.shape).astype(np.float32)
    conf = np.clip(conf, 0, 1)
    image = np.empty((H, W, 3), np.uint8)
    image[...] = (40, 45, 60)
    image[truth] = (200, 200, 205)
    return image, conf, truth, patch


def run(name: str, **options: object) -> None:
    rng = np.random.default_rng(7)
    for key, value in options.items():
        setattr(comp, key, value)
    c = comp.MaskCompositor()
    holes, leaks, flicker, ghosts, ms = [], [], [], [], []
    prev = None
    history: list[np.ndarray] = []
    for i in range(int(4 * FPS)):
        t = i / FPS
        image, conf, truth, patch = scene(t, rng)
        start = time.perf_counter()
        rgba = c.compose(image, conf, int(t * 1e9), (W, H))
        ms.append((time.perf_counter() - start) * 1000)
        alpha = rgba[..., 3] / 255.0
        still = truth & ~(np.abs(np.mgrid[0:H, 0:W][1] - W * 0.5) > W * 0.3)
        if i > FPS:  # after the warm-up
            holes.append(float((alpha[patch] >= 0.5).mean()))
            background = ~truth
            leaks.append(float((alpha[background] > 0.1).mean()))
            if prev is not None:
                flicker.append(float(np.abs(alpha - prev)[still & ~patch].mean()))
            # ghost: shown pixels that were arm two frames ago and are background now
            if len(history) >= 2:
                was_arm = history[-2]
                ghosts.append(float(((alpha > 0.3) & was_arm & background).sum()))
        prev = alpha
        history.append(truth)
    print(
        f"{name:34} hole {np.mean(holes):5.2f}  leak {np.mean(leaks):6.4f}  "
        f"flicker {np.mean(flicker):6.4f}  ghost {np.mean(ghosts):7.1f} px  "
        f"{np.mean(ms):5.2f} ms"
    )


if __name__ == "__main__":
    base = {
        "FILL_HOLES": 0,
        "RISE": comp.SMOOTHING,
        "FALL": comp.SMOOTHING,
        "GUIDED": False,
        "ENCLOSED_FILL": 0.0,
    }
    run("current (ramp + EMA 0.5)", **base)
    run("hole filling (closing)", **{**base, "FILL_HOLES": 0.03})
    run("asymmetric EMA rise 0.7 fall 0.35", **{**base, "RISE": 0.7, "FALL": 0.35})
    run("guided filter edges", **{**base, "GUIDED": True})
    run("closing + asymmetric", **{**base, "FILL_HOLES": 0.03, "RISE": 0.7, "FALL": 0.35})
    run(
        "closing + asymmetric + guided",
        **{**base, "FILL_HOLES": 0.03, "RISE": 0.7, "FALL": 0.35, "GUIDED": True},
    )
    run("enclosed-hole fill (<= 10 %)", **{**base, "ENCLOSED_FILL": 0.10})
    run("enclosed-hole fill + guided", **{**base, "ENCLOSED_FILL": 0.10, "GUIDED": True})
