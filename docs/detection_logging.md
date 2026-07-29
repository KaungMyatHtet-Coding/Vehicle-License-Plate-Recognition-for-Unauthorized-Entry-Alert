# Day 11 detection logging and private evidence

## Scope

Day 11 records an already-produced Day 10 authorization outcome and associates
it with a privacy-minimized annotated image when evidence succeeds. It adds no
HTTP endpoint, live Supabase connection, alert, frontend, video, camera, or
gate action. All adapters used by the application tests are in memory and
network-free.

## Audit contract

`DetectionLogRecord` retains the Day 8 raw/normalized OCR text, confidence,
OCR status/review reason, finite non-negative timings, correlation ID, and
creation time. The forward Day 11 migration adds:

- the exact `AUTHORIZED`, `UNAUTHORIZED`, or `MANUAL_REVIEW` decision;
- its existing stable Day 10 reason;
- the optional matched authorized-vehicle UUID.

The decision/reason pair is constrained to the Day 10 vocabulary. Authorized
records require a matched vehicle. Existing rows are compatibly backfilled as
manual review using their retained OCR review reason where possible. The
original Day 9 migration is not rewritten.

## Evidence generation and paths

The annotation service decodes a copied source image in memory, validates an
exclusive-edge plate bounding box, draws only that box and the decision/reason,
and emits a deterministic quality-90 JPEG. Re-encoding drops source EXIF and
other unnecessary metadata. The caller's bytes are not mutated.

Evidence paths contain a date prefix and fresh UUID components. They are
relative, traversal-free, independent of raw upload filenames, and always
paired with the configured private bucket. The default bucket is
`detection-evidence`.

The current annotation does not redact faces or unrelated surroundings.
Operators should minimize the captured scene before submission, restrict
access, and establish a lawful operational basis. Face recognition and
unrelated redaction features are outside Day 11.

## Decision preservation and partial failures

The logging service receives a Day 10 result after authorization is complete.
It immediately copies its values into a frozen Day 11 audit snapshot and never
retains, mutates, performs lookup with, or recalculates the caller's mutable
model. Every return includes the same decision values even when evidence work
fails.

Stable partial-failure codes are:

- `LOG_INPUT_INVALID`
- `LOG_TIME_INVALID`
- `ANNOTATION_FAILED`
- `EVIDENCE_STORAGE_FAILED`
- `EVIDENCE_CONFIRMATION_INVALID`
- `EVIDENCE_ORPHAN_UNVERIFIED`
- `LOG_PERSISTENCE_FAILED`
- `EVIDENCE_CLEANUP_SUCCEEDED`
- `EVIDENCE_CLEANUP_FAILED`
- `SIGNED_ACCESS_FAILED`

Annotation or evidence-storage failure still attempts a metadata-only log.
Storage confirmations must match the requested private bucket/path, byte
count, and SHA-256 digest before that reference can be logged or signed.
Mismatched confirmations are rejected. Cleanup targets only the originally
requested operation reference; an adapter-claimed mismatched reference is
untrusted, is never deleted, and is reported as `EVIDENCE_ORPHAN_UNVERIFIED`.
When evidence is stored but log persistence fails, compensating deletion is
attempted. Cleanup is reported as successful only when the deletion
confirmation matches and a separate post-delete check confirms that the object
is absent. Unconfirmed cleanup retains the private evidence reference for
trusted follow-up. Signed-access failure
does not remove the successfully stored evidence or metadata log. Provider
exceptions, filesystem paths, credentials, and dependency internals never
enter the result.

## Private access, retention, and credentials

Configuration defaults:

```text
EVIDENCE_STORAGE_BUCKET=detection-evidence
EVIDENCE_SIGNED_ACCESS_TTL_SECONDS=300
EVIDENCE_RETENTION_DAYS=30
```

Trusted server operators may change these bounded values. Signed access is an
opaque object-bound grant with an expiry, created only by trusted backend code.
The in-memory adapter resolves only known, unexpired grants to defensive byte
copies and revokes grants when their object is deleted. The contract does not
return a public storage URL. A future Supabase adapter must use a
private bucket, least-privilege server operations, and short-lived grants.

Evidence should be deleted when its configured retention period expires.
Orphan cleanup must be retried and audited when compensating deletion fails.
Day 11 documents this policy and exposes the retention setting but does not add
a scheduler.

Any Supabase service-role credential remains server-only. It must never enter a
browser bundle, API result, signed token payload, object path, application log,
fixture, or committed environment file. Live database/storage integration and
production bucket policies remain deferred.

## Verification

```powershell
python -m pytest -p no:cacheprovider backend\tests -k "logging or evidence or storage"
python scripts\validate_schema.py
python -m pytest -p no:cacheprovider backend\tests -k repositor
```

The offline SQL validator checks migration structure only; it is not proof
that a migration was applied to a live Supabase project.
