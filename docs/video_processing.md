# Experimental short-video processing (Phase 6)

Phase 6 is an optional localhost-only workflow. It is disabled by default and
does not support live streaming, physical-camera capture, public deployment,
production surveillance, or real-world accuracy/performance claims.

## Enable explicitly

Use an isolated local process and set `ENABLE_EXPERIMENTAL_VIDEO=true` without
committing an actual `.env` file or secret. The default examples keep the flag
`false`. When disabled, `/api/recognition/analyze-video` is absent from OpenAPI
and returns HTTP 404.

The request is multipart with field name `file`:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/recognition/analyze-video `
  -F "file=@sample.mp4"
```

The supported extensions are `.mp4`, `.avi`, and `.mov`. The service validates
the decoded container rather than trusting the filename or MIME type.

## Conservative bounds

Defaults are validated by `Settings` and can only be changed within bounded
limits:

| Setting | Default | Purpose |
|---|---:|---|
| `VIDEO_MAX_UPLOAD_BYTES` | 25 MiB | bounded upload read |
| `VIDEO_MAX_DURATION_SECONDS` | 10 | maximum metadata duration |
| `VIDEO_TARGET_FPS` | 2 | deterministic sampling target |
| `VIDEO_MAX_DECODED_FRAMES` | 300 | hard decoder work limit |
| `VIDEO_MAX_SAMPLED_FRAMES` | 20 | hard analysis limit |
| `VIDEO_MAX_FRAME_WIDTH` / `HEIGHT` | 1920 / 1080 | dimension bounds |
| `VIDEO_MAX_FRAME_PIXELS` | 2,073,600 | pixel bound |
| `VIDEO_CONSENSUS_MIN_OBSERVATIONS` | 2 | exact repeated observations |
| `VIDEO_CONSENSUS_WINDOW_FRAMES` | 8 | bounded retained observations |

Invalid bounds, inconsistent consensus/window settings, empty uploads,
unsupported extensions, malformed metadata, corrupt/zero-frame videos,
decoder failures, oversized frames, and persistence failures fail closed with
stable sanitized error codes. Temporary video files are removed in all normal
success and failure paths.

## Sampling, consensus, and persistence

Frames are decoded sequentially up to the decoded-frame limit. A deterministic
stride respects the target FPS and sampled-frame limit. Each sampled frame is
encoded and sent through the Phase 4 non-persisting `analyze()` boundary.

Only one exact normalized plate can reach finalization. At least the configured
number of matching reliable observations is required. OCR noise, insufficient
observations, unsupported grammar, low confidence, no-plate results, and
distinct reliable plates remain unresolved/manual review. Alternative plates,
raw OCR, frame bytes, and local paths are never returned.

After final consensus and authorization, the representative observation's own
encoded frame, analysis, and correlation ID are persisted at most once. No
individual frame creates a log or evidence. A persistence exception or
unsuccessful logging result returns a sanitized failure rather than a false
success response.

## Response and limitations

The existing experimental response schema is retained. It reports sampled-frame
count, one finalized outcome or one unresolved/no-plate summary, and timings;
`completed` means processing completed, not that external persistence exists.
Memory repositories remain authoritative locally and Supabase is not accessed.
This feature has no independent accuracy evaluation and must not be presented
as production or surveillance capability.
