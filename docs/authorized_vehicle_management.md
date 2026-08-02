# Day 15 authorized-vehicle management

Day 15 adds server-authoritative, process-local authorized-vehicle management at
`/api/authorized-vehicles` and connects the Authorized vehicles page to it.

Implemented behavior includes create, list, read, replace, and status-update APIs;
conservative uppercase letter/digit normalization; normalized uniqueness; plate
search; `ACTIVE`, `INACTIVE`, and `BLOCKED` filters; and timezone-aware validity
boundaries. Important UI edits and status changes require confirmation. There is
intentionally no destructive delete endpoint. The existing decision engine reads the
same repository, so later recognition reflects status and validity changes.

Invalid and extra input fails closed. Responses do not include credentials, storage
references, private paths, provider details, or raw exceptions.

## Prototype limitations

Records remain in the shared in-memory application dependency and are lost on process
restart. Authentication, operator audit identities, and live Supabase persistence are
not implemented. This prototype is not production-ready.
