# Vehicle License Plate Recognition for Unauthorized Entry Alert (CVPX)

## Overview

CVPX is an automated vehicle license plate recognition (ALPR) and entry authorization system. It recognizes license plates from vehicle images, compares normalized OCR text against authorized vehicle allowlists, and returns an authoritative decision (`AUTHORIZED`, `UNAUTHORIZED`, or `MANUAL_REVIEW`). It retains detection logs, audit statistics, and protected evidence, providing operational views for recognition workspace, entry dashboard, detection history, security alerts, and vehicle allowlist management.

## Core Workflow

```text
image → validate → detect plate (YOLOv8 ONNX) → crop/preprocess
      → local OCR (RapidOCR) → normalize text → authorization lookup (Allowlist)
      → explain decision → store event & evidence → operational views (Dashboard / History / Alerts)
```

Still-image recognition is the supported localhost workflow. The standalone
OpenCV webcam is a local demonstration only. Phase 6 short-video processing is
disabled/experimental and intentionally deferred.

---

## 🏗️ Technology Stack

| Area | Technology | Implementation Detail |
|---|---|---|
| **Frontend** | Next.js 16 (App Router), React 19, Tailwind CSS | Localhost prototype; Vercel deferred |
| **Backend** | FastAPI, Python 3.12, Pydantic v2 | Localhost prototype; Render deferred |
| **Plate Detector** | YOLOv8 Single-class ONNX Model | CPU Execution Provider (`models/day4/best.onnx`) |
| **OCR Engine** | RapidOCR ONNXRuntime | CPU Execution Provider with character-level accuracy |
| **Database & Storage** | Process-local memory repositories/storage | Supabase blocked pending migration/schema evidence |
| **Local Webcam** | OpenCV HighGUI | Standalone runner (`scripts/run_webcam.py`) |

---

## 📊 Evaluation Baseline

`sample-data/evaluation` contains four project-generated synthetic fixtures
(three positive images, one negative/no-plate image, and four labeled plate
instances). They are development/regression data reused during implementation,
not an independent evaluation set. The Phase 7 evaluator reports plate-level
TP/FP/FN, OCR pairs, negative-only false-alert/no-plate metrics, authorization
metrics, and latency distributions, but its output must not be interpreted as
real-world, Myanmar-specific, or production performance. Four images are also
insufficient for reliable p95 or performance claims.

Run the explicitly development-only report with:

```powershell
backend\.venv\Scripts\python.exe scripts\evaluate_system.py --input sample-data\evaluation --output artifacts\evaluation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.12+ with virtual environment
- Node.js 18+ and npm

The ignored local detector prerequisite is `models/day4/best.onnx` with size
`12,265,233` bytes and SHA-256
`a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9`.
It is not tracked or redistributed; license and attribution verification
remain unresolved.

### 2. Backend Setup
```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- Health Check: `http://127.0.0.1:8000/health`
- Interactive API Docs (Swagger): `http://127.0.0.1:8000/docs`

### 3. Frontend Setup
```powershell
cd frontend
npm.cmd install
npm run dev
```
- Web Application UI: `http://localhost:3000`

### 4. Local Webcam Demo
```powershell
backend\.venv\Scripts\python.exe scripts\run_webcam.py --camera 0
```
- Press **`Q`** to exit webcam window.

### 5. Reproducible Evaluation Runner
```powershell
backend\.venv\Scripts\python.exe scripts\evaluate_system.py --input sample-data\evaluation --output artifacts\evaluation
```
This report is development-fixture smoke evidence only, not a benchmark or a
real-world, Myanmar-specific, or production accuracy claim. The schema
validator is expected to exit 1 while the historical migration conflict and
unknown live ledger remain unresolved.

Docker commands are local reproducibility steps, not executed evidence; Docker
was unavailable in the earlier verification environment.

---

## 📁 Repository Structure

```text
backend/         FastAPI application, domain schemas, services, repositories
frontend/        Next.js App Router user interface and API client
docs/            Task board, deployment guide, security checklist, demo guide
scripts/         Webcam runner, system evaluation, smoke test scripts
supabase/        SQL database migration schema scripts
tests/           Cross-system, webcam, and evaluation test suites
sample-data/     Ground-truth evaluation fixtures and datasets
artifacts/       Generated evaluation JSON & Markdown reports
PROJECT.md       System requirements and architecture specification
PROJECT_PLAN.md  Milestone schedule & acceptance criteria
```

---

## 📚 Documentation & Milestones

- [Project Specification](PROJECT.md)
- [Daily Project Plan](PROJECT_PLAN.md)
- [Task Board](docs/task_board.md)
- [Free-Tier Deployment Guide](docs/deployment.md)
- [Release QA & Security Checklist](docs/release_qa_checklist.md)
- [Demo Rehearsal Checklist](docs/demo_rehearsal_checklist.md)
- [Local Webcam Demo Guide](docs/webcam_demo.md)
- [Final Verification Boundary](docs/final_verification.md)
