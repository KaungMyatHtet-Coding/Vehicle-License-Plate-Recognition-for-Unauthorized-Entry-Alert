# Local Webcam Demo

`python scripts/run_webcam.py` is a standalone, localhost-only CLI for a
physical camera. It constructs the existing Phase 4 services directly and
does not send every frame through the public persistence-producing endpoint.
The backend server remains camera- and GUI-free.

## Usage

```powershell
python scripts\run_webcam.py --help
python scripts\run_webcam.py --camera 0 --fps 2 --cooldown 3
python scripts\run_webcam.py --camera -1
```

The CLI captures sampled frames, encodes bounded JPEG bytes, performs
non-persisting analysis, associates selected boxes by spatial IoU, and requires
two exact observations before persistence. `--consensus-window`,
`--agreement-count`, `--track-expiry`, `--max-tracks`, and `--iou-threshold`
are bounded local controls. No target FPS or recognition accuracy is promised.

## Safety behavior

- Tracks have a fixed maximum count, short expiry, and bounded observation
  window. They are never keyed only by OCR text.
- OCR must repeat the exact normalized text. Prefix/character disagreements,
  distinct reliable plates in one track, and unresolved candidates remain
  `MANUAL_REVIEW` and create no log or evidence.
- A stable normalized plate is checked against the backend decision service,
  then its own analyzed frame and correlation ID are persisted at most once
  during the cooldown. Suppression occurs before logging/evidence; cooldown is
  recorded only after `logging.log_persisted` succeeds, so failed events remain
  retryable. Cooldown state is bounded and expires.
- The overlay draws only the selected detector box after clipping it to the
  original frame. Invalid or zero-area boxes are skipped. It shows only safe
  workflow status and selected text, never evidence paths or provider details.
- Camera-open, frame-read, encoding, analysis, `Q`, Escape, and Ctrl+C paths
  release the camera and destroy OpenCV windows safely.

The direct in-process CLI uses the local memory repository by default. It is a
local demonstration and does not change still-image endpoint persistence
semantics. It does not implement webcam consensus in the backend server or
provide a public no-logging API flag.

## Controls and limitations

`Q` or Escape stops the window; Ctrl+C stops the terminal process. A missing
camera exits safely with code 1. Tests are camera-free and use deterministic
fake frames/services; they do not establish real-world accuracy.
