# Vehicle License Plate Recognition for Unauthorized Entry Alert

## Overview

This repository contains a free-tier prototype that will recognize a license plate from a vehicle image, compare normalized OCR text with authorized-vehicle records, and return `AUTHORIZED`, `UNAUTHORIZED`, or `MANUAL_REVIEW`. It will retain detection records and protected evidence and present results, history, alerts, authorized vehicles, and dashboard statistics.

## Core workflow

```text
image → validate → detect plate → crop/preprocess → local OCR
      → normalize text → authorization lookup → explain decision
      → store event/evidence → display result/history/alerts/statistics
```

Required deployment supports online still images. Short videos are optional and bounded. OpenCV webcam input is local-only; continuous CCTV/IP-camera streaming is outside scope.

## Planned technology stack

| Area | Technology |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS; Vercel Free |
| Backend | FastAPI, Python, Pydantic; Render Free |
| Computer vision | OpenCV and a benchmark-selected free local plate detector |
| OCR | Benchmark-selected free local OCR |
| Data | Supabase PostgreSQL |
| Evidence | Supabase Storage |
| Local webcam | OpenCV |
| Source control | Git and GitHub |

No paid APIs are planned.

## Proposed structure

```text
backend/       FastAPI, business rules, CV/OCR, repositories
frontend/      Next.js user interface
docs/          task board and supporting documentation
scripts/       repeatable development/evaluation utilities
tests/         cross-system and evaluation tests
sample-data/   small legal fixtures and metadata (no private uploads)
PROJECT.md     requirements, architecture, scope, and decisions
PROJECT_PLAN.md daily milestone schedule
```

Directories that have not reached their milestone contain `.gitkeep`
placeholders. Day 4 added research/benchmark evidence, Day 5 integrates
still-image localization and crop extraction, and Day 6 adds configurable
non-destructive crop variants.

## Development and deployment overview

Development will proceed as reviewed milestones: backend input and recognition pipeline, Supabase persistence, frontend workflows, integration, then evaluation/deployment hardening. The Next.js frontend is planned for Vercel Free, FastAPI for Render Free, and PostgreSQL/private evidence storage for Supabase Free. Environment-specific secrets remain outside Git; only placeholder variable names appear in `.env.example`.

Day 2 includes a minimal FastAPI foundation, Day 3 adds transient image-input
validation, Day 4 selects and verifies an exact plate-specific ONNX detector,
and Day 5 integrates it as a lazy CPU service that returns bounded boxes,
confidence, timings, and lossless transient crops. Windows PowerShell setup,
model configuration, API contracts, and test commands are documented in
[backend/README.md](backend/README.md). Day 6 adds independently selectable
grayscale, resize, denoise, contrast, threshold, deskew, and perspective
variants without changing the detection API. Day 8 adds transient local OCR
and conservative normalization for validated plate crops. Day 10 adds the pure
authorization decision. Day 11 adds network-free detection logging and private
evidence abstractions; live Supabase connectivity, frontend features, and
deployment remain unimplemented.

## Current status

**Day 3 — secure image input (July 25, 2026):** the tested FastAPI shell now
also validates bounded JPEG/PNG multipart input in memory, verifies decoded
content and dimensions, returns safe metadata, and rejects invalid input with
structured errors.

**Day 4 — plate-detector evaluation:** Completed on July 28, 2026 on
`research/plate-detector`. The research identifies one immutable
plate-specific ONNX candidate with separate weights/runtime/dataset licensing,
locally verifies its checksum, CPU tensor/decoding contract, and generated
fixture results, defines a versioned bbox contract, and retains honest primary
and fallback raw results. The ignored verification weight is not committed and
the API detector was not integrated during research.

**Day 5 — still-image plate detection:** Completed on July 29, 2026 on
`feat/plate-detection`. The backend now reuses the Day 4 contract/decoding
behavior, lazily loads the configured verified ONNX model once with CPU
execution, returns zero/one/multiple bounded detections and lossless in-memory
PNG crops, and reports structured model failures. Existing health and
validation routes remain unchanged.

**Day 6 — plate preprocessing:** Completed on July 29, 2026 on
`feat/plate-preprocessing`. The backend now produces explicitly configured,
independent OCR-ready variants from preserved Day 5 crops with shape/type
metadata and timings. Deterministic tests and a generated legal-fixture contact
sheet document the behavior.

**Day 7 — OCR evaluation:** Completed on July 29, 2026 on
`research/ocr-baseline`. A reproducible local CPU benchmark compares
recognition-only and full-pipeline RapidOCR over four labeled synthetic plate
crops and six independent Day 6 variants. Raw per-sample evidence, environment,
model size, confidence, latency, candidate tradeoffs, Render caveats, and the
primary/fallback choice are retained in
[the OCR evaluation](docs/ocr_evaluation.md).

**Day 8 — OCR and normalization:** Completed on July 30, 2026 on
`feat/ocr-recognition`. The backend now lazily reuses the selected local CPU
OCR engine, tries recognition-only before the documented full-pipeline
fallback, returns raw and normalized text with confidence, and sends empty or
low-confidence results to manual review without making an authorization
decision. See [the OCR service contract](docs/ocr_recognition.md). Day 9
adds the versioned Supabase data model, typed repository boundaries,
network-free mocks, and offline schema validation. It does not yet connect the
application to Supabase or make authorization decisions. See
[the database design](docs/database_schema.md). Day 10 adds a pure,
deterministic three-way entry-decision service with stable reasons,
timezone-aware vehicle validity, safe dependency failures, and no physical or
external side effects. See
[the decision contract](docs/authorization_decision.md). Day 11 adds a
network-free logging/evidence boundary with a forward schema migration,
deterministic annotated JPEGs, collision-safe private paths, explicit partial
failures, compensating cleanup, and opaque short-lived signed access. See
[the logging and evidence contract](docs/detection_logging.md).
Deadline: **August 15, 2026**.

## Documentation

- [Project specification](PROJECT.md)
- [Daily project plan](PROJECT_PLAN.md)
- [Task board](docs/task_board.md)
- [Day 7 OCR evaluation](docs/ocr_evaluation.md)
- [Day 8 OCR service contract](docs/ocr_recognition.md)
- [Day 9 Supabase data design](docs/database_schema.md)
- [Day 10 authorization decision contract](docs/authorization_decision.md)
- [Day 11 detection logging and evidence](docs/detection_logging.md)

## Git policy

`main` contains only reviewed, working milestones. Use one coherent milestone per branch and start from the latest `main`. Test before marking Completed. Multiple milestones may finish on one real day, but commit dates must never be altered. Do not automatically merge Pull Requests, and do not commit, push, merge, or delete branches without explicit approval.
