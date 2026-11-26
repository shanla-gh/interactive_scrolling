"""Download and verify the MediaPipe hand landmarker model (one-time, ~7.8 MB).

Usage:
    python scripts/download_model.py            # into models/hand_landmarker.task
    python scripts/download_model.py --force    # re-download even if a valid copy exists
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from interactive_scrolling.vision.model_assets import (
    MODEL_SHA256,
    MODEL_URL,
    ModelDownloadError,
    default_model_path,
    download_model,
    verify_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=None, help="destination file")
    parser.add_argument("--force", action="store_true", help="download even if already valid")
    args = parser.parse_args()
    target = args.output or default_model_path()
    if not args.force and verify_model(target):
        print(f"Model already present and verified: {target}")
        return 0
    print(f"Downloading {MODEL_URL}")
    try:
        download_model(target)
    except ModelDownloadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Saved and verified (sha256 {MODEL_SHA256[:16]}...): {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
