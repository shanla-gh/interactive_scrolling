# M1 - Director verification record

Date recorded: 2026-11-26 (reported in Engineering Brief 002).

## What the Director reported

The Director launched the application, tested it with the physical webcam, provided a
screenshot of successful live hand tracking and reported that everything appears to work
correctly. The screenshot shows the operational webcam preview, the hand skeleton, the
landmarks, the bounding box, the handedness label and the motion analysis display.

No individual results for the items of the
[manual checklist](M1_MANUAL_VERIFICATION.md) were reported, so none are recorded as
individually passed below unless the screenshot or report directly covers them.

## Reconciliation with the checklist

| Checklist item | Director evidence | Other evidence |
|---|---|---|
| Start camera shows the live image | Covered (screenshot) | hardware tests |
| One raised hand: landmarks and skeleton on the hand | Covered (screenshot) | pixel-alignment tests |
| Handedness label shown | Covered (screenshot) | correctness on a real photo: `test_detects_two_real_hands_with_correct_handedness` |
| Motion analysis display | Covered (screenshot) | 37 motion tests; 87-88 px/s measured vs 86.7 px/s true |
| Stop, repeated start/stop, close releases camera | Not individually reported | hardware tests, two 10-minute sessions with 4 restarts each |
| Busy camera (another app holds it) | Not individually reported | simulated-device tests only |
| Scan, each resolution | Not individually reported | hardware tests (640x480, 1280x720), UI test for scan |
| Finger bending, two hands, hand leaving the frame, resizing, overlay toggles | Not individually reported | integration tests (alignment at 4 sizes, two-hand colours, lost-hand clearing, layer toggles) |
| Arrow and direction match perceived movement | Not individually reported | pixel test of arrow direction in both mirror modes |
| UI responsiveness | General report ("everything appears to work") | stability sessions (heartbeat p99 12-14 ms) |

## Decision

Every mandatory M1 acceptance criterion now has evidence: the visual criteria that need a
person (landmarks visibly aligned with the user's fingers, real-time skeleton) are covered by
the Director's live test and screenshot, and the remaining criteria by automated, hardware and
stability evidence. **M1 is closed as COMPLETED.**

Residual, non-blocking gaps (carried as known limitations): the busy-camera and
camera-disconnect paths have not been exercised on real hardware, and two-hand tracking and
handedness correctness on the Director's own hands were not explicitly confirmed.
