# Vehicle License Plate Recognition for Unauthorized Entry Alert

## Backend foundation

This directory contains the Day 2 FastAPI backend foundation. It currently
provides only public API information, a deterministic health endpoint, safe
development configuration, structured validation errors, and endpoint tests.
Plate detection, OCR, authorization, persistence, uploads, and deployment are
later milestones and are intentionally not implemented here.

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

Run tests from the repository root:

```powershell
python -m pytest backend\tests
```

Alternatively, commands may be run from inside `backend\` after activating
the environment; in that case use `python -m uvicorn app.main:app` and
`python -m pytest tests`.

The virtual environment and `.env` files are local-only and ignored by Git.
Copy `backend\.env.example` to `backend\.env` only for local development;
the example contains no secrets. No deployment is configured by Day 2.
