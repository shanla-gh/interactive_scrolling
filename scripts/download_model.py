"""Download and verify the local MediaPipe models (one-time).

Usage:
    python scripts/download_model.py            # all models into models/
    python scripts/download_model.py --only hand
    python scripts/download_model.py --force    # re-download even if a valid copy exists
"""

from __future__ import annotations

import argparse
import sys

from interactive_scrolling.vision.model_assets import (
    MODELS,
    ModelDownloadError,
    download_model,
    verify_model,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=[m.key for m in MODELS], action="append")
    parser.add_argument("--force", action="store_true", help="download even if already valid")
    args = parser.parse_args()
    failed = 0
    for model in MODELS:
        if args.only and model.key not in args.only:
            continue
        target = model.path()
        if not args.force and verify_model(target, model.sha256):
            print(f"{model.description}: present and verified ({target})")
            continue
        print(f"{model.description}: downloading {model.url} ({model.size_bytes:,} bytes)")
        try:
            download_model(target, model.url, model.sha256)
        except ModelDownloadError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"  saved and verified (sha256 {model.sha256[:16]}...): {target}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
