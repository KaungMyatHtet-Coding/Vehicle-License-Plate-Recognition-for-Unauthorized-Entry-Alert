# Vehicle License Plate Recognition for Unauthorized Entry Alert

**Project period:** July 23, 2026 through August 15, 2026

## Problem statement

Manual gate checks are slow, inconsistent, and difficult to audit. This prototype assists security staff by extracting a plate from a supplied vehicle image, comparing normalized OCR text with an authorized-vehicle register, explaining its decision, and retaining a controlled event record. It is decision support, not an infallible enforcement system.

## Objectives

- Provide required online still-image recognition using only free/open-source tools and free service tiers.
- Detect, crop, preprocess, OCR, and normalize a visible license plate.
- Return an explainable `AUTHORIZED`, `UNAUTHORIZED`, or `MANUAL_REVIEW` result.
- Persist authorized vehicles, detection records, and protected evidence screenshots.
- Display recognition results, history, security alerts, vehicle records, and useful statistics.
- Measure real detection, OCR, decision, and latency outcomes reproducibly.

## Users and actors

- **Security operator:** submits images, reviews decisions/evidence, monitors alerts, and resolves manual-review cases.
- **Authorized-vehicle administrator:** creates and updates vehicle authorization records.
- **Auditor/project evaluator:** reviews history, metrics, controls, and limitations.
- **Vehicle/plate:** the observed subject; never treated as a user identity by itself.
- **External services:** Supabase database/storage, Render backend, and Vercel frontend.

## Image-to-decision workflow

1. The frontend validates basic file selection and submits a supported image.
2. FastAPI enforces byte, type, decoded-format, and dimension limits and assigns a correlation ID.
3. The local CV detector locates candidate plates and selects a primary candidate by a documented rule.
4. OpenCV crops the plate and generates useful, configurable preprocessing variants.
5. A benchmark-selected free local OCR engine returns raw text and confidence.
6. A separate normalizer uppercases text and removes permitted separators/unsupported characters without unsafe character guessing.
7. The decision service evaluates OCR reliability, exact normalized match, record status, and validity dates.
8. The API returns the decision, reason, text, confidence, bounding box/crop references, and timing.
9. The backend stores the event and a privacy-controlled annotated screenshot; partial storage failures are explicit.
10. The frontend updates the result, history, alerts, authorized vehicles, and dashboard statistics.

## Functional requirements

- Accept supported vehicle images online and reject empty, corrupt, disguised, or oversized input.
- Optionally accept bounded short videos after the still-image MVP is stable.
- Support an isolated local OpenCV webcam demo.
- Detect zero, one, or multiple plate candidates safely.
- Preserve original crops and expose relevant preprocessing/OCR evidence.
- Normalize plate text consistently and retain raw OCR text.
- Manage active, inactive, blocked, and validity-bounded authorized vehicles.
- Apply the documented three-way decision rules and include a human-readable reason.
- Store searchable detection logs, timestamps, confidences, timings, and evidence references.
- Display recognition, dashboard statistics, history/details, alerts, and authorized-vehicle management.
- Provide health/error responses, pagination/filtering, and safe loading/empty/failure UI states.

## Non-functional requirements

- **Cost:** no paid API; use free tiers and free/open-source local CV/OCR.
- **Security:** server-side secrets, least privilege, input limits, safe errors, private evidence, and auditable changes.
- **Privacy:** collect only necessary vehicle/event data, restrict access, define retention, and avoid public evidence URLs.
- **Reliability:** dependency failures must never falsely authorize; model lifecycle avoids per-request reload.
- **Performance:** record real stage/end-to-end latency and document free-tier cold starts; do not promise unmeasured targets.
- **Maintainability:** typed schemas, separated services/repositories, migrations, tests, and environment-based configuration.
- **Accessibility:** keyboard-operable controls, labels, focus visibility, contrast, and responsive layouts.
- **Reproducibility:** pinned/constrained dependencies, versioned evaluation inputs, and commands that regenerate metrics.

## Architecture and responsibilities

```text
Browser (Next.js on Vercel)
        |
        | HTTPS image request / result and management APIs
        v
FastAPI on Render
  |-- validation and API schemas
  |-- OpenCV + local plate detector
  |-- preprocessing + local OCR
  |-- normalization + decision service
  |-- repositories, event logging, signed evidence access
        |
        +--> Supabase PostgreSQL (vehicles, events, settings)
        +--> Supabase Storage (private evidence screenshots)

Local-only: OpenCV webcam runner reuses backend recognition services.
```

- **Frontend:** file UX, typed requests, result/evidence presentation, history/alerts/statistics, vehicle management, and accessible error/loading states. It holds no service-role secret and performs no authoritative decision.
- **Backend:** validation, orchestration, decision rules, authorization checks, safe errors, logging, evidence generation, and server-only service integration.
- **CV/OCR:** plate localization, crop/preprocessing, raw recognition/confidence, timings, and failure metadata. OCR does not decide authorization.
- **Database:** normalized authorized-vehicle records, validity/status, immutable-style detection history, settings, constraints, indexes, and audit-supporting timestamps.
- **Storage:** private evidence objects with collision-safe paths, controlled/signed access, and a documented retention policy.

## Local and deployed boundaries

| Capability | Deployed | Local |
|---|---:|---:|
| Still-image recognition | Required | Supported |
| Bounded short-video upload | Optional, only if free-tier limits permit | Optional |
| OpenCV webcam capture | No | Optional demo |
| Continuous CCTV/IP-camera streaming | Out of scope | Out of scope |

A deployed Render backend cannot directly open a visitor’s webcam as an OpenCV device. Any future browser camera capture would be a separate browser-mediated upload feature, not direct backend webcam access.

## Decision rules

- **`MANUAL_REVIEW`:** no reliable plate/text; OCR below configured threshold; ambiguous/multiple unresolved candidate; or a database/system dependency failure that prevents a trustworthy lookup.
- **`AUTHORIZED`:** reliable normalized text exactly matches an active record whose validity window includes the timezone-aware detection time.
- **`UNAUTHORIZED`:** reliable text has no matching record, or its record is blocked, inactive, not yet valid, or expired.

Every result includes a reason code/message. Confidence thresholds are configurable and verified against real evaluation data. Similar-looking characters are not silently substituted without tested plate-format rules. A plate match establishes vehicle authorization only; it does not prove driver identity.

## Privacy and security

- Treat plate numbers, owner fields, timestamps, and screenshots as sensitive operational data.
- Obtain appropriate consent/authority for samples; avoid unrelated faces and surroundings where practical.
- Use TLS, server-only secrets, least-privilege Supabase policies, private buckets, signed short-lived evidence access, and role-aware administration.
- Validate decoded content rather than trusting names/MIME alone; bound bytes, dimensions, video duration, and processing time.
- Generate storage names; never use raw filenames as paths; avoid logging credentials or unnecessary image data.
- Define and enforce retention/deletion and incident-response procedures before real use.
- Keep audit history for status changes; do not present OCR as certain; require human review where confidence is inadequate.

## Success and evaluation metrics

Metrics must come from a labeled, legally usable evaluation set, with sample count, environment, model/OCR versions, method, date, and raw per-sample output:

- plate detection success and bounding-box success where annotated;
- OCR exact-match accuracy and character-level accuracy;
- three-way decision accuracy and confusion counts;
- false unauthorized-alert and false authorization counts/rates;
- no-plate/manual-review handling rate;
- average and percentile stage/end-to-end latency;
- API/UI smoke-test success and stored-event/evidence integrity.

No target or result is claimed until measured. Small samples and selection bias must be disclosed.

## Risks, limitations, and fallbacks

- Plate angle, blur, glare, occlusion, uncommon formats, and low resolution may reduce detection/OCR quality → preprocess variants and `MANUAL_REVIEW`.
- Generalization depends on legal, representative samples → retain failure cases and report sample limitations.
- Render Free may cold-start or lack memory for a large model → load once, choose a smaller detector/OCR, warm before demo, and keep a local/recorded fallback.
- Supabase/network failures can prevent logging/lookup → never falsely authorize; surface a review/system error and preserve auditable retry details where safe.
- OCR confidence may be poorly calibrated → evaluate thresholds and avoid character guessing.
- A copied/fraudulent plate can match → the prototype authorizes the recorded plate, not the driver or physical vehicle identity.
- Optional video/webcam may consume schedule → drop them before compromising the still-image MVP.

## Scope

**In scope:** online image upload; plate detection/crop/preprocessing; local OCR and normalization; three-way decisions; authorized-vehicle records; detection history/evidence; alerts/statistics; responsive frontend; free-tier deployment; reproducible evaluation; optional bounded video and local webcam.

**Out of scope:** continuous CCTV/IP-camera streams; a deployed backend directly accessing visitor webcams through OpenCV; paid recognition APIs; biometric/driver identity; barrier/gate hardware control; guaranteed legal enforcement; nationwide plate registry integration; large-scale training; unlimited video or permanent raw-image retention.

## Git policy

`main` contains only reviewed, working milestones. Use one coherent milestone per branch, starting from the latest `main`; verify before marking Completed; multiple milestones may finish on one real day; never alter commit dates; never automatically merge a Pull Request; and never commit, push, merge, or delete branches without explicit approval.
