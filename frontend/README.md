# CVPX frontend foundation

This directory contains the Day 12 Next.js App Router foundation for the CVPX
operations interface. It provides responsive navigation and placeholder routes
for:

- `/dashboard`
- `/recognition`
- `/history`
- `/alerts`
- `/authorized-vehicles`

Day 13 replaces the Recognition placeholder with a complete still-image
workflow. Day 14 adds server-derived dashboard statistics, filtered/paginated
history and detail, and backend-selected alerts. Vehicle management remains a
foundation-only route.

## Local setup

Use Node.js 20.9 or newer:

```powershell
cd frontend
npm.cmd ci
Copy-Item .env.example .env.local
npm.cmd run dev
```

`NEXT_PUBLIC_API_BASE_URL` is the only browser-visible configuration value. It
must contain only the public HTTP(S) origin/path of the CVPX backend. Never put
Supabase service-role credentials, storage tokens, model paths, or other
secrets in a `NEXT_PUBLIC_` variable.

The localhost fallback is development/test-only. Production must provide an
explicit valid `NEXT_PUBLIC_API_BASE_URL`; missing or unsafe configuration
fails closed before any request is issued.

## API boundary

`src/lib/api/types.ts` mirrors the stable backend schemas through Day 11.
`src/lib/api/client.ts` validates base and contained endpoint URLs, bounds
request timeouts, accepts authoritative structured backend errors, requires an
operation-level success parser, and replaces malformed/network/provider
failures with safe messages. It does not call an API during import or page
rendering.

## Verification

```powershell
npm.cmd run test
npm.cmd run lint
npm.cmd run type-check
npm.cmd run build
npm.cmd run evidence:day13
npm.cmd run evidence:day14
npm.cmd audit
```

The shell includes a keyboard skip link, semantic navigation/main landmarks,
descriptive page headings and metadata, visible focus treatment, reduced-motion
handling, minimum-size actions, mobile horizontal navigation, and a persistent
desktop sidebar.

## Recognition workflow

The browser submits one JPEG/PNG as multipart data to
`POST /api/recognition/analyze`. It runtime-validates the complete response and
displays only the backend's authoritative decision/reason, OCR data, selected
plate crop, safe processing metrics, and private evidence/log availability.
Blob preview URLs are revoked when replaced, reset, or unmounted. See
[`docs/recognition_interface.md`](../docs/recognition_interface.md).

The evidence command uses the installed system Chrome and deterministic
request interception to regenerate the six UI-state screenshots in
`docs/evidence/day13/`. It is development evidence only and does not bypass or
modify production recognition behavior.

Day 14 operational responses are runtime-validated and expose evidence only as
an availability boolean. History is process-local and volatile; restarting the
backend may clear it. Live Supabase persistence and authenticated evidence
access remain unimplemented.
Completed recognition parsing rejects unexpected fields at every nested public
object boundary and has direct parser coverage for every supported decision
outcome. History detail failures and invalid filters use sanitized accessible
feedback without clearing the history list.

`npm.cmd run evidence:day14` verifies the deterministic Day 14 Playwright
states without changing screenshots. To intentionally capture them in
PowerShell, set `$env:CVPX_CAPTURE_DAY14_EVIDENCE='1'` for that command and
remove the environment variable afterward.

The Day 15 Authorized vehicles route supports create, search, status filter, confirmed
edit/status operations, and optional validity dates through sanitized backend APIs. It
contains no service credential and inherits the backend's process-local limitation.
