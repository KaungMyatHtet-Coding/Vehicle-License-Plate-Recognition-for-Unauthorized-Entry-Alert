# Final reduced-P0 verification boundary

CVPX is a localhost-only university prototype. The supported workflow is the
still-image recognition endpoint with process-local memory repositories and
storage. Supabase persistence is blocked until authorized live migration-ledger
and schema evidence is supplied; the historical Day 19 schema conflicts with
the Day 9/11 assumptions. The validator is expected to exit 1 for that reason.

Recognition uses conservative YGN/MDY/NPT grammar, exact normalized lookup,
deterministic candidate ranking, and `MANUAL_REVIEW` for unreliable, ambiguous,
or distinct multi-plate results. Analysis is non-persisting; finalized still
image results persist exactly once. The local webcam CLI adds bounded spatial
tracking, exact temporal consensus, real clipped boxes, cooldown suppression,
and retry after unsuccessful persistence. It is a local demonstration, not
production surveillance. Phase 6 short-video processing remains disabled/
experimental and deferred.

The ignored model prerequisite is `models/day4/best.onnx`, exactly
12,265,233 bytes with SHA-256
`a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9`. It is not
tracked or redistributed. Model license and attribution review remains
unresolved.

Docker is a local reproducibility path only. Earlier Docker verification was
blocked because Docker was unavailable; do not treat the commands in
`docs/deployment.md` as executed evidence. Render, Vercel backend/public
deployment, public Supabase, and public health endpoints remain deferred and
unsupported.

The four project-generated synthetic fixtures contain three positive images,
one negative/no-plate image, and four labeled plates. They were reused during
development and regression tests and are not independent. Evaluation output is
development-fixture smoke evidence, not a benchmark or real-world,
Myanmar-specific, or production accuracy claim. Reports retain raw matches,
OCR pairs, decisions, errors, timings, manifest/model/runtime metadata, and
limitations without private paths or secrets.
