# PyInstaller build definition (one-folder Windows build).
#
#   .venv\Scripts\python.exe -m PyInstaller packaging\interactive_scrolling.spec --noconfirm
#
# Output: dist\InteractiveScrolling\InteractiveScrolling.exe (+ _internal\). The three MediaPipe
# models (verified by SHA-256 before building), the browser extension, the license and the
# third-party notices are bundled, so the build runs offline without a Python installation.
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

from interactive_scrolling.vision.model_assets import MODELS, verify_model

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 (provided by PyInstaller)

for model in MODELS:
    if not verify_model(model.path(), model.sha256):
        raise SystemExit(f"{model.filename} missing or invalid: run scripts/download_model.py")

datas, binaries, hiddenimports = [], [], []
for package in ("mediapipe",):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

datas += [(str(model.path()), "models") for model in MODELS]
datas += [
    (str(ROOT / "browser_extension"), "browser_extension"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "docs" / "THIRD_PARTY_NOTICES.md"), "."),
    (str(ROOT / "packaging" / "LICENSE-APACHE-2.0.txt"), "."),
    (str(ROOT / "packaging" / "README-RELEASE.txt"), "."),
]

a = Analysis(  # noqa: F821
    [str(ROOT / "src" / "interactive_scrolling" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InteractiveScrolling",
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="InteractiveScrolling",
)
