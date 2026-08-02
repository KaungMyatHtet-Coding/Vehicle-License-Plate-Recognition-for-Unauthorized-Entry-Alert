# Day 17 bounded short video processing

Day 17 implements bounded short-video license plate recognition by reusing the authoritative still-image recognition pipeline (`RecognitionOrchestrationService`) across sampled video frames without modifying still-image behavior or contracts.

## Architecture and Design

```
User Upload (Video file: .mp4, .avi, .mov <= 25MB, <= 10s)
               │
               ▼
POST /api/recognition/analyze-video
               │
               ▼
VideoValidationService
   ├── Size check (<= 25 MiB)
   ├── Extension check (.mp4, .avi, .mov)
   └── Duration check (<= 10.0s via OpenCV metadata)
               │
               ▼
VideoProcessingService (OpenCV cv2.VideoCapture)
   ├── Frame Sampling (Target FPS: 2.0 FPS -> e.g. every 5th frame for 10 FPS video)
   ├── Frame Extraction -> JPEG bytes
   ├── RecognitionOrchestrationService.recognize(frame_bytes, correlation_id)
   └── Duplicate Suppression (Cooldown: 3.0s per unique plate)
               │
               ▼
VideoProcessingResponse JSON
   ├── correlation_id, filename, total_frames_analyzed, duration_seconds, fps
   ├── unique_plates_count, detections (list of frame outcomes)
   └── timings (extraction_ms, recognition_ms, total_ms)
```

## Input Limits & Constraints

| Metric | Boundary Limit | Enforcement Point | Error Response |
|---|---|---|---|
| **Max File Size** | 25 MiB (26,214,400 bytes) | `VideoProcessingService` | HTTP 400 `VIDEO_OVERSIZED` |
| **Max Duration** | 10.0 seconds | OpenCV VideoCapture | HTTP 400 `VIDEO_DURATION_EXCEEDED` |
| **Allowed Formats** | `.mp4`, `.avi`, `.mov` | File extension inspection | HTTP 400 `VIDEO_FORMAT_UNSUPPORTED` |
| **Empty Payload** | 0 bytes | Stream byte length | HTTP 400 `VIDEO_EMPTY` |

## Duplicate Suppression Rules

To prevent event log spamming during video playback:
- When a license plate is recognized on frame $F_i$ at timestamp $T_i$, its normalized text is checked against `last_seen_times`.
- If $T_i - \text{last\_seen}(plate) < 3.0\text{s}$, the detection is recorded with `suppressed_as_duplicate = True`.
- Subsequent frame detections for the same plate outside the 3-second window refresh the timestamp and set `suppressed_as_duplicate = False`.

## CLI Smoke Testing

Run the CLI smoke script to test video processing locally:

```powershell
python scripts\smoke_video.py --help
python scripts\smoke_video.py
python scripts\smoke_video.py --input sample-data\short-video
```
