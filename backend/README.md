# Vehicle License Plate Recognition for Unauthorized Entry Alert

## Backend foundation

This directory contains the Day 2 FastAPI backend foundation plus the Day 3
transient image-input validation boundary. It validates image bytes and
returns metadata only; plate detection, OCR, authorization, persistent upload
storage, and deployment are later milestones and are intentionally not
implemented here.

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
```

Run tests from the repository root:

```powershell
python -m pytest backend\tests
```

The Day 3 validation tests generate tiny JPEG/PNG images in memory and require
no downloaded fixtures.

Alternatively, commands may be run from inside `backend\` after activating
the environment; in that case use `python -m uvicorn app.main:app` and
`python -m pytest tests`.

The virtual environment and `.env` files are local-only and ignored by Git.
Copy `backend\.env.example` to `backend\.env` only for local development;
the example contains no secrets. No deployment is configured by Day 2.
