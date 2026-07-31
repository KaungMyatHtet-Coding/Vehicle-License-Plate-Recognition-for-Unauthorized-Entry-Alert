# Day 13 recognition interface

## Scope

Day 13 connects the existing secure image, detector, preprocessing/OCR,
decision, logging, and private-evidence boundaries to one browser workflow. It
does not add dashboard/history queries, alerts, authentication, camera input,
vehicle management, a live Supabase adapter, or gate control.

## Authoritative endpoint

`POST /api/recognition/analyze` accepts one multipart field named `file`.
JPEG and PNG uploads pass through the existing Day 3 byte, MIME, extension,
decoded-format, dimension, and corruption checks. The validated bytes remain
transient in the request.

The backend then:

1. detects plate candidates and selects the existing confidence-sorted first
   candidate as the primary plate;
2. returns `no_plate_detected` without inventing OCR or authorization data
   when no candidate exists;
3. passes the lossless primary crop to the Day 8 OCR service, which already
   uses the Day 6 non-destructive preprocessing boundary and conservative
   normalization;
4. passes the OCR result to the Day 10 decision service;
5. passes the unchanged decision, original image, primary bounding box, OCR,
   and timings to Day 11 logging/evidence;
6. returns the selected crop, OCR values, frozen authoritative decision,
   logging/evidence status, correlation ID, and safe timings.

Expected pipeline failures use the established structured error envelope.
Unexpected failures return `RECOGNITION_FAILED` without provider exceptions,
paths, or credentials. Browser CORS permits only the existing configured
frontend origins and the required `GET`/`POST` methods, without credentials.

## Browser states

The Recognition page supports idle, selected/previewed, running, authorized,
unauthorized, manual-review, no-plate, invalid-file, timeout, network, and
server-failure states. A selected image can be replaced or removed. The submit
button and an immediate in-memory guard prevent duplicate requests. Local blob
preview URLs are revoked on replacement, reset, and unmount. Reset clears the
result so another image can be analyzed.

The browser runtime-validates the complete success contract and never computes
or changes a decision. It displays the private-evidence/log status but does not
expose the bucket, object path, or signed-access token.

## Persistence and limitations

The orchestration uses the existing Day 9/11 in-memory repository and private
storage adapters. Successful process-local runs can record metadata and
evidence, but those values do not survive a restart. No migration is needed.
A live Supabase adapter remains deferred by the existing Day 11 contract.
Until authorized-vehicle integration is added, the default empty process-local
vehicle repository cannot produce an authorized match; deterministic dependency
fakes cover authorized behavior without bypassing production rules.

Automated tests cover all result and failure states without model weights,
external services, hardware, or live OCR. Six desktop browser screenshots are
retained under `docs/evidence/day13/`. Playwright drives system-installed
Chrome and deterministically intercepts the analyze request with valid
documented response contracts. These screenshots prove frontend rendering and
state handling, not live detector/OCR/database accuracy.
