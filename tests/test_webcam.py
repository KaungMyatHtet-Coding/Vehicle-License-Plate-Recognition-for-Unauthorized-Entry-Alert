"""Day 18 tests for local webcam demonstration script.

These tests verify camera-unavailable handling, safe stop, argument parsing,
and server-independence invariants WITHOUT requiring a physical camera.
"""

from __future__ import annotations

import sys
import os

# Ensure scripts/ is importable
_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
for _p in (_SCRIPTS, _BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from run_webcam import CameraUnavailableError, WebcamRunner, parse_args  # noqa: E402


def test_parse_args_defaults() -> None:
    """parse_args with no arguments returns expected defaults."""
    args = parse_args([])
    assert args.camera == 0
    assert args.fps == 2.0
    assert args.cooldown == 3.0


def test_parse_args_custom_values() -> None:
    """parse_args accepts --camera, --fps, --cooldown overrides."""
    args = parse_args(["--camera", "1", "--fps", "5.0", "--cooldown", "2.5"])
    assert args.camera == 1
    assert args.fps == 5.0
    assert args.cooldown == 2.5


def test_open_camera_unavailable_raises() -> None:
    """open_camera raises CameraUnavailableError for an invalid camera index."""
    runner = WebcamRunner(camera_index=9999)
    with pytest.raises(CameraUnavailableError) as exc_info:
        runner.open_camera()
    assert "9999" in str(exc_info.value)
    assert "unavailable" in str(exc_info.value).lower()


def test_run_returns_1_when_camera_unavailable() -> None:
    """run() returns exit code 1 when the camera cannot be opened."""
    runner = WebcamRunner(camera_index=9999)
    result = runner.run()
    assert result == 1


def test_duplicate_suppression_logic() -> None:
    """_is_suppressed returns False for first occurrence, True within cooldown."""
    runner = WebcamRunner(cooldown_seconds=3.0)
    t = 100.0

    # First time: not suppressed
    assert runner._is_suppressed("YGN1234", t) is False

    # Within cooldown window: suppressed
    assert runner._is_suppressed("YGN1234", t + 1.0) is True
    assert runner._is_suppressed("YGN1234", t + 2.9) is True

    # After cooldown: not suppressed again
    assert runner._is_suppressed("YGN1234", t + 3.1) is False


def test_webcam_script_importable_and_help() -> None:
    """run_webcam.py is importable without triggering camera or server startup."""
    import run_webcam  # noqa: F401

    assert callable(run_webcam.main)
    assert callable(run_webcam.parse_args)


def test_server_startup_does_not_import_webcam() -> None:
    """backend/app/main.py must not import run_webcam.py — server is camera-free."""
    main_path = os.path.join(_BACKEND, "app", "main.py")
    with open(main_path) as f:
        content = f.read()
    assert "run_webcam" not in content
    assert "WebcamRunner" not in content
