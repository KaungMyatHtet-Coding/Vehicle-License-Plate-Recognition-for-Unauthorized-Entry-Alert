# Webcam Demo — Day 18

## Overview

`scripts/run_webcam.py` is a **standalone local CLI script** that runs OpenCV-based license plate recognition on a physical camera attached to your machine.

> **IMPORTANT:** The backend API server (`uvicorn`) does NOT require a camera to start. This script is entirely isolated from the server process.

---

## Usage

```powershell
# Show all options
python scripts\run_webcam.py --help

# Run with default camera (index 0)
python scripts\run_webcam.py

# Run with a specific camera index
python scripts\run_webcam.py --camera 1

# Test camera-unavailable error handling (safe)
python scripts\run_webcam.py --camera -1

# Custom FPS and cooldown
python scripts\run_webcam.py --camera 0 --fps 3 --cooldown 2.0
```

## Options

| Option | Default | Description |
|---|---|---|
| `--camera INDEX` | `0` | OpenCV camera index |
| `--fps FPS` | `2.0` | Recognition frames per second |
| `--cooldown SECONDS` | `3.0` | Duplicate suppression window |

---

## On-Screen Overlays

| Element | Position | Content |
|---|---|---|
| **FPS / Latency** | Top-left | Live capture FPS and inference latency in ms |
| **Plate + Decision** | Bottom bar | Detected plate text and AUTHORIZED/UNAUTHORIZED decision |
| **Duplicate label** | Bottom bar | `(dup)` suffix + `[suppressed]` when cooldown active |

---

## Controls

| Key | Action |
|---|---|
| `Q` or `Escape` | Stop the demo cleanly |
| `Ctrl+C` (terminal) | Graceful shutdown |

---

## Camera-Unavailable Handling

When no camera is attached or the requested index is invalid:

```
[WebcamDemo] Camera unavailable: Camera index 9999 is unavailable or not connected.
[WebcamDemo] NOTE: The backend API server does not require a camera to start.
```

The script exits with code **1** (error) without crashing or hanging.

---

## Architecture

```
scripts/run_webcam.py           ← Standalone CLI entry point
  └── WebcamRunner              ← Camera loop, overlay drawing, cooldown
        └── RecognitionOrchestrationService  ← Shared Day 16 pipeline
              ├── PlateDetectionService       ← YOLO/CV detector
              ├── PlateOcrService             ← OCR model
              ├── AuthorizationDecisionService
              └── DetectionLoggingService
```

The `run_webcam.py` script adds the `backend/` directory to `sys.path` at runtime; no changes to server imports are required.

---

## Running Tests

```powershell
# Day 18 focused tests only
python -m pytest tests -k webcam -v

# Full suite (Day 1–18 regression)
python -m pytest
```

### What the Tests Verify

| Test | Description |
|---|---|
| `test_parse_args_defaults` | Default CLI argument values |
| `test_parse_args_custom_values` | Custom `--camera`, `--fps`, `--cooldown` |
| `test_open_camera_unavailable_raises` | `CameraUnavailableError` for invalid index |
| `test_run_returns_1_when_camera_unavailable` | Exit code 1, no crash |
| `test_duplicate_suppression_logic` | Cooldown window logic |
| `test_webcam_script_importable_and_help` | Script importable without side effects |
| `test_server_startup_does_not_import_webcam` | `main.py` is camera-free |
