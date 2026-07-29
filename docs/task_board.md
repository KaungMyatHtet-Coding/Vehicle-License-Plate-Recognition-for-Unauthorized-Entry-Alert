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
| Aug 1 | Decision engine | Project developer | Tests for all three decisions and failures |
| Aug 2 | Detection logging/evidence | Project developer | Storage/log mock integration tests |
| Aug 3 | Frontend foundation | Project developer | Lint, type-check, build, responsive smoke test |
| Aug 4 | Recognition interface | Project developer | Six result/error-state tests |
| Aug 5 | Dashboard/history/alerts | Project developer | Filter/statistics tests and UI evidence |
| Aug 6 | Authorized vehicles | Project developer | CRUD/status/decision integration evidence |
| Aug 7 | Core integration freeze | Project developer | Repeated end-to-end image smoke tests |
| Aug 8 | Optional bounded video | Project developer | Limit/duplicate tests or honest deferral |
| Aug 9 | Local webcam demo | Project developer | Local start/stop/unavailable-camera evidence |
| Aug 10 | Free-tier deployment | Project developer | Public health and image-flow timestamps |
| Aug 11 | Reproducible evaluation | Project developer | Raw per-sample and regenerated aggregate output |
| Aug 12 | Online QA/security | Project developer | Release checklist and secret/security review |
| Aug 13 | UI/accessibility polish | Project developer | Checks/build and keyboard/responsive evidence |
| Aug 14 | Deliverables/rehearsal | Project developer | Reconciled report, demo checklist, backup |
| Aug 15 | Final verification/submission | Project developer | Full verification and deliverable checklist |

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
