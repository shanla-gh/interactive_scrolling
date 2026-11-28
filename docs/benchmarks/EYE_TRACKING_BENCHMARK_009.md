# Eye tracking benchmark - Brief 009

| Check | Data | Result |
|---|---|---|
| Gaze estimate geometry | synthetic landmarks (`tests/unit/test_gaze.py`) | centred irises -> 0 deg (+-0.5); iris offset 0.1 eye widths -> 13.8 deg; head yaw 20 deg -> 20 deg; iris up -> positive pitch |
| Quality gating | synthetic | blink 0.9 and head yaw 55 deg -> unusable; missing head angles or face -> no estimate |
| Overlay direction and mirroring | synthetic render | arrow points to the person's left (image right) and flips in the mirrored view |
| Overlay on a face-like image | canonical face mesh (no person), `screenshots/brief009/gaze/` | straight, eyes left (+17 deg), head turned (+25 deg), up, blink (hidden) |
| Cost | full-app replay with the face model running (PERFORMANCE_009.md) | hand recognition latency unchanged (10.2 ms median with eye analytics vs 10.4 basic Broadcast) |
| Calibration accuracy (pixel error, region accuracy, availability, drift) | **none** - needs a person | tool ready: `scripts/evaluate_gaze_calibration.py` |
| Robustness (glasses, lighting, distance, rotation, fast head movement) | **none** - needs a person | - |

No claim of eye-tracker accuracy is made. Real-person measurements are part of
BRIEF_009_VALIDATION.md.
