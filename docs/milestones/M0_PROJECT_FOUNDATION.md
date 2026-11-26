# M0 - Project Foundation

Status: **COMPLETED** (2026-11-26)

## CP 0.1 - Workspace and GitHub initialization: COMPLETED

Findings at start:

| Item | Finding |
|---|---|
| Local workspace | `E:\interactive_scrolling` existed and was empty; no Git repository |
| Remote | `https://github.com/shanla-gh/interactive_scrolling` existed, reachable, **no commits** (`git ls-remote` returned no refs) |
| Git identity | owner's existing global identity (`user.name` = `shanla-gh`); not modified |
| Authentication | Git Credential Manager (`credential.helper=manager`); GitHub CLI not installed |
| Python | 3.12.10 (Microsoft Store build, `py -3.12`), 3.11.9 (python.org) |
| Hardware | Intel Core i7-13700H (14 cores / 20 threads), 15.6 GB RAM, one integrated "HP HD Camera" |

Actions: `git init -b main`, `origin` set to the remote. Because the remote had no history,
no merge was required. No destructive operation was performed.

## CP 0.2 - Technology stack and architecture: COMPLETED

* Python 3.12 in a project-local `.venv`; exact pins in `requirements*.txt`.
* mediapipe 1.2.3, opencv-contrib-python 4.12.0.88, numpy 2.2.6, PySide6 6.10.3, psutil 7.2.2;
  dev: pytest 9.0.3, pytest-qt 4.5.0, ruff 0.15.22. Versions were chosen from what is
  available, checked against package metadata and verified by running the real model and
  camera on the target machine (see ADR-001 to ADR-003).
* Architecture and layering: `docs/architecture/ARCHITECTURE.md`, decisions in
  `docs/architecture/DECISIONS.md`, layering enforced by `tests/unit/test_architecture.py`.
* Licensing: MIT for the project; all dependency licenses reviewed from package metadata; the
  model's Apache 2.0 license confirmed from Google's official model card PDF
  (`docs/THIRD_PARTY_NOTICES.md`).

## CP 0.3 - Testing and development infrastructure: COMPLETED

* pytest with `unit`, `integration`, `regression` and `hardware` suites; markers `hardware`,
  `model`, `network`; webcam tests are skipped unless `--hardware` is passed.
* ruff format + lint configured in `pyproject.toml`.
* `scripts/setup.ps1`, `scripts/run.ps1`, `scripts/test.ps1`; entry points
  `interactive-scrolling` and `python -m interactive_scrolling`.
* GitHub Actions workflow `.github/workflows/ci.yml` (Windows, Python 3.12): format check,
  lint, model download with SHA-256 verification, hardware-independent tests. CI validation
  result is recorded in `PROJECT_STATUS.md`.

## CP 0.4 - Persistent project documentation: COMPLETED

`README.md`, `ROADMAP.md`, `PROJECT_STATUS.md`, `CHANGELOG.md`, `CONTRIBUTING.md`,
`docs/ENGINEERING_CONVENTIONS.md` (persistent rules for future sessions, including the
attribution and privacy rules), `docs/THIRD_PARTY_NOTICES.md`, architecture documents.
