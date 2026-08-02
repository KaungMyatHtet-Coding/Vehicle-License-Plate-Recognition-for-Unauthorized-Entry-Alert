# Vehicle License Plate Recognition for Unauthorized Entry Alert

## Task board

**Project period:** July 23, 2026 through August 15, 2026  
**Milestone owner:** Project developer (one active developer)  
**Board rule:** Status reflects evidence, not intention.

## Evidence required for Completed

A task may move to Completed only when its scoped files exist, applicable verification commands have passed with recorded results, acceptance criteria are demonstrated, documentation reflects reality, and a diff/secret/generated-file review finds no unintended content. User-facing work also needs a recorded smoke test or screenshot; research needs sources, license/version details, fixture/method, and real raw results. A commit or PR is useful milestone evidence but is not required for Day 1 and must never be created without explicit approval.

## Planned

| Date | Milestone | Owner | Required evidence |
|---|---|---|---|
| Aug 8 | Optional bounded video | Project developer | Limit/duplicate tests or honest deferral |

## In Progress

None.

## Completed

| Date | Task | Owner | Evidence |
|---|---|---|---|
| Jul 23 | Repository baseline inspected | Project developer | Status, branch, history, remotes, and file inventory captured |
| Jul 23 | Scope and architecture documented | Project developer | `PROJECT.md` and `README.md` |
| Jul 23 | Daily milestone plan documented | Project developer | `PROJECT_PLAN.md`, Jul 23–Aug 15 |
| Jul 23 | Task board and repository hygiene prepared | Project developer | This board, `.gitignore`, `.env.example`, and tracked empty directories |
| Jul 24 | FastAPI foundation | Project developer | `py -3.12`, dependency install, endpoint tests including canonical `/health`, Ruff lint/format, compileall, local health JSON, `/docs` HTTP 200; commit pending approval |
| Jul 25 | Secure image input | Project developer | 15 pytest passes; JPEG/PNG, empty, unsupported, spoofed, mismatched, truncated, oversized, and dimension tests; Ruff, format, compileall, and endpoint smoke checks; commit pending approval |
| Jul 28 | Plate-detector evaluation | Project developer | Immutable plate-specific ONNX artifact size/SHA verified; uploader/runtime/dataset license declarations kept separate with attribution; CPU tensor and decoding contract inspected; primary 4/4 generated fixtures at 100.064 ms mean and 131.266 MB maximum sampled RSS; contour fallback fails 2/4 honestly; 53 contract and 15 regression tests; no weights committed |
| Jul 29 | Still-image plate detection | Project developer | Lazy ONNX Runtime CPU lifecycle; shared Day 4 bbox contract; four generated fixtures return expected counts and valid crops; safe zero/multiple and structured missing/invalid/unloadable-model tests; health/image-validation regressions retained; no weights committed |
| Jul 29 | Plate preprocessing | Project developer | Non-destructive configurable grayscale/resize/denoise/contrast/threshold/deskew/perspective service; deterministic shape/type, preservation, independent-stage, geometry, bound, and error tests; reproducible legal-fixture contact sheet; no OCR |
| Jul 29 | OCR evaluation | Project developer | 48 retained raw CPU results across four labeled synthetic crops, six independent preprocessing variants, and two RapidOCR modes; 24/24 exact for each mode on this limited set; primary/fallback, environment, size, latency, confidence, Render caveats, and limitations documented; no OCR integration |
| Jul 30 | OCR and normalization | Project developer | Lazy RapidOCR 3.9.2 CPU-only primary/fallback service; separate conservative normalization; raw/normalized text, confidence, mode, review reason, and timing contract; empty/low-confidence manual review; focused service/API/failure tests; no authorization or persistence |
| Jul 31 | Supabase data design | Project developer | Transactional versioned schema with normalized uniqueness, timestamps, indexes, RLS, and client revocation; typed repository contracts and locked network-free mocks; offline validator; private-bucket/RLS and server-only credential guidance; no remote integration or decision logic |
| Aug 1 | Decision engine | Project developer | Pure three-way decision service; configurable inclusive confidence boundary; exact active/valid lookup; explicit missing/inactive/blocked/not-yet-valid/expired reasons; timezone and dependency failures fail to manual review; stable non-accusatory output; no persistence, alert, or gate action |
| Aug 2 | Detection logging/evidence | Project developer | Deterministic metadata-free JPEG annotation; collision-safe private paths; thread-safe network-free storage and signed-access abstraction; exact decision/reason/vehicle audit fields; explicit storage/log/signing/cleanup failures; mock association and compensation tests; no live Supabase or public URLs |
| Aug 3 | Frontend foundation | Project developer | Next.js App Router with strict TypeScript/Tailwind; responsive accessible navigation and five route layouts; typed sanitized environment-based API client; focused tests, lint, type-check, production build, route smoke, and clean dependency audit |
| Aug 4 | Recognition interface | Project developer | Authoritative full-pipeline endpoint; accessible upload/preview/result/reset workflow; deterministic backend/frontend state tests; six inspected 1440×1100 Playwright/system-Chrome screenshots under `docs/evidence/day13/`; interception evidence labeled as frontend rendering rather than live OCR |
| Aug 5 | Dashboard/history/alerts | Project developer | Shared process-local dependency boundary; sanitized history/detail/statistics/alerts APIs; explicit detail failure and invalid-filter states; backend-derived decisions, UTC trends, and alert selection; fail-closed nested public parsing and restricted evidence metadata; safe no-plate failure warning; 18 focused, 214 backend, 273 full, and 125 frontend tests; lint/format/type-check/build/schema/audit; eight inspected rendering-only screenshots under `docs/evidence/day14/` |
| Aug 6 | Authorized vehicles | Project developer | Validated process-local create/read/update/status APIs and connected UI; normalized uniqueness; search/status filters; timezone-aware validity; ACTIVE/INACTIVE/BLOCKED handling; confirmations without destructive deletion; decision integration and sanitized-error tests; 5 focused/219 full backend and 8 focused/133 full frontend tests; Ruff, ESLint, TypeScript, and production build pass; persistence limitation documented |
| Aug 7 | Core integration freeze | Project developer | Dedicated end-to-end integration test suite covering input validation -> detection -> OCR -> decision -> logging -> operational views & security alerts; fail-closed verification for unknown, BLOCKED, INACTIVE, EXPIRED, NOT_YET_VALID, low confidence, and no-plate cases; 287 backend pytest, 133 frontend vitest, Ruff lint/format, ESLint, TypeScript, and Next.js build pass cleanly; P0 scope frozen |
| Aug 8 | Optional short video | Project developer | Reused still-image recognition pipeline across frame-sampled short video files; enforced size (<=25MB), duration (<=10s), format (.mp4/.avi/.mov) limits; 3.0s duplicate suppression; 4 focused/291 full backend tests, CLI smoke script, Ruff, ESLint, TypeScript, and Next.js production build pass cleanly |
| Aug 9 | Local webcam demo | Project developer | Isolated standalone `scripts/run_webcam.py` with `--camera`, `--fps`, `--cooldown`; bounding-box overlays; FPS/latency HUD; 3s duplicate suppression; camera-unavailable error handling (exit 1, no crash); Q/Ctrl+C safe stop; server-independence invariant verified; 7 focused/298 full backend tests, Ruff lint/format pass cleanly |
| Aug 10 | Free-tier deployment | Project developer | Dockerfile, render.yaml blueprint, Supabase SQL migration script, secret-free deployment guide (`docs/deployment.md`); 6 focused/304 full backend tests, Ruff lint/format, Vitest (133/133), ESLint, TypeScript, and Next.js production build pass cleanly |
| Aug 11 | Reproducible evaluation | Project developer | Reproducible system evaluator `scripts/evaluate_system.py`, Levenshtein distance & character accuracy, JSON/Markdown evaluation reports under `artifacts/evaluation/`; 4 focused/308 full backend tests, Ruff lint/format, Vitest (133/133), ESLint, TypeScript, and Next.js production build pass cleanly |
| Aug 12 | Online QA/security | Project developer | Online security & hardening tests `backend/tests/test_online_hardening.py`, secret scanner, payload size limit enforcement, error response sanitization, release QA checklist (`docs/release_qa_checklist.md`); 5 focused/313 full backend tests, Ruff lint/format, Vitest (133/133), ESLint, TypeScript, and Next.js production build pass cleanly |
| Aug 13 | UI/accessibility polish | Project developer | Accessible focus-visible ring styles, ARIA labels, EmptyState feedback components across all 5 routes, mobile responsive layout checks; 313 backend pytest, Vitest (133/133), ESLint, TypeScript, and Next.js production build pass cleanly |
| Aug 14 | Deliverables/rehearsal | Project developer | Reconciled `README.md` with system architecture & performance baseline metrics, demo rehearsal guide (`docs/demo_rehearsal_checklist.md`), offline fallback procedures; 313 backend pytest, Vitest (133/133), ESLint, TypeScript, and Next.js production build pass cleanly |
| Aug 15 | Final verification/submission | Project developer | Full Day 1–24 audit: 313 backend pytest (all test suites), 133 frontend Vitest, Ruff lint/format (68 files), ESLint, TypeScript, Next.js production build (9/9 routes) — all 446 automated tests passed with zero failures, zero lint errors, zero type errors; `main` at commit `23e2ab3` verified clean and submission-ready |

## Blocked

None.

## Backlog

- Browser-mediated camera capture (distinct from direct OpenCV access).
- Continuous CCTV/IP-camera streaming.
- Gate/barrier hardware integration.
- Broader plate-region training and production-scale monitoring.
- Advanced charts, animations, and nonessential UI customization.

## Git policy

- `main` contains only reviewed, working milestones.
- Use one coherent milestone per branch, created from the latest `main`.
- Test and verify before moving work to Completed.
- Multiple milestones may finish on one real day; never alter commit dates.
- Never automatically merge a Pull Request into `main`.
- Do not commit, push, merge, or delete branches without explicit approval.
