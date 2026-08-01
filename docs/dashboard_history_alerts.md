# Day 14 dashboard, history, and alerts

Day 14 makes process-local recognition activity visible through sanitized,
server-authoritative operational APIs and three responsive frontend views.
It does not add Supabase integration, durable persistence, authentication, or
evidence delivery.

## API contract

- `GET /api/detections` returns newest-first detection records with a UUID
  tie-breaker, pages of 1–100 items, and optional decision, exact normalized
  plate, inclusive `created_from`, and exclusive `created_to` filters.
- `GET /api/detections/{correlation_id}` returns one sanitized event detail.
- `GET /api/dashboard/statistics` returns authoritative decision totals,
  no-plate activity, and seven UTC calendar-day buckets ending today.
- `GET /api/alerts` returns only backend-selected `UNAUTHORIZED` records with
  non-accusatory operational language and bounded pagination.

All timestamps and trend boundaries are timezone-aware UTC. Public schemas do
not contain credentials, buckets, object paths, signed grants, provider
details, or filesystem paths. Evidence is represented only by
`evidence_available`; detail responses label access as `restricted`.
History detail requests expose accessible loading, sanitized not-found,
contract-invalid, timeout, and server-failure states without removing the
history list. Invalid normalized-plate filters are blocked locally with an
accessible message and never trigger an API request.

## Persistence and privacy boundary

Recognition and read endpoints share locked in-memory repositories through a
single application dependency container. Data is process-local and volatile;
restarting the backend may clear detection history, statistics, alerts, and
evidence. Live Supabase database/storage adapters remain unimplemented.

Authentication and role-aware access control are also unimplemented, so Day 14
never returns evidence bytes or access grants. The Day 13 public recognition
response was hardened to replace private evidence references and signed access
with a boolean availability field. The decision, reason, logging status, and
recognition workflow remain authoritative and otherwise unchanged.
The browser runtime parser requires the exact public logging and nested
decision fields and rejects legacy or unexpected private fields.

If process-local no-plate activity cannot be recorded, recognition remains a
no-plate result and the backend emits only a stable failure category and
correlation ID. Raw exceptions and storage/provider details are never logged.

## UI evidence

Run `npm.cmd run evidence:day14` from `frontend` for non-capturing state
verification. To intentionally regenerate the eight images under
`docs/evidence/day14/` in PowerShell, set
`$env:CVPX_CAPTURE_DAY14_EVIDENCE='1'` for that command and remove it afterward.
Playwright uses deterministic intercepted API contracts. These screenshots
demonstrate rendering and state handling only;
they do not prove live detector/OCR accuracy, database performance, Supabase
integration, or production authentication/authorization.
