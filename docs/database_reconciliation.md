# Phase 2 database reconciliation status

Phase 2 defines the canonical local repository vocabulary from the Day 9
schema plus the Day 11 outcome fields. The optional Supabase adapters map only
those canonical columns:

- vehicles use `normalized_plate` and lowercase internal statuses;
- detection logs retain OCR status/reason, decision/reason, matched vehicle,
  evidence bucket/object, timings, and timestamps;
- vehicle creation uses insert semantics and updates target an existing ID.

The retained historical migrations are inspection inputs only. The Day 19
`20260802000000_initial_schema.sql` uses conflicting names and semantics such
as `plate_number`, uppercase statuses, a string correlation ID, and a reduced
detection-log shape. It cannot safely be treated as part of the Day 9/11
canonical chain. `scripts/validate_schema.py` reports this conflict and also
reports that the live Supabase migration ledger is unknown.

No Supabase project was inspected, contacted, or migrated. Reconciliation is
blocked until an authorized export of the live migration ledger and schema is
available. Do not apply, reorder, delete, or rewrite the historical SQL files
to resolve this finding.

The default localhost application remains memory-backed and network-free.
Supabase adapters require explicit schema-readiness evidence; otherwise they
fail closed with `SUPABASE_SCHEMA_NOT_READY`. `schema_ready=True` is currently
used only by deterministic adapter contract tests; no runtime configuration or
user-provided environment value may self-assert readiness. Production
activation remains blocked pending authorized ledger/schema evidence and a
later reviewed readiness mechanism. A structured PostgreSQL unique-violation
code maps vehicle normalized-plate conflicts to the duplicate error. Detection
log unique violations remain generic because the structured code alone cannot
safely distinguish a correlation-ID constraint from another unique constraint.
