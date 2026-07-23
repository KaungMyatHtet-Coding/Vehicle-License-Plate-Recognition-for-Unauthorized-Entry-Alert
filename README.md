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

Empty directories currently contain `.gitkeep` placeholders only.

## Development and deployment overview

Development will proceed as reviewed milestones: backend input and recognition pipeline, Supabase persistence, frontend workflows, integration, then evaluation/deployment hardening. The Next.js frontend is planned for Vercel Free, FastAPI for Render Free, and PostgreSQL/private evidence storage for Supabase Free. Environment-specific secrets remain outside Git; only placeholder variable names appear in `.env.example`.

Setup and execution commands will be added when implementation begins. Day 1 intentionally installs no dependencies, creates no virtual environment, and scaffolds neither FastAPI nor Next.js.

## Current status

**Day 1 — planning only (July 23, 2026):** repository scope, architecture, schedule, task board, safe ignore policy, environment template, and empty folder structure are prepared. All implementation milestones remain Planned. Deadline: **August 15, 2026**.

## Documentation

- [Project specification](PROJECT.md)
- [Daily project plan](PROJECT_PLAN.md)
- [Task board](docs/task_board.md)

## Git policy

`main` contains only reviewed, working milestones. Use one coherent milestone per branch and start from the latest `main`. Test before marking Completed. Multiple milestones may finish on one real day, but commit dates must never be altered. Do not automatically merge Pull Requests, and do not commit, push, merge, or delete branches without explicit approval.

