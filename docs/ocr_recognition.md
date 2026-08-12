# Day 8 OCR and normalization contract

## Scope

Day 8 integrates the free local OCR choice selected on Day 7 for one validated
plate crop. It adds no authorization lookup, accusation, persistence, alert,
frontend, camera, video, or database behavior.

## Endpoint

`POST /api/recognition/recognize-plate` accepts the existing multipart `file`
field. JPEG and PNG validation, byte/dimension limits, transient handling, and
structured error envelopes are unchanged. The input is an already detected
plate crop; this route does not rerun plate detection.

Successful fields:

| Field | Meaning |
|---|---|
| `correlation_id` | Existing request correlation identifier |
| `status` | `recognized` or `manual_review` |
| `review_reason` | `OCR_EMPTY`, `OCR_LOW_CONFIDENCE`, or `null` |
| `raw_text` | Exact selected engine text |
| `normalized_text` | Uppercase ASCII `A-Z` and `0-9` only |
| `confidence` | Selected engine score, or `null` when unavailable |
| `mode` | `recognition_only` or `full_pipeline` |
| `inference_ms` | Selected OCR attempt timing |
| `total_ms` | Decode, copy/preprocessing, all OCR attempts, and response preparation |
| `image_width`, `image_height` | Validated crop dimensions |

## Recognition lifecycle

`PlateOcrService` is cheap to construct. It imports and initializes RapidOCR
only on the first OCR call, under a lock, then reuses that engine for later
calls. Application import, health, image validation, and plate detection do
not load OCR.

Every RapidOCR detection, classification, and recognition session must expose
exactly `CPUExecutionProvider`. The service requires RapidOCR 3.9.2 and returns
safe structured errors for a missing, unsupported, unloadable, invalid-output,
or failed runtime without exposing model paths or exception details.

Recognition-only is the primary. It receives the copied original returned by
an empty Day 6 preprocessing selection, so neither the caller's crop nor an
implicit transformation chain is introduced. If the primary is empty or below
`OCR_MIN_CONFIDENCE`, and `OCR_FULL_PIPELINE_FALLBACK=true`, the documented
full pipeline runs on that same copied crop. A non-empty higher-confidence
fallback is selected; otherwise the primary remains selected.

## Normalization and review

Normalization is a separate pure function:

```text
YGN 5A-1234 -> YGN5A1234
  ygn_5a/1234 -> YGN5A1234
O0 0O -> O00O
```

It uppercases and retains only ASCII letters and digits. Whitespace,
separators, punctuation, and unsupported characters are removed. It never
substitutes similar-looking characters such as letter `O` and digit `0`.

- An empty normalized result returns `manual_review` / `OCR_EMPTY`.
- A non-empty result below `OCR_MIN_CONFIDENCE` returns
  `manual_review` / `OCR_LOW_CONFIDENCE`.
- A result meeting the threshold returns `recognized`.

When used by the still-image orchestration, recognition also applies the
configured conservative plate grammar (`YGN`, `MDY`, and `NPT` by default),
bounded normalized length, and a required numeric component. Unsupported
plausible prefixes and alphabetic watermark text such as `ALAMY` remain manual
review. Separators are normalized before this check; no fuzzy character
substitution is performed.

These statuses describe OCR reliability only. They are not `AUTHORIZED` or
`UNAUTHORIZED`; those decisions belong to later milestones.

## Configuration and dependency boundary

```text
OCR_MIN_CONFIDENCE=0.80
OCR_FULL_PIPELINE_FALLBACK=true
MAX_RECOGNITION_CANDIDATES=3
SUPPORTED_PLATE_REGIONS=YGN,MDY,NPT
MIN_PLATE_LENGTH=7
MAX_PLATE_LENGTH=12
CANDIDATE_AMBIGUITY_MARGIN=0.08
```

The 0.80 default is a configurable conservative development value, not a
calibrated real-world threshold. Day 7 measured clean synthetic samples only.

RapidOCR retains the Day 7 installation boundary:

```powershell
python -m pip install -r backend\requirements-dev.txt
python -m pip install --no-deps rapidocr==3.9.2
```

This deliberately preserves `opencv-python-headless` and avoids installing GUI
`opencv-python` beside it. OCR model files remain package-local inside the
ignored virtual environment and are not tracked by the repository.
