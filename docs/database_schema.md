# Day 9 Supabase data design

## Scope

Day 9 defines durable PostgreSQL records and backend repository boundaries for
authorized vehicles, OCR detection logs, server settings, and optional evidence
references. It does not connect the application to Supabase, persist a request,
upload evidence, or decide whether a vehicle is authorized. Those behaviors
belong to later milestones.

## Versioned migration

The initial migration is
`supabase/migrations/202607310001_day9_data_model.sql`. It is designed for a
clean Supabase development project and runs in one transaction.

| Table | Purpose and key constraints |
|---|---|
| `authorized_vehicles` | Unique uppercase ASCII-alphanumeric `normalized_plate`; active/inactive/blocked record state; optional validity interval; creation/update timestamps |
| `detection_logs` | Unique correlation ID; Day 8 raw/normalized OCR text, confidence, OCR status/reason, timings, optional paired evidence reference, creation timestamp |
| `app_settings` | Server-owned JSON setting keyed by a constrained lowercase name; creation/update timestamps |

Indexes support vehicle status/validity queries, newest-first detection
history, and normalized-plate history. Triggers maintain `updated_at` for
mutable tables. Detection logs intentionally contain no `AUTHORIZED`,
`UNAUTHORIZED`, or decision column because Day 10 owns that contract.

The migration enables row-level security and revokes table access from the
Supabase `anon` and `authenticated` roles. Day 9 exposes no direct browser data
path and creates no permissive client policy.

## Offline validation

From the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\validate_schema.py
backend\.venv\Scripts\python.exe -m pytest -p no:cacheprovider backend\tests -k repositor
```

The validator performs deterministic structural checks against the retained
migration without a database, Docker, Supabase CLI, credentials, or network.
It verifies the required tables, constraints, indexes, timestamps, RLS,
revocations, transaction boundary, and absence of embedded credentials or Day
10 decision fields. This is documented local validation, not proof that a
remote project or future migration has applied successfully.

When a clean Supabase development project is available, apply migrations with
the official Supabase migration workflow and inspect the resulting tables,
constraints, indexes, triggers, grants, and RLS state before enabling any
integration. Never paste command output containing project references or
credentials into repository files.

## Repository contracts

`backend/app/repositories/contracts.py` provides typed protocols and immutable
records. `backend/app/repositories/memory.py` provides locked, network-free
test implementations that mirror the important database constraints:

- exact normalized-plate format and uniqueness;
- timezone-aware timestamps and ordered validity intervals;
- confidence bounds and Day 8 OCR status/reason consistency;
- paired, relative, traversal-free evidence references;
- unique correlation IDs and non-negative finite timings;
- constrained setting keys and copied JSON-compatible values.

Repository errors have stable codes and safe messages. Mutable dictionaries
are copied at repository boundaries. No repository interprets vehicle status,
makes an authorization decision, performs application initialization, or
writes to disk.

## Evidence bucket and access guidance

Use a private Supabase Storage bucket such as `plate-evidence`; do not make it
public. Store only the bucket name and collision-safe relative object path in
`detection_logs`. Creation of objects, retention, partial-failure behavior, and
signed access are Day 11 work and are deliberately absent here.

Before Day 11 deployment:

1. Create the private bucket through a reviewed server-side migration or
   administrative workflow.
2. Deny public/anonymous object reads and writes.
3. Permit the minimum backend service operations required for a private,
   collision-safe prefix.
4. Use short-lived signed URLs only from trusted server code.
5. Define and enforce evidence retention and deletion behavior.

## Credential rules

- `SUPABASE_SERVICE_ROLE_KEY` is server-only and must never be exposed through
  an API response, browser bundle, log, migration, fixture, or committed file.
- Keep real values in environment/secret management; repository examples
  contain variable names only.
- The future backend adapter must use safe structured errors and must not
  expose Supabase URLs, SQL, policy details, or raw provider exceptions.
- Client-facing code must never use the service-role credential.

No dependency or remote-service setup is required for the Day 9 mock and
schema-validation evidence.
