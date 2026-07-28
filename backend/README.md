# Vehicle License Plate Recognition for Unauthorized Entry Alert

## Backend foundation

This directory contains the Day 2 FastAPI foundation, Day 3 transient
image-input validation, and the Day 5 still-image plate-detection service. It
validates image bytes, locates zero/one/multiple plates, and returns transient
lossless crops. Day 6 adds configurable non-destructive preprocessing. OCR,
authorization, persistent upload storage, and deployment are later milestones
and are intentionally absent.

## Image validation

`POST /api/recognition/validate-image` accepts one multipart field named
`file`. JPEG (`.jpg`/`.jpeg`, `image/jpeg`) and PNG (`.png`, `image/png`) are
supported. The validator reads at most 10 MiB plus one byte, verifies decoded
format with Pillow, rejects corrupt/truncated/spoofed content, and enforces:

- minimum width and height: 32 pixels;
- maximum width and height: 10,000 pixels;
- maximum decoded area: 25,000,000 pixels.

Successful responses contain a correlation ID, original filename, content
type, detected format, byte size, width, and height. No file is persisted and
no plate result is produced. Invalid input returns a structured error with a
stable code, safe message, and correlation ID. These format and limit values
are Day 3 development assumptions because the project plan specifies the
validation categories but not exact values; they are configurable through the
backend environment example.

## Still-image plate detection

`POST /api/recognition/detect-plates` accepts the same `file` field and runs
the complete secure JPEG/PNG validation flow before detection. Configure the
ignored, locally verified Day 4 artifact through:

```text
DETECTOR_MODEL_PATH=models/day4/best.onnx
DETECTOR_CONFIDENCE_THRESHOLD=0.25
DETECTOR_NMS_IOU_THRESHOLD=0.45
```

The model path is environment-based; no model weight is tracked. The service
validates the selected artifact size/SHA and tensor/class contract, explicitly
requests ONNX Runtime `CPUExecutionProvider`, and initializes lazily on the
first detection request. The initialized detector is reused rather than
reloaded per request. Ordinary imports, `/health`, `/api/health`, and
`validate-image` therefore work without a local model.

A successful response contains the correlation ID, `detected` or
`no_plate_detected` status, count, original dimensions, inference/total
milliseconds, and confidence-sorted detections. Each bbox is original-image
`x1,y1,x2,y2` with exclusive right/bottom edges. Each crop is copied from the
original decoded pixels and transported as lossless base64 PNG with dimensions.
No upload or crop is persisted. Optional debug observation exists only as an
injected service sink; the application configures none and writes no debug
files.

Missing configuration/model files, failed artifact validation, unloadable
models, contract mismatches, and inference failures return HTTP 503 with a
stable structured code, safe message, and correlation ID. Invalid input keeps
the Day 3 status/code behavior.

## Plate preprocessing

`PlatePreprocessingService` accepts a Day 5 `uint8` grayscale or BGR crop and
an explicit `PreprocessingOptions` selection. Supported independent variants
are grayscale, aspect-preserving resize, bilateral denoise, CLAHE contrast,
Otsu threshold, deskew, and perspective correction. An empty selection returns
only a copied original, so there is no unconditional transformation chain.

The result preserves the original crop and returns original/stage dimensions,
channel count, dtype, parameters, per-stage milliseconds, and total
milliseconds. Deskew requires an explicit bounded angle. Perspective correction
requires explicit in-crop corners and a bounded output size; Day 6 does not
attempt unverified automatic geometry estimation.

The existing HTTP routes and response contracts are unchanged. This service is
the internal crop-to-variant boundary for later OCR work. See
[`docs/plate_preprocessing.md`](../docs/plate_preprocessing.md) for the exact
contract, legal-fixture visual example, limitations, and regeneration command.

## Windows PowerShell setup

Run these commands from the repository root (`D:\CVPX`):

```powershell
cd D:\CVPX
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements-dev.txt
```

Then remain at the repository root and start the development server:

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for Swagger UI. The canonical health check is
`http://127.0.0.1:8000/health` or:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

`/api/health` remains an undocumented compatibility alias and returns the same
deterministic response.

Validate a local image from the repository root:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/recognition/validate-image -F "file=@sample.jpg"
curl.exe -X POST http://127.0.0.1:8000/api/recognition/detect-plates -F "file=@sample.jpg"
```

Run tests from the repository root:

```powershell
python -m pytest backend\tests
```

The Day 3 validation tests generate tiny JPEG/PNG images in memory. Day 5
unit tests require no model; when the ignored verified Day 4 artifact is
present, the focused suite also exercises all generated evaluation fixtures.
Day 6 preprocessing tests require no model and use deterministic in-memory
arrays.

Alternatively, commands may be run from inside `backend\` after activating
the environment; in that case use `python -m uvicorn app.main:app` and
`python -m pytest tests`.

The virtual environment and `.env` files are local-only and ignored by Git.
Copy `backend\.env.example` to `backend\.env` only for local development;
the example contains no secrets. No deployment is configured by Day 2.
