# Windows release candidate (M11)

## Packaging approach

PyInstaller one-folder build (`packaging/interactive_scrolling.spec`, `scripts/build.ps1`):
`InteractiveScrolling.exe` plus an `_internal` folder with Python, PySide6, MediaPipe, OpenCV,
the three verified models, the browser extension, `LICENSE`, `THIRD_PARTY_NOTICES.md` and the
Apache 2.0 license text. Users do not need Python. One folder (not one file) because a
one-file build unpacks ~365 MB to a temporary folder on every start; an installer (MSIX/Inno
Setup) was not added for the release candidate: unzip-and-run is simpler and needs no admin
rights or signing.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
# -> dist\InteractiveScrolling\InteractiveScrolling.exe
# -> dist\InteractiveScrolling-0.3.0rc1-windows-x64.zip
```

Not signed: Windows SmartScreen may warn on first start ("More info" -> "Run anyway").

## Clean-environment validation (2026-11-26, development machine)

Build copied to a new folder outside the repository, `LOCALAPPDATA` pointed to an empty
temporary folder (fresh user data), no `PYTHONPATH`:

| Check | Result |
|---|---|
| Build size | 365 MB (one folder) |
| `InteractiveScrolling.exe --self-test` | PASS, exit code 0: three models found inside the build and verified (SHA-256); hand, segmentation and face inference on a synthetic image offline; settings file and statistics database created |
| First self-test (before the fix) | FAIL: `No module named 'matplotlib'` - MediaPipe imports it at import time and the spec had excluded it. Fixed in the spec, rebuilt, passed. |
| GUI start | main window shown after < 10 s, 230 MB working set |
| Graceful close | exit code 0 within 15 s, no process left |

Limits of this validation: same machine and Windows installation (system DLLs, Visual C++
runtime and camera drivers present); the camera and the browser extension were not exercised
from the packaged build. A second, clean Windows computer is part of the Director checklist
(section 8). Browser extension installation stays manual (*Load unpacked*); it is not published
to any extension store.

## Release status

0.3.0rc1 is a **release candidate**, not a stable release. No release tag was created and
nothing was uploaded. A stable 1.0 requires the Director acceptance checklist
(`docs/milestones/DIRECTOR_ACCEPTANCE_CHECKLIST.md`).
