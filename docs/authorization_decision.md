# Day 10 authorization decision contract

## Scope

Day 10 adds a pure, deterministic service that combines one Day 8 OCR result
with one Day 9 authorized-vehicle lookup. It returns an explainable entry
decision but does not persist anything, upload evidence, send an alert,
operate a gate, accuse a person, or connect to Supabase.

## Input boundaries

Only a Day 8 result with all of the following can reach vehicle lookup:

- `status=recognized` and no review reason;
- non-empty normalized ASCII `A-Z`/`0-9` plate text;
- finite confidence in the inclusive range zero through one;
- confidence greater than or equal to `DECISION_MIN_CONFIDENCE`.

Empty OCR returns `MANUAL_REVIEW / OCR_EMPTY`. A Day 8 low-confidence result
or a recognized result immediately below the decision threshold returns
`MANUAL_REVIEW / OCR_LOW_CONFIDENCE`. Malformed or inconsistent OCR returns
`MANUAL_REVIEW / OCR_RESULT_INVALID`. The service never changes normalized
text or guesses between letter `O` and digit `0`.

The default decision threshold is `0.80`:

```text
DECISION_MIN_CONFIDENCE=0.80
```

It is independently configurable from OCR recognition so deployments may
require a stricter decision boundary without changing the retained OCR result.

## Ordered decision rules

After OCR passes:

| Condition | Decision | Reason |
|---|---|---|
| Exact active match, validity started, not expired | `AUTHORIZED` | `ACTIVE_MATCH` |
| No exact normalized-plate match | `UNAUTHORIZED` | `VEHICLE_NOT_FOUND` |
| Matching inactive record | `UNAUTHORIZED` | `VEHICLE_INACTIVE` |
| Matching blocked record | `UNAUTHORIZED` | `VEHICLE_BLOCKED` |
| Matching record before `valid_from` | `UNAUTHORIZED` | `VEHICLE_NOT_YET_VALID` |
| Matching record at or after `valid_until` | `UNAUTHORIZED` | `VEHICLE_EXPIRED` |
| Malformed or mismatched repository record | `MANUAL_REVIEW` | `VEHICLE_RECORD_INVALID` |
| Repository exception | `MANUAL_REVIEW` | `VEHICLE_LOOKUP_FAILED` |
| Missing, naive, or failed decision clock | `MANUAL_REVIEW` | `DECISION_TIME_INVALID` |

`valid_from` is inclusive and `valid_until` is exclusive. All evaluated and
stored timestamps must be timezone-aware. The service uses exact normalized
plate equality; it performs no fuzzy matching.

`blocked` is a record state, not evidence of wrongdoing. Its public message
only says that the record does not permit entry. Likewise, `UNAUTHORIZED`
means this application found no currently permitting record; it is not an
accusation about a vehicle or person.

## Output

`EntryDecision` contains:

- correlation ID;
- `AUTHORIZED`, `UNAUTHORIZED`, or `MANUAL_REVIEW`;
- stable machine-readable reason;
- sanitized non-accusatory message;
- normalized plate and confidence retained for audit;
- matched vehicle UUID when a valid record exists;
- timezone-aware evaluation timestamp.

The output has no gate, alert, notification, evidence, persistence, or
physical-action field.

## Failure and side-effect policy

Repository errors and unexpected provider exceptions are converted to a
sanitized manual-review result. Raw exceptions, service credentials, database
details, and local paths are never returned. A malformed record or dependency
failure can never produce `AUTHORIZED`.

The service and in-memory repository require no network or filesystem access.
Importing the application still initializes neither detector nor OCR and does
not connect to Supabase. Day 11 logging/evidence behavior remains deferred.
