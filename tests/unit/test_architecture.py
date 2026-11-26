"""Static checks that module boundaries and dependency direction are respected."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "interactive_scrolling"

# Layer -> packages it must not import.
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "config": (
        "PySide6",
        "cv2",
        "mediapipe",
        "interactive_scrolling.vision",
        "interactive_scrolling.motion",
        "interactive_scrolling.core",
        "interactive_scrolling.ui",
        "interactive_scrolling.visualization",
    ),
    "core": (
        "PySide6",
        "mediapipe",
        "interactive_scrolling.ui",
        "interactive_scrolling.visualization",
    ),
    "vision": (
        "PySide6",
        "interactive_scrolling.motion",
        "interactive_scrolling.ui",
        "interactive_scrolling.visualization",
        "interactive_scrolling.core.pipeline",
    ),
    "motion": (
        "PySide6",
        "cv2",
        "mediapipe",
        "interactive_scrolling.ui",
        "interactive_scrolling.visualization",
        "interactive_scrolling.core.pipeline",
    ),
    "visualization": ("mediapipe", "cv2", "interactive_scrolling.ui"),
    "gestures": (
        "PySide6",
        "cv2",
        "mediapipe",
        "interactive_scrolling.ui",
        "interactive_scrolling.visualization",
        "interactive_scrolling.core.pipeline",
        "interactive_scrolling.actions",
        "interactive_scrolling.integrations",
        "interactive_scrolling.storage",
    ),
    "actions": (
        "PySide6",
        "cv2",
        "mediapipe",
        "interactive_scrolling.ui",
        "interactive_scrolling.integrations",
        "interactive_scrolling.storage",
        "interactive_scrolling.core.pipeline",
    ),
    "storage": ("PySide6", "cv2", "mediapipe", "interactive_scrolling.ui"),
    "wellbeing": (
        "PySide6",
        "cv2",
        "mediapipe",
        "interactive_scrolling.ui",
        "interactive_scrolling.visualization",
        "interactive_scrolling.core.pipeline",
        "interactive_scrolling.integrations",
    ),
    "integrations/youtube": (
        "PySide6",
        "cv2",
        "mediapipe",
        "interactive_scrolling.ui",
        "interactive_scrolling.gestures",
        "interactive_scrolling.storage",
    ),
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _cases() -> list[tuple[str, Path]]:
    return [(layer, f) for layer in FORBIDDEN for f in sorted((PACKAGE / layer).glob("*.py"))]


@pytest.mark.parametrize(("layer", "path"), _cases(), ids=lambda v: getattr(v, "name", v))
def test_layer_does_not_import_forbidden_modules(layer: str, path: Path) -> None:
    for module in imported_modules(path):
        for forbidden in FORBIDDEN[layer]:
            assert not (module == forbidden or module.startswith(forbidden + ".")), (
                f"{path.relative_to(PACKAGE)} imports {module}, which the '{layer}' layer "
                f"must not depend on"
            )


def test_mediapipe_is_confined_to_the_model_adapters() -> None:
    # Brief 003 added two optional models; each has its own adapter in vision/.
    offenders = sorted(
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*.py")
        if any(m.split(".")[0] == "mediapipe" for m in imported_modules(path))
    )
    assert offenders == sorted(
        str(Path("vision") / name)
        for name in ("hand_tracker.py", "segmenter.py", "face_tracker.py")
    )
