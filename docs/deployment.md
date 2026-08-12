# Local deployment boundary

Phase 3 supports a reproducible localhost prototype only. Render, Vercel, and
live Supabase deployment are deferred and unsupported for the current
submission. No public deployment success is claimed.

## Backend

The backend runs on loopback by default:

```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The canonical health check is `http://127.0.0.1:8000/health`. The Docker
container listens on its internal configurable `PORT`; publish it only to the
host loopback interface, for example:

```text
127.0.0.1:8000:8000
```

The later local-only Docker commands are documented here but are not executed
in Phase 3:

```powershell
docker build --file backend/Dockerfile --tag cvpx-local:phase3 .
docker run --rm --publish 127.0.0.1:8000:8000 cvpx-local:phase3
```

The health endpoint remains independent of model loading and database access.
The application remains in memory repository mode by default, and the Phase 2
Supabase schema-readiness and migration-ledger blocker remains in force.

## Detector prerequisite

The ignored local prerequisite `models/day4/best.onnx` is not included in Git
or redistributed here. A local Docker build requires the file and fails if its
size is not `12,265,233` bytes or its SHA-256 is not
`a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9`. Model
license and attribution verification remains unresolved.

The current local verification environment reports `opencv-python==5.0.0.93`,
while the clean-container manifest declares
`opencv-python-headless==4.12.0.88`. Clean-container compatibility remains
unverified; no dependency pin is changed for this limitation.

## Deferred public platforms

`render.yaml` is retained only as a clearly marked future reference and does
not configure an active service. Render/Vercel hostnames, credentials, CORS
origins, migrations, storage policies, and public health checks must not be
treated as verified. Do not add secrets or claim a public deployment without a
separate authorized phase and evidence.

The browser-visible frontend setting is consistently named
`NEXT_PUBLIC_API_BASE_URL`. It must contain only an explicitly configured
public HTTP(S) backend URL in a future deployment; localhost remains the only
supported setting for this submission.
