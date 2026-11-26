"""The installation self-test (used to validate packaged builds) with the real models."""

from __future__ import annotations

import json

import pytest

from interactive_scrolling.app import parse_args, self_test
from interactive_scrolling.storage.paths import DATA_DIR_ENV_VAR
from interactive_scrolling.vision.model_assets import MODELS, verify_model


def test_self_test_passes_without_camera(monkeypatch, tmp_path, capsys) -> None:
    if not all(verify_model(m.path(), m.sha256) for m in MODELS):
        pytest.skip("models not downloaded (scripts/download_model.py)")
    monkeypatch.setenv(DATA_DIR_ENV_VAR, str(tmp_path))
    assert parse_args(["--self-test"]).self_test
    assert self_test() == 0
    report = json.loads((tmp_path / "self-test.json").read_text(encoding="utf-8"))
    assert report["result"] == "PASS"
    assert report["hand_inference"].startswith("ok")
    assert report["face_inference"].startswith("ok")
    assert (tmp_path / "settings.json").is_file()
    assert "PASS" in capsys.readouterr().out
