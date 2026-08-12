# Vehicle License Plate Recognition for Unauthorized Entry Alert

The supported delivery mode is a localhost-only university prototype. The
backend defaults to loopback binding, loopback frontend origins, coherent
process-local memory repositories, and disabled-by-default experimental video:

```text
APP_MODE=localhost
REPOSITORY_MODE=memory
ENABLE_EXPERIMENTAL_VIDEO=false
```

Phase 6 short-video processing is available only after explicitly setting
`ENABLE_EXPERIMENTAL_VIDEO=true` in an isolated local process. It accepts
bounded `.mp4`, `.avi`, or `.mov` uploads (25 MiB, 10 seconds, 300 decoded
frames, 20 sampled frames, and 2-observation exact consensus by default).
It is not live streaming or production surveillance.

`APP_MODE=localhost` validates the supported application settings: `APP_HOST`
and configured frontend origins must be loopback values. This rule does not
claim to override an arbitrary host supplied directly to the Uvicorn CLI.

Historical Phase 1 focused verification contained 11 test functions and 12 collected test
cases: the localhost configuration file has 7 functions, including 1
two-case parameterized function, and the video file has 4 functions. The
repository-wide Ruff format check has one known pre-existing finding:
`backend/app/repositories/supabase_repo.py` would be reformatted. That file is
intentionally unchanged.

Choosing `REPOSITORY_MODE=supabase` is explicit, requires complete server-side
configuration, and never silently falls back to memory. Default unit tests
override ignored dotenv configuration before importing the application and
reject external network connections; no live service is required.

Phase 2 keeps the localhost repository contract canonical: vehicle persistence
uses `normalized_plate` and lowercase internal statuses, while public vehicle
responses retain uppercase statuses. Detection-log persistence retains the
complete OCR, decision, matched-vehicle, evidence, timing, and timestamp
fields. The optional Supabase adapter requires explicit schema-readiness
evidence and otherwise fails closed. Historical migration reconciliation is
blocked because the live migration ledger is unknown; see
[`docs/database_reconciliation.md`](../docs/database_reconciliation.md).

## Backend foundation

This directory contains the tested validation, detection, preprocessing, OCR,
decision, repository, and Day 11 logging/evidence service boundaries. The API
also exposes the Day 13 still-image orchestration route. The retained adapters
remain network-free and do not connect to Supabase.

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

Phase 4 recognition ranking is bounded and conservative. The defaults evaluate
at most three candidates, support configurable YGN/MDY/NPT prefixes, require a
numeric component and normalized length from 7 through 12, and use a 0.08
ambiguity margin. Unsupported prefixes, alphabetic watermark text such as
`ALAMY`, low-confidence OCR, and close competing candidates produce manual
review. These are workflow safeguards, not accuracy claims.

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

## Plate OCR and normalization

`POST /api/recognition/recognize-plate` accepts one already cropped plate image
through the same secure bounded JPEG/PNG validation flow. It does not run the
plate detector. Configure the review threshold and documented fallback:

```text
OCR_MIN_CONFIDENCE=0.80
OCR_FULL_PIPELINE_FALLBACK=true
```

The service initializes RapidOCR lazily on the first OCR request and reuses one
process-local instance. Recognition-only is always attempted first. When it is
empty or below the configured threshold, the optional Day 7 full pipeline is
attempted on the same untouched crop copy. All detection, classification, and
recognition sessions must report only ONNX Runtime `CPUExecutionProvider`.

The response contains raw text, normalized ASCII letters/digits, confidence,
selected mode, inference/total milliseconds, and `recognized` or
`manual_review`. Empty output uses `OCR_EMPTY`; below-threshold output uses
`OCR_LOW_CONFIDENCE`. Normalization removes whitespace, separators, and
unsupported characters but never guesses `O/0`. This endpoint does not
authorize, accuse, store, alert, or write files. See
[`docs/ocr_recognition.md`](../docs/ocr_recognition.md).

## Data model and repositories

Day 9 adds a versioned PostgreSQL/Supabase migration plus typed repository
interfaces and network-free in-memory repositories. It defines authorized
vehicle records, Day 8-compatible OCR detection logs, server-owned settings,
and optional evidence references. It does not connect API routes to Supabase,
persist requests, upload evidence, or make authorization decisions.

Validate the retained migration and mock contracts from the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\validate_schema.py
backend\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests -k repositor
```

See [`docs/database_schema.md`](../docs/database_schema.md) for exact table and
repository contracts, clean-project application guidance, private evidence
bucket/RLS requirements, limitations, and server-only credential rules.

## Authorization decision engine

Day 10 adds a pure service that consumes the Day 8 OCR response and Day 9
authorized-vehicle repository. Configure its independent inclusive threshold:

```text
DECISION_MIN_CONFIDENCE=0.80
```

Only reliable normalized OCR can be looked up. An active exact match inside
its timezone-aware validity interval returns `AUTHORIZED`; missing, inactive,
blocked, not-yet-valid, or expired records return explicit `UNAUTHORIZED`
reasons. Empty/low-confidence OCR, malformed data, time failures, and
repository failures return `MANUAL_REVIEW`. Messages are stable and
non-accusatory.

The service itself does not add an endpoint, persist a result, upload evidence,
send an alert, or operate a gate. Its already-produced result is the input to
the separate Day 11 logging service. See
[`docs/authorization_decision.md`](../docs/authorization_decision.md).

## Detection logging and private evidence

Day 11 extends detection logs with the exact Day 10 `decision`, stable
`decision_reason`, and optional matched vehicle UUID. The logging orchestrator
accepts an already-produced decision and never recalculates or changes it.
Annotation, private storage, metadata persistence, signed access, and
compensating cleanup failures are returned as stable sanitized codes.
The returned logging contract contains a frozen value snapshot rather than the
caller's mutable Day 10 model. Storage confirmations must match the requested
reference, byte count, and digest before metadata can refer to the object.
Mismatched claimed references are never cleanup targets. Compensating deletion
is successful only after a matching receipt and verified object absence;
otherwise the private reference remains available for trusted cleanup.

Evidence annotation copies the decoded source, draws only the selected plate
box plus decision/reason, and deterministically encodes a metadata-free JPEG
in memory. Generated paths use UUID components under a date prefix and never
use raw upload filenames. The in-memory storage adapter is locked, private,
network-free, and intended for tests/local development.

Trusted server configuration defaults are:

```text
EVIDENCE_STORAGE_BUCKET=detection-evidence
EVIDENCE_SIGNED_ACCESS_TTL_SECONDS=300
EVIDENCE_RETENTION_DAYS=30
```

Bucket names, signed-access lifetimes (60–3,600 seconds), and retention
(1–365 days) are validated. The contract returns an opaque short-lived token,
not a public object URL. In-memory grants are object-bound, expire
deterministically, and stop resolving after deletion. Live Supabase Storage,
an HTTP orchestration endpoint,
retention scheduling, and frontend access remain deferred. See
[`docs/detection_logging.md`](../docs/detection_logging.md).

## Still-image recognition orchestration

`POST /api/recognition/analyze` accepts one validated vehicle JPEG/PNG and
composes the existing detector, OCR/preprocessing, decision, logging, and
private-evidence boundaries. It returns an explicit no-plate result or the
selected primary crop, OCR values, authoritative frozen decision, correlation
ID, logging/evidence status, and timings. It never recalculates authorization
in the client or exposes a private evidence path/token as a browser URL.

The default Day 13 repositories/storage are process-local and network-free;
live Supabase persistence remains deferred. See
[`docs/recognition_interface.md`](../docs/recognition_interface.md).

The public recognition response exposes only `evidence_available`; private
bucket/object coordinates and signed grants remain inside trusted backend
boundaries.

## Dashboard, history, and alerts

Day 14 adds sanitized `GET /api/detections`,
`GET /api/detections/{correlation_id}`, `GET /api/dashboard/statistics`, and
`GET /api/alerts` endpoints. History supports bounded pagination, exact
decision/normalized-plate filters, and timezone-aware date bounds. Statistics
and alert selection are performed by the backend; trends use seven UTC calendar
days. Evidence is availability metadata only because authentication and
role-aware access are not implemented.

No-plate activity ledger failures do not change the recognition outcome. They
emit a warning containing only the correlation ID and stable
`NO_PLATE_ACTIVITY_PERSISTENCE_FAILED` category, never the raw exception or
private storage information.

Recognition and read routes share one locked process-local dependency
container. Restarting the backend may clear all records. This is not live
Supabase persistence. See
[`docs/dashboard_history_alerts.md`](../docs/dashboard_history_alerts.md).

## Windows PowerShell setup

Run these commands from the repository root (`D:\CVPX`):

```powershell
cd D:\CVPX
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements-dev.txt
```

Production and development requirements use explicit versions. Do not add an
unpinned fallback install or install a second OpenCV distribution to work
around metadata from a package dependency.

## Local container prerequisite

The detector requires the ignored local file `models/day4/best.onnx`. It is not
tracked or redistributed by this repository. Before a local Docker build,
provide that file in the build context and verify the documented size
(`12,265,233` bytes) and SHA-256
(`a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9`). The
Docker build fails closed when the file is absent or mismatched. Model license
and attribution verification remains an unresolved review item.

Docker is local-only in this phase. Publish the container on loopback, for
example `127.0.0.1:8000:8000`; do not treat the Dockerfile or `render.yaml` as
verified public deployment configuration.

The current local verification environment reports `opencv-python==5.0.0.93`,
while the clean-container manifest declares
`opencv-python-headless==4.12.0.88`. Clean-container compatibility remains
unverified; do not change the pinned headless dependency based only on the
local distribution.

The later local-only Docker commands are documented here but are not executed
in Phase 3:

```powershell
docker build --file backend/Dockerfile --tag cvpx-local:phase3 .
docker run --rm --publish 127.0.0.1:8000:8000 cvpx-local:phase3
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

The Day 7 research benchmark is separate from application startup and uses
ground-truth crops plus the Day 6 variants:

```powershell
python scripts\benchmark_ocr.py --help
python scripts\benchmark_ocr.py --input sample-data\evaluation
```

It writes raw evidence to `docs/day7_ocr_benchmark.json`. Importing the backend
does not initialize OCR. Day 8 application OCR remains lazy until
`recognize-plate` is called.

Alternatively, commands may be run from inside `backend\` after activating
the environment; in that case use `python -m uvicorn app.main:app` and
`python -m pytest tests`.

The virtual environment and `.env` files are local-only and ignored by Git.
Copy `backend\.env.example` to `backend\.env` only for local development;
the example contains no secrets. No deployment is configured by Day 2.

Day 15 exposes process-local authorized-vehicle management under
`/api/authorized-vehicles`. Normalization, uniqueness, validity, status, and later
authorization decisions remain backend-owned. See
`docs/authorized_vehicle_management.md`. This is not durable Supabase persistence.
