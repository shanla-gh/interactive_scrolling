"""MediaPipe result conversion and model asset handling (no model file required)."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from interactive_scrolling.config.settings import TrackingSettings
from interactive_scrolling.vision import model_assets
from interactive_scrolling.vision.hand_tracker import (
    MediaPipeHandTracker,
    ModelNotFoundError,
    convert_result,
)
from interactive_scrolling.vision.landmarks import Handedness
from interactive_scrolling.vision.model_assets import (
    ModelDownloadError,
    default_model_path,
    download_model,
    sha256_of,
    verify_model,
)


def lm(x: float, y: float, z: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(x=x, y=y, z=z, visibility=None, presence=None)


def category(name: str, score: float | None) -> SimpleNamespace:
    return SimpleNamespace(category_name=name, score=score, index=0, display_name=name)


def fake_result(hands: list[tuple[list, list, list | None]]) -> SimpleNamespace:
    return SimpleNamespace(
        hand_landmarks=[h[0] for h in hands],
        handedness=[h[1] for h in hands],
        hand_world_landmarks=[h[2] for h in hands if h[2] is not None],
    )


def test_convert_result_builds_observations() -> None:
    points = [lm(i / 21, 1 - i / 21, -0.01 * i) for i in range(21)]
    world = [lm(0.001 * i, 0.0, 0.0) for i in range(21)]
    result = fake_result([(points, [category("Right", 0.97)], world)])
    (hand,) = convert_result(result)
    assert hand.handedness is Handedness.RIGHT
    assert hand.handedness_score == pytest.approx(0.97)
    assert hand.landmarks.shape == (21, 3)
    assert hand.landmarks[20, 0] == pytest.approx(20 / 21)
    assert hand.landmarks[5, 2] == pytest.approx(-0.05)
    assert hand.world_landmarks is not None and hand.world_landmarks[3, 0] == pytest.approx(0.003)


def test_convert_result_uses_top_scoring_category() -> None:
    points = [lm(0.5, 0.5) for _ in range(21)]
    result = fake_result([(points, [category("Left", 0.3), category("Right", 0.6)], None)])
    (hand,) = convert_result(result)
    assert hand.handedness is Handedness.RIGHT


def test_convert_result_missing_handedness_is_unknown_not_invented() -> None:
    points = [lm(0.5, 0.5) for _ in range(21)]
    result = SimpleNamespace(hand_landmarks=[points], handedness=[], hand_world_landmarks=[])
    (hand,) = convert_result(result)
    assert hand.handedness is Handedness.UNKNOWN
    assert hand.handedness_score is None
    assert hand.world_landmarks is None


def test_convert_result_discards_malformed_hands() -> None:
    good = [lm(0.5, 0.5) for _ in range(21)]
    bad = [lm(0.5, 0.5) for _ in range(5)]
    result = fake_result(
        [(bad, [category("Left", 0.9)], None), (good, [category("Right", 0.9)], None)]
    )
    hands = convert_result(result)
    assert len(hands) == 1 and hands[0].handedness is Handedness.RIGHT


def test_convert_empty_result() -> None:
    assert (
        convert_result(SimpleNamespace(hand_landmarks=[], handedness=[], hand_world_landmarks=[]))
        == ()
    )


def test_missing_model_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ModelNotFoundError, match="download_model"):
        MediaPipeHandTracker(TrackingSettings(), tmp_path / "missing.task")


# ---------------------------------------------------------------------- model assets


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_download_model_verifies_and_installs(tmp_path: Path) -> None:
    import hashlib

    payload = b"model-bytes" * 1000
    digest = hashlib.sha256(payload).hexdigest()
    target = tmp_path / "models" / "hand_landmarker.task"
    download_model(
        target,
        url="https://example.invalid/m",
        expected_sha256=digest,
        opener=lambda url: FakeResponse(payload),
    )
    assert target.read_bytes() == payload
    assert verify_model(target, digest)
    assert sha256_of(target) == digest
    assert list(target.parent.iterdir()) == [target]  # no temporary files left


def test_download_model_rejects_corrupt_payload(tmp_path: Path) -> None:
    target = tmp_path / "hand_landmarker.task"
    with pytest.raises(ModelDownloadError, match="verification"):
        download_model(target, expected_sha256="0" * 64, opener=lambda url: FakeResponse(b"bad"))
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_download_model_network_error(tmp_path: Path) -> None:
    def failing(url: str) -> FakeResponse:
        raise OSError("no route to host")

    with pytest.raises(ModelDownloadError, match="no route"):
        download_model(tmp_path / "m.task", opener=failing)
    assert list(tmp_path.iterdir()) == []


def test_verify_model_missing_file(tmp_path: Path) -> None:
    assert not verify_model(tmp_path / "absent.task")


def test_default_model_path_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom.task"
    monkeypatch.setenv(model_assets.MODEL_ENV_VAR, str(custom))
    assert default_model_path() == custom


def test_default_model_path_points_into_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(model_assets.MODEL_ENV_VAR, raising=False)
    path = default_model_path()
    assert path.name == "hand_landmarker.task"
    assert path.parent.name == "models"


def test_pinned_model_url_is_versioned_https() -> None:
    assert model_assets.MODEL_URL.startswith("https://storage.googleapis.com/mediapipe-models/")
    assert "/float16/1/" in model_assets.MODEL_URL
    assert len(model_assets.MODEL_SHA256) == 64
