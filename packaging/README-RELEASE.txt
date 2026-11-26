Interactive Scrolling - Windows release candidate (development build)

Start:      InteractiveScrolling.exe
Check:      InteractiveScrolling.exe --self-test   (no camera; writes self-test.json to
            %LOCALAPPDATA%\interactive_scrolling and returns exit code 0 on success)

Browser extension (for YouTube Shorts and tab control):
  1. Open edge://extensions (or chrome://extensions), enable Developer mode.
  2. Load unpacked -> select the "browser_extension" folder inside "_internal".
  3. Click the extension icon, paste the pairing code from the app's Browser tab.

Everything runs locally. Your settings and statistics are stored in
%LOCALAPPDATA%\interactive_scrolling. Licenses: LICENSE (MIT), THIRD_PARTY_NOTICES.md,
LICENSE-APACHE-2.0.txt (MediaPipe models).
