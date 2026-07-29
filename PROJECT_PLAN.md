# Vehicle License Plate Recognition for Unauthorized Entry Alert

## Project plan

**Project period:** July 23, 2026 through August 15, 2026  
**Team assumption:** One active developer  
**Cost rule:** Free/open-source software and free service tiers only; no paid APIs

The required prototype accepts a vehicle image, detects and preprocesses its license plate, recognizes and normalizes the text, compares it with authorized-vehicle records, and returns `AUTHORIZED`, `UNAUTHORIZED`, or `MANUAL_REVIEW`. It stores detection records and evidence screenshots and presents results, history, alerts, authorized vehicles, and statistics. Limited short-video processing is optional; OpenCV webcam recognition is local-only.

## Git policy

- `main` contains only reviewed, working milestones.
- Use one coherent milestone per branch and start each branch from the latest `main`.
- Test and verify evidence before moving a task to Completed.
- Multiple milestones may be completed on one real day; retain the real commit dates.
- Never alter commit dates.
- Never automatically merge a Pull Request into `main`.
- Do not commit, push, merge, or delete branches without explicit user approval.

Commands below are prospective and must be run only when their milestone begins. Use only commands supported by files that exist at that time.

## Daily milestones

### Day 1 — July 23, 2026 — Planning and repository baseline

**Branch:** `docs/project-planning`  
**Depends on:** Git repository, `main`, and configured `origin`.

**Objectives:** Fix scope, architecture, boundaries, schedule, and working policy.

**Implementation tasks:**

- Audit status, branch, recent history, remotes, and non-generated files.
- Create the project brief, daily plan, README, task board, safe ignore rules, environment template, and empty top-level structure.
- Document free-tier constraints, privacy, risks, decision rules, and local/deployed boundaries.
- Do not install, scaffold, download models/data, or implement features.

**Verification commands:**

```powershell
git status
git branch --show-current
git log -5 --oneline
git remote -v
git diff -- . ':!.git'
rg -n "Vehicle License Plate Recognition for Unauthorized Entry Alert|August 15, 2026"
```

**Acceptance/evidence:** Required documents exist; title and deadline are consistent; no secrets or application code exist; only Day 1 planning is Completed on the task board.  
**Recommended commit:** `docs: define project scope and delivery plan`

### Day 2 — July 24, 2026 — FastAPI foundation

**Branch:** `feat/backend-foundation`  
**Depends on:** Day 1 reviewed and merged to `main`.

**Objectives:** Establish a small, testable backend shell.

**Implementation tasks:** Create a virtual environment; scaffold FastAPI/Pydantic configuration, package layout, safe CORS settings, structured errors, `GET /health`, dependency files, and tests; document local setup.

**Verification commands:**

```powershell
python -m venv .venv
pip install -r backend\requirements.txt
python -m pytest backend\tests
```

**Acceptance/evidence:** Clean install works, health response is documented, tests pass, and no CV/OCR/database logic is included.  
**Recommended commit:** `feat: establish FastAPI backend foundation`

**Day 2 status:** Completed on July 24, 2026 on `feat/backend-foundation`. Evidence: Python 3.12 virtual environment, dependency installation, endpoint tests including canonical `/health`, Ruff lint/format checks, Python compilation, local Uvicorn health response, and `/docs` HTTP 200 smoke test. No implementation beyond the backend foundation was added.

### Day 3 — July 25, 2026 — Secure image input

**Branch:** `feat/image-input-validation`  
**Depends on:** Day 2 backend contracts and tests.

**Objectives:** Accept required online image input safely.

**Implementation tasks:** Define recognition request/response schemas; enforce supported formats, decoded type, dimensions, and byte limit; reject empty/corrupt inputs; generate correlation IDs; keep uploads transient.

**Verification commands:**

```powershell
python -m pytest backend\tests -k "upload or image or validation"
python -m pytest backend\tests
```

**Acceptance/evidence:** Valid fixtures pass; empty, disguised, corrupt, unsupported, and oversized fixtures return safe documented errors.  
**Recommended commit:** `feat: add secure image input validation`

**Day 3 status:** Completed on July 25, 2026 on `feat/image-input-validation`. Evidence: 15 backend tests, Pillow decoded-content checks, bounded in-memory reads, JPEG/PNG valid and invalid-input cases, Ruff lint/format, Python compilation, and local endpoint smoke tests. The validation-only endpoint returns metadata and does not detect, recognize, authorize, or persist anything.

### Day 4 — July 26, 2026 — Plate-detector evaluation

**Branch:** `research/plate-detector`  
**Depends on:** Day 3 validated image contract.

**Objectives:** Select a free local detector that can run on CPU and Render Free.

**Implementation tasks:** Compare license, source, size, CPU latency, memory, output contract, and integration effort; define legal test fixtures and bounding-box ground truth; select a primary and fallback; do not commit weights.

**Verification commands:**

```powershell
python scripts\benchmark_detector.py --help
python -m pytest tests -k detector_contract
```

**Acceptance/evidence:** Reproducible comparison and license/source notes exist; selection is evidence-based; any unavailable benchmark is explicitly recorded.  
**Recommended commit:** `docs: select free plate detection approach`

**Day 4 status:** Completed on July 28, 2026 on `research/plate-detector`. Primary: plate-specific `joker5914/yolov8n-license-plate` ONNX at immutable revision `8286762929bd4b111a19186f2a05e0a5940b6088`; the uploader's AGPL-3.0 weights declaration, dataset publisher's CC BY 4.0 declaration, and ONNX Runtime's MIT license are documented separately. The ignored artifact matched its published size/SHA-256, loaded with CPUExecutionProvider, and exposed the documented `[1,3,640,640]` to `[1,5,8400]` contract. The Day 4 research adapter validated 4/4 generated fixtures at 100.064 ms mean latency and 131.266 MB maximum sampled process RSS; these are synthetic/local results, not real-world or Render claims. Fallback: local OpenCV contour baseline, explicitly labeled heuristic, which honestly fails 2/4 fixtures and exits non-zero. Evidence: 53 detector-contract tests and 15 backend regression tests passed in the project environment; Ruff lint/format, syntax/import, and API smoke checks passed; no weights are committed.

### Day 5 — July 27, 2026 — Still-image plate detection

**Branch:** `feat/plate-detection`  
**Depends on:** Day 4 detector decision and fixture contract.

**Objectives:** Locate and crop plates without reloading the model per request.

**Implementation tasks:** Implement model lifecycle, coordinate mapping, confidence, crop extraction, timing, and safe zero/one/multiple-detection behavior; isolate optional debug output.

**Verification commands:**

```powershell
python -m pytest backend\tests -k detection
python scripts\benchmark_detector.py --input sample-data\evaluation
```

**Acceptance/evidence:** Known fixtures return valid boxes/crops, no-plate images return a safe outcome, and failure cases are recorded.  
**Recommended commit:** `feat: add still-image plate detection`

**Day 5 status:** Completed on July 29, 2026 on `feat/plate-detection`.
Evidence: the selected checksum-verified ONNX model loads lazily once per
application process with `CPUExecutionProvider`; the shared Day 4 contract,
letterbox coordinate mapping, confidence/NMS, lossless transient PNG crops,
timings, and safe zero/one/multiple results are integrated behind
`POST /api/recognition/detect-plates`. Missing, invalid, unloadable, and runtime
model failures return structured errors without making health, imports, or
image validation depend on a local weight. The four generated Day 4 fixtures
return their expected counts and valid bounded crops. No model weight is
committed, and Day 6 preprocessing is not implemented.

### Day 6 — July 28, 2026 — Plate preprocessing

**Branch:** `feat/plate-preprocessing`  
**Depends on:** Day 5 crop contract.

**Objectives:** Produce configurable OCR-ready variants while preserving originals.

**Implementation tasks:** Add grayscale, resize, denoise, contrast, threshold, and optional deskew/perspective operations; return stage metadata and timings; avoid unconditional transformation chains.

**Verification commands:**

```powershell
python -m pytest backend\tests -k preprocessing
```

**Acceptance/evidence:** Deterministic shape/type tests pass, original crops remain unchanged, and visual examples document useful variants.  
**Recommended commit:** `feat: add configurable plate preprocessing`

**Day 6 status:** Completed on July 29, 2026 on
`feat/plate-preprocessing`. Evidence: a non-destructive service produces only
explicitly selected grayscale, aspect-preserving resize, bilateral denoise,
CLAHE contrast, Otsu threshold, deskew, and perspective variants from the
unchanged Day 5 crop. It returns original/stage shape and type metadata plus
per-stage and total timings. Focused deterministic tests cover shapes, types,
independent stages, preservation, optional geometry, safe bounds, and failure
codes. A reproducible contact sheet uses the generated legal fixture. No OCR
or Day 7 work is included.

### Day 7 — July 29, 2026 — OCR evaluation

**Branch:** `research/ocr-baseline`  
**Depends on:** Day 6 variants and labeled text fixtures.

**Objectives:** Select a free local OCR solution after real testing.

**Implementation tasks:** Compare licenses, package/model size, CPU behavior, Render feasibility, supported characters, confidence output, and preprocessing variants; record exact-match and character results from actual samples only.

**Verification commands:**

```powershell
python scripts\benchmark_ocr.py --help
python scripts\benchmark_ocr.py --input sample-data\evaluation
```

**Acceptance/evidence:** Raw per-sample output, environment details, limitations, primary OCR, and fallback are documented; no fabricated metric appears.  
**Recommended commit:** `docs: select free local OCR baseline`

**Day 7 status:** Completed on July 29, 2026 on `research/ocr-baseline`.
Evidence: the reproducible CPU benchmark retained 48 raw results covering four
labeled synthetic plate crops, six independent Day 6 variants, and two
RapidOCR modes. Both modes produced 24/24 normalized exact matches on this
small synthetic fixture set; recognition-only was selected as the primary and
the full detection/classification/recognition pipeline as the fallback.
Environment, bundled-model size, confidence, latency, candidate comparison,
deployment caveats, and limitations are documented. No OCR API integration or
Day 8 work is included.

### Day 8 — July 30, 2026 — OCR and normalization

**Branch:** `feat/ocr-recognition`  
**Depends on:** Day 7 OCR choice and Day 6 preprocessing API.

**Objectives:** Return raw and normalized plate text with confidence.

**Implementation tasks:** Integrate OCR; separate normalization from recognition; normalize case, whitespace, separators, and unsupported characters; avoid unproven `O/0` substitutions; flag empty/low-confidence output for review.

**Verification commands:**

```powershell
python -m pytest backend\tests -k "ocr or normaliz"
python -m pytest backend\tests
```

**Acceptance/evidence:** Normalization examples such as `YGN 5A-1234` → `YGN5A1234` pass; low confidence never automatically accuses a vehicle.  
**Recommended commit:** `feat: integrate OCR and plate normalization`

**Day 8 status:** Completed on July 30, 2026 on `feat/ocr-recognition`.
Evidence: a lazily reused RapidOCR 3.9.2 service runs the Day 7
recognition-only primary and optional full-pipeline fallback with all sessions
restricted to `CPUExecutionProvider`. A separate conservative normalizer
uppercases and retains only ASCII letters/digits, without `O/0` substitution.
Empty and below-threshold results return `manual_review`; no authorization
decision is made. The transient `POST /api/recognition/recognize-plate` route
preserves secure JPEG/PNG validation and returns raw/normalized text,
confidence, mode, review reason, dimensions, and timings. No Day 9 data work
is included.

### Day 9 — July 31, 2026 — Supabase data design

**Branch:** `feat/database-schema`  
**Depends on:** Day 8 normalized text and result schema.

**Objectives:** Define durable authorized vehicles, detection logs, settings, and evidence references.

**Implementation tasks:** Add versioned SQL/migrations, indexes, constraints, normalized uniqueness, timestamps, repository interfaces, mock repositories, storage-bucket/RLS guidance, and server-only credential rules.

**Verification commands:**

```powershell
python -m pytest backend\tests -k repositor
python scripts\validate_schema.py
```

**Acceptance/evidence:** Schema applies to a clean development project or passes a documented local validation; mock tests require no network; secrets are absent.  
**Recommended commit:** `feat: define Supabase data model`

**Day 9 status:** Completed on July 31, 2026 on `feat/database-schema`.
Evidence: a transactional versioned PostgreSQL migration defines constrained
authorized-vehicle, detection-log, and server-setting tables with normalized
uniqueness, timestamps, indexes, RLS, and client-role revocation. Typed
repository interfaces and locked in-memory mocks validate the same key
boundaries without network access. The offline schema validator, storage/RLS
guidance, and server-only credential rules are documented. No remote
connection, persistence integration, evidence upload, or Day 10 authorization
decision is included.

### Day 10 — August 1, 2026 — Decision engine

**Branch:** `feat/authorization-engine`  
**Depends on:** Day 8 confidence/normalization and Day 9 repository interface.

**Objectives:** Produce deterministic, explainable decisions.

**Implementation tasks:** Implement a pure service with configurable thresholds and timezone-aware validity: unreliable/empty OCR → `MANUAL_REVIEW`; active valid exact match → `AUTHORIZED`; missing, blocked, inactive, or expired record → `UNAUTHORIZED`; dependency failure → `MANUAL_REVIEW` or explicit system error, never false authorization.

**Verification commands:**

```powershell
python -m pytest backend\tests -k decision
```

**Acceptance/evidence:** Boundary, status, confidence, missing-record, and dependency-failure tests cover every rule and reason code.  
**Recommended commit:** `feat: add authorization decision engine`

### Day 11 — August 2, 2026 — Detection logging and evidence

**Branch:** `feat/detection-logging`  
**Depends on:** Day 9 schema and Day 10 decision result.

**Objectives:** Persist auditable outcomes and privacy-aware screenshots.

**Implementation tasks:** Create annotated evidence, collision-safe paths, log metadata/timings, partial-failure handling, retention guidance, and signed/private access; never place service credentials in the client.

**Verification commands:**

```powershell
python -m pytest backend\tests -k "logging or evidence or storage"
```

**Acceptance/evidence:** Mock integration proves metadata/evidence association; storage failure cannot change the decision or hide the failure.  
**Recommended commit:** `feat: persist detection records and evidence`

### Day 12 — August 3, 2026 — Next.js frontend foundation

**Branch:** `feat/frontend-foundation`  
**Depends on:** Stable API schemas through Day 11.

**Objectives:** Establish responsive navigation and typed API access.

**Implementation tasks:** Scaffold Next.js/TypeScript/Tailwind; add layouts for dashboard, recognition, history, alerts, and authorized vehicles; implement environment-based API client, loading/error primitives, and accessibility baseline.

**Verification commands:**

```powershell
cd frontend
npm run lint
npm run type-check
npm run build
```

**Acceptance/evidence:** Production build passes, routes render at mobile/desktop widths, and no secret enters the browser bundle.  
**Recommended commit:** `feat: establish frontend foundation`

### Day 13 — August 4, 2026 — Recognition interface

**Branch:** `feat/recognition-ui`  
**Depends on:** Day 12 shell and Day 3–11 image API.

**Objectives:** Complete the required deployed image-recognition experience.

**Implementation tasks:** Add image selection/preview, validation, submit/progress states, timeout/error handling, result decision/reason, plate crop, raw/normalized text, confidence, and evidence display.

**Verification commands:**

```powershell
cd frontend
npm run test
npm run lint
npm run type-check
npm run build
```

**Acceptance/evidence:** Authorized, unauthorized, manual-review, no-plate, invalid-file, and server-failure states are demonstrated with recorded screenshots/tests.  
**Recommended commit:** `feat: add image recognition interface`

### Day 14 — August 5, 2026 — Dashboard, history, and alerts

**Branch:** `feat/dashboard-history`  
**Depends on:** Day 11 records and Day 12 frontend.

**Objectives:** Make events and operational statistics visible.

**Implementation tasks:** Add paginated history, filters, event detail/evidence, alert view, and server-derived totals/trends for decisions; define empty/loading/error states and timezone display.

**Verification commands:**

```powershell
python -m pytest backend\tests -k "history or stats or alert"
cd frontend
npm run test
npm run build
```

**Acceptance/evidence:** Seeded records produce correct filters/totals; unauthorized alerts are visually distinct; empty and failed queries are safe.  
**Recommended commit:** `feat: add dashboard history and alerts`

### Day 15 — August 6, 2026 — Authorized-vehicle management

**Branch:** `feat/vehicle-management`  
**Depends on:** Day 9 authorized-vehicle schema and Day 12 UI.

**Objectives:** Manage the allowlist safely and audibly.

**Implementation tasks:** Add validated create/read/update/status endpoints and UI; search/filter; normalized uniqueness; validity dates; confirmations; prefer inactive/blocked status over destructive deletion.

**Verification commands:**

```powershell
python -m pytest backend\tests -k vehicle
cd frontend
npm run test
npm run build
```

**Acceptance/evidence:** Create/update/duplicate/block/expiry tests pass, and changing a record changes a later decision as specified.  
**Recommended commit:** `feat: add authorized vehicle management`

### Day 16 — August 7, 2026 — Core integration freeze

**Branch:** `test/system-integration`  
**Depends on:** Days 3–15 required still-image features.

**Objectives:** Stabilize the required MVP before optional work.

**Implementation tasks:** Exercise upload-to-history end to end; standardize correlation IDs, timeouts, payload limits, CORS, and safe errors; cover no/multiple plates, low confidence, expired/blocked vehicles, and database/storage failure; freeze P0 scope.

**Verification commands:**

```powershell
python -m pytest
cd frontend
npm run lint
npm run type-check
npm run build
```

**Acceptance/evidence:** Repeated full-flow smoke tests pass with recorded commands/results; unresolved P0 defects block optional work.  
**Recommended commit:** `test: harden still-image recognition workflow`

### Day 17 — August 8, 2026 — Optional short video

**Branch:** `feat/video-processing`  
**Depends on:** Day 16 passing core freeze; skip if P0 is unstable.

**Objectives:** Reuse the image pipeline for bounded video files.

**Implementation tasks:** Enforce documented size/duration/format limits; sample frames; suppress duplicate events; summarize detections and progress; preserve image behavior; fall back to local-only or backlog if free-tier limits fail.

**Verification commands:**

```powershell
python -m pytest backend\tests -k video
python scripts\smoke_video.py --input sample-data\short-video
```

**Acceptance/evidence:** A legal short fixture completes inside stated limits without excessive duplicate logs; otherwise feature remains Planned/Blocked and is not advertised.  
**Recommended commit:** `feat: add bounded short-video recognition`

### Day 18 — August 9, 2026 — Local webcam demo

**Branch:** `feat/local-webcam`  
**Depends on:** Day 16 stable services; independent of deployed browser access.

**Objectives:** Provide a local OpenCV demonstration only.

**Implementation tasks:** Build an isolated local runner with sampled frames, overlays, cooldown, FPS/latency, camera-unavailable handling, and safe stop; ensure server startup never requires a camera.

**Verification commands:**

```powershell
python scripts\run_webcam.py --help
python -m pytest tests -k webcam
python scripts\run_webcam.py --camera 0
```

**Acceptance/evidence:** Local start/stop and unavailable-camera behavior are recorded; documentation clearly says a deployed backend cannot access a visitor’s webcam through OpenCV.  
**Recommended commit:** `feat: add local webcam demonstration`

### Day 19 — August 10, 2026 — Free-tier deployment

**Branch:** `chore/deployment`  
**Depends on:** Day 16 core release candidate; optional Days 17–18 must not block it.

**Objectives:** Deploy the required online image flow to Render, Vercel, and Supabase Free.

**Implementation tasks:** Configure health/start/build commands, platform port, environment variables, production CORS, migrations/storage policies, frontend API URL, cold-start messaging, and secret-free deployment instructions.

**Verification commands:**

```powershell
python -m pytest
cd frontend
npm run build
curl.exe $env:BACKEND_HEALTH_URL
```

**Acceptance/evidence:** Public frontend and health endpoint work and a public image produces a stored result; actual URLs/test timestamps are recorded without credentials.  
**Recommended commit:** `chore: configure free-tier deployment`

### Day 20 — August 11, 2026 — Reproducible evaluation

**Branch:** `test/system-evaluation`  
**Depends on:** Day 16 frozen core and selected CV/OCR versions.

**Objectives:** Generate honest, traceable quality and timing results.

**Implementation tasks:** Separate evaluation from tuning data; define ground truth; calculate detection success, OCR exact/character accuracy, decision accuracy, false-alert rate, and latency summaries; retain per-sample failures and environment/version details.

**Verification commands:**

```powershell
python scripts\evaluate_system.py --input sample-data\evaluation --output artifacts\evaluation
python -m pytest tests -k metrics
```

**Acceptance/evidence:** Aggregate values regenerate from retained raw output; sample size and limitations are explicit; missing data is never filled with invented results.  
**Recommended commit:** `test: add reproducible system evaluation`

### Day 21 — August 12, 2026 — Online QA and security review

**Branch:** `fix/online-hardening`  
**Depends on:** Day 19 deployment and Day 20 measured baseline.

**Objectives:** Fix verified release risks without broad refactoring.

**Implementation tasks:** Test browser widths, cold starts, timeouts, upload limits, CORS, storage/database policies, secret exposure, error leakage, dependency warnings, model reloads, and evidence sizing; prioritize P0/P1 defects.

**Verification commands:**

```powershell
python -m pytest
cd frontend
npm run lint
npm run type-check
npm run build
git diff --check
```

**Acceptance/evidence:** Release checklist records environment and results; no secrets/internal traces appear; remaining issues have severity and fallback.  
**Recommended commit:** `fix: harden deployed recognition workflow`

### Day 22 — August 13, 2026 — UI and accessibility polish

**Branch:** `style/project-show-polish`  
**Depends on:** Day 21 release behavior and frozen API rules.

**Objectives:** Improve clarity and accessibility without destabilizing logic.

**Implementation tasks:** Audit spacing, typography, hierarchy, contrast, focus, keyboard use, labels, dialogs, mobile overflow, result states, and placeholders; add only restrained feedback interactions.

**Verification commands:**

```powershell
cd frontend
npm run test
npm run lint
npm run type-check
npm run build
```

**Acceptance/evidence:** Required pages have loading/empty/success/error states, keyboard paths work, target widths have no horizontal overflow, and build passes.  
**Recommended commit:** `style: polish project-show interface`

### Day 23 — August 14, 2026 — Deliverables and rehearsal

**Branch:** `docs/final-deliverables`  
**Depends on:** Days 20–22 verified outputs and release candidate.

**Objectives:** Prepare truthful report, deterministic demo, and offline fallback.

**Implementation tasks:** Reconcile docs with actual implementation; add architecture, setup, real evaluation, limitations, privacy, and future work; capture screenshots; rehearse authorized/unauthorized/manual-review cases; prepare local fixtures and a backup demo recording.

**Verification commands:**

```powershell
git diff --check
rg -n "TODO|TBD|PLACEHOLDER" README.md PROJECT.md docs
python -m pytest
cd frontend
npm run build
```

**Acceptance/evidence:** Report metrics trace to Day 20 output, links work, demo checklist has timestamps, and optional/unverified features are labeled honestly.  
**Recommended commit:** `docs: finalize report and demo materials`

### Day 24 — August 15, 2026 — Final verification and submission

**Branch:** `main`; use `fix/final-blocker` only for an essential correction.  
**Depends on:** Reviewed and explicitly merged Day 23 release candidate.

**Objectives:** Submit a stable, reproducible project with backups.

**Implementation tasks:** Verify clean reviewed source, backend tests, frontend checks/build, local and public image smoke tests, health/storage availability, links, report/presentation/source/deployment/backup materials, and secret scan; warm Render before presentation. Create a tag only with explicit approval.

**Verification commands:**

```powershell
git status
python -m pytest
cd frontend
npm run lint
npm run type-check
npm run build
```

**Acceptance/evidence:** `AUTHORIZED`, `UNAUTHORIZED`, and `MANUAL_REVIEW` flows work; history/statistics update; all deliverables and limitations are present; no secret is tracked.  
**Recommended commit:** `release: finalize project submission`

## Priority and feasibility controls

1. **P0:** still-image validation, detection, OCR/normalization, three-way decision, logging/evidence, recognition UI, deployment, and honest evaluation.
2. **P1:** dashboard/history/alerts, vehicle management, accessibility, and backup demo.
3. **P2:** short video, local webcam, extra charts, and animation.

If Day 16 is unstable, postpone P2. Short video and webcam must never delay the required online-image flow. For one developer, prefer small vertical slices, mocks for deterministic tests, and documented fallbacks over simultaneous frontend/backend/CV expansion.

## Principal risks and fallbacks

| Risk | Mitigation | Fallback |
|---|---|---|
| Detector/OCR quality is weak | Benchmark early; keep failure samples | `MANUAL_REVIEW`; disclose limits |
| Render memory/build/cold start | Check model size; load once; warm service | Smaller free model or local inference demo |
| Supabase outage/policy issue | Mock repositories; explicit partial failures | Local evidence for demo; disclose outage |
| Too little legal evaluation data | Define collection/labeling early | Report sample-size limitation |
| Optional scope threatens core | Freeze P0 on August 7 | Drop video, then webcam |
| Network fails at presentation | Rehearse local path | Recorded demo and local fixtures |
| Sensitive plate/evidence exposure | Private storage, minimal retention, access control | Disable evidence sharing and document incident |
