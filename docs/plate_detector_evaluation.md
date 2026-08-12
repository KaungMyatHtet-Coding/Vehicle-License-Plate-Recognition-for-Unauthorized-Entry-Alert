# Plate-detector evaluation

**Research started:** July 27, 2026
**Primary verification:** July 28, 2026
**Branch:** `research/plate-detector`
**Scope:** Day 4 selection and contract research only; no Day 5 detector
integration is implemented.

## Objective and decision

Select a free local license-plate detector that can run on CPU within the
planned Render Free constraints. The selection distinguishes inference code,
model weights, and training data because each has separate provenance and
license obligations.

**Primary:** `joker5914/yolov8n-license-plate`, immutable Hugging Face revision
`8286762929bd4b111a19186f2a05e0a5940b6088`, using its plate-specific
`best.onnx` artifact with ONNX Runtime.

**Fallback:** this repository's OpenCV contour baseline
`detect_contour`, contract version 1. It is a deterministic heuristic for
degraded operation and comparison, not a substitute for a trained detector.

Standard COCO YOLOv8n weights are explicitly rejected: their 80 COCO classes do
not include a license-plate class.

## Exact primary provenance and publisher declarations

The license labels below are declarations made by the model uploader,
framework publisher, runtime publisher, or dataset publisher. This project
verified that the declarations exist at the cited immutable/current sources;
it did not independently prove ownership of the weights or every dataset
image.

| Item | Observed value or publisher declaration |
|---|---|
| Model name | `joker5914/yolov8n-license-plate` |
| Immutable version | Hugging Face revision `8286762929bd4b111a19186f2a05e0a5940b6088`, dated 2026-05-29 |
| Model uploader source | <https://huggingface.co/joker5914/yolov8n-license-plate> |
| Immutable repository view | <https://huggingface.co/joker5914/yolov8n-license-plate/tree/8286762929bd4b111a19186f2a05e0a5940b6088> |
| Weights URL | <https://huggingface.co/joker5914/yolov8n-license-plate/resolve/8286762929bd4b111a19186f2a05e0a5940b6088/best.onnx?download=true> |
| Expected filename | `best.onnx` |
| Published file size | 12,265,233 bytes |
| Published LFS SHA-256 | `a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9` |
| Model task/class | Single-class license-plate object detection; input documented as 640×640 |
| Weights license declaration | AGPL-3.0, declared by the immutable model repository metadata/model card |
| Training/export framework declaration | Ultralytics YOLOv8n; Ultralytics publishes its code as AGPL-3.0 |
| Local inference code | ONNX Runtime 1.26.0 CPU API; Microsoft publishes ONNX Runtime under MIT |
| Training dataset | `keremberke/license-plate-object-detection`, full configuration |
| Dataset source | <https://huggingface.co/datasets/keremberke/license-plate-object-detection>; upstream Roboflow “Vehicle Registration Plates” dataset version 1 |
| Dataset license declaration | CC BY 4.0, declared by the dataset card |

The model card states that this is YOLOv8n fine-tuned for license-plate
detection on the named dataset for 100 epochs. It provides `best.pt`,
`best.onnx`, and retained training results. The immutable Hugging Face API tree
publishes the ONNX LFS object digest and size above.

### Use and redistribution conditions

- AGPL-3.0 permits educational/demo use, modification, and redistribution of
  the identified weights subject to its conditions, including preserving the
  license/notices and providing corresponding source where the license
  requires it. Network deployment can trigger AGPL source-availability
  obligations. This is a project compliance requirement, not legal advice.
- CC BY 4.0 permits sharing and adaptation of the training dataset, including
  educational use, provided appropriate credit, a license link, and change
  indication are supplied without implying endorsement.
- ONNX Runtime's MIT license permits use and redistribution with its copyright
  and permission notice.
- The framework license is not used as proof of the weights or dataset license;
  each license is recorded from its own source.
- Public GitHub or Hugging Face visibility alone is not treated as an
  open-source grant.

Dataset attribution preserved by this repository: **Vehicle Registration
Plates Dataset**, Augmented Startups, Roboflow, 2022, CC BY 4.0, source
<https://universe.roboflow.com/augmented-startups/vehicle-registration-plates-trudk/dataset/1>.
The original dataset and weights are not redistributed by this repository.
The ignored local verification artifact matched the published SHA-256. Any
future local acquisition must repeat that verification; this repository does
not redistribute the model. License and attribution compliance remains an
explicit unresolved review item.

## Evidence classification

| Property | Primary ONNX model | Contour fallback |
|---|---|---|
| Plate specificity | **Externally published:** model card and named one-class dataset | **Known from local code:** heuristic searches for plate-like rectangles |
| Artifact size | **Externally published:** 12,265,233 bytes | **Known:** no weights |
| Synthetic-fixture result | **Locally measured:** 4/4 fixtures valid; four expected boxes detected | **Locally measured:** 2/4 fixtures valid |
| CPU latency | **Locally measured:** 100.064 ms mean end-to-end adapter time across four fixtures | **Locally measured:** raw result retains per-image timings and environment |
| Process memory | **Locally observed, approximate:** 52.203 MB RSS before load, 72.820 MB after load, 131.266 MB maximum sampled after inference | **Unknown:** not profiled |
| Installed runtime size | **Unknown:** not measured in the target deployment image | **Unknown:** not measured in the target deployment image |
| Render Free fitness | **Estimated:** a 12.3 MB model and CPU ONNX path appear feasible, but deployment memory/cold start remain unmeasured | **Estimated:** no model load, but OpenCV package and process memory remain unmeasured |
| Myanmar-plate quality | **Unknown:** training-set geographic coverage and Myanmar performance were not established | **Unknown:** synthetic shapes do not represent Myanmar road imagery |

The primary was locally downloaded to the ignored `models/day4` directory,
checksum-verified, loaded with ONNX Runtime CPUExecutionProvider, decoded, and
benchmarked through the Day 4 research adapter. This adapter proves candidate
compatibility only; FastAPI lifecycle integration, production error handling,
and crop extraction remain Day 5 work.

The retained local primary run used Python 3.12.0, OpenCV 4.12.0, and ONNX
Runtime 1.26.0. It validated all 4/4 generated fixtures, produced the four
expected boxes, averaged 100.064 ms per image, and recorded IoUs of 0.920556,
0.916384, 0.941885, and 0.946237. Model load took 96.485 ms. Process RSS was
sampled rather than continuously profiled, so 131.266 MB is an observed
approximation, not a proven peak. These synthetic results do not measure
real-world or Myanmar-plate accuracy.

The retained local contour run on Python 3.12.0/OpenCV 4.12.0 processed four
fixtures, produced one detection, validated 2/4 fixtures, and averaged
9.674 ms. Only the yellow fixture's expected box matched (IoU 0.932562); the
white and multi-plate fixtures failed. These results establish that the
fallback is weak and suitable only for explicitly tagged degraded behavior,
not that it has real-world accuracy.

## Candidate comparison

| Candidate | License/provenance result | Resource evidence | Output/integration | Decision |
|---|---|---|---|---|
| Exact `joker5914/yolov8n-license-plate` ONNX revision above | Uploader declares weights AGPL-3.0; dataset publisher declares CC BY 4.0; ONNX Runtime publisher declares MIT | Artifact size/hash verified locally; local CPU timing and sampled RSS retained | Locally verified `[1,3,640,640]` input, `[1,5,8400]` output, one plate class, manual NMS/scaling | **Primary** |
| Standard Ultralytics YOLOv8n COCO | Framework/official weights are identifiable, but COCO has no plate class | Official generic metrics do not measure plate detection | Wrong class contract | Rejected |
| OpenCV DNN with unspecified pretrained model | OpenCV Apache-2.0, but weights/dataset vary and were not identified | Unknown until a model is named | Manual pre/post-processing | Rejected as unresolved |
| Local OpenCV contour baseline | OpenCV Apache-2.0; local project code has repository provenance | No weights; local timing retained | Native original-image boxes; heuristic confidence | **Fallback** |
| PaddleOCR text detector | PaddleOCR Apache-2.0 | Unmeasured locally | Detects text regions, not plate objects | Rejected for detector role |

## Locally inspected ONNX tensor and decoding contract

- Provider: `CPUExecutionProvider`.
- Input: `images`, float32 NCHW `[1, 3, 640, 640]`.
- Preprocessing: decode with OpenCV, preserve aspect ratio with a 640×640
  letterbox filled with value 114, BGR-to-RGB conversion, transpose HWC to
  NCHW, contiguous float32 conversion, and division by 255.
- Output: `output0`, float32 `[1, 5, 8400]`.
- Export metadata: Ultralytics 8.4.56, opset 12, batch 1, static 640×640,
  `nms=False`, class mapping `{0: "license_plate"}`.
- Each anchor supplies `(x_center, y_center, width, height, class_0_score)` in
  letterboxed-input pixels; there is no separate objectness column.
- Candidates use confidence `>= 0.25`. OpenCV NMS is applied at IoU 0.45
  because NMS is not embedded in the model.
- Kept `cxcywh` boxes are converted to corners, letterbox padding is removed,
  coordinates are divided by the resize scale, left/top are rounded down,
  right/bottom are rounded up, and results are clipped to original-image
  bounds before creating `PlateDetection`.

## Detector output contract, version 1

Day 4 defines the localization result only:

```python
@dataclass(frozen=True)
class PlateDetection:
    bbox: tuple[int, int, int, int]
    confidence: float
    label: str
```

- `bbox` is `(x1, y1, x2, y2)` in original-image pixels.
- `x1, y1` are inclusive; `x2, y2` are exclusive.
- All four coordinates are integers; booleans are invalid.
- A valid box has `0 <= x1 < x2 <= image_width` and
  `0 <= y1 < y2 <= image_height`.
- A backend that works on a resized/letterboxed image must remove padding,
  scale coordinates to the original image, round the left/top down and
  right/bottom up, then clip to original bounds before constructing the
  contract object. Exact Day 5 pre/post-processing tests must cover this.
- `confidence` is a finite Python `float` in `[0.0, 1.0]`. The ONNX research
  adapter uses the single-class model score; the contour fallback's value is
  explicitly
  heuristic and must not be interpreted as calibrated probability.
- `label` is the non-empty semantic class. The primary uses
  `license_plate`; the fallback uses `plate_candidate` to avoid presenting a
  heuristic rectangle as a confirmed plate.
- A result list may contain zero, one, or multiple detections and is sorted by
  descending confidence.
- A crop is deliberately absent. `PROJECT_PLAN.md` assigns crop extraction,
  preservation, and failure behavior to Day 5.

`PlateDetection` validates intrinsic field types, ordering, non-negativity,
finite confidence, and label presence. Image-bound validation requires the
original image size and is performed by `validate_detection_bounds`.

## Generated fixtures and ground truth

The four PNG fixtures are generated entirely by
`scripts/generate_test_fixtures.py`; their provenance and reuse boundary are in
`sample-data/evaluation/README.md`. No third-party images or real plates are
included.

`sample-data/evaluation/ground_truth.json` records original-image dimensions,
expected counts, and version-1 boxes. The contract test verifies that every
entry has a corresponding decodable image, dimensions agree, and every box is
inside the image.

These simple fixtures validate the harness and fallback behavior only. They do
not establish real-world detector quality.

## Reproducible local benchmark

From the repository root with the project environment:

```powershell
backend\.venv\Scripts\python.exe scripts\benchmark_detector.py --help
backend\.venv\Scripts\python.exe scripts\benchmark_detector.py `
  --input sample-data\evaluation `
  --backend contour `
  --output docs\day4_contour_benchmark.json
backend\.venv\Scripts\python.exe scripts\benchmark_detector.py `
  --input sample-data\evaluation `
  --backend onnx `
  --model models\day4\best.onnx `
  --output docs\day4_primary_benchmark.json
```

The command writes raw structured results even when counts or boxes miss
ground truth, then exits `1` for an invalid benchmark result. Missing or
malformed ground truth, missing/unreadable images, backend exceptions, or
output-write failures exit non-zero. The ONNX path requires an explicit ignored
model path and refuses a size/hash or tensor-contract mismatch. It is a Day 4
research adapter, not the Day 5 backend service.

The retained `docs/day4_primary_benchmark.json` exits `0` with 4/4 valid
fixtures. The retained `docs/day4_contour_benchmark.json` exits `1` because
two fixtures do not meet the declared count/IoU validity rule. The weak
contour result is accepted only as evidence of degraded fallback behavior; it
is not described as a passing accuracy benchmark.

## Unavailable evidence and limitations

1. Render deployment memory, cold start, and installed-image footprint remain
   unknown.
2. Process RSS was sampled before/after load and after inference; it is not a
   continuously measured peak.
3. No legally cleared real-world evaluation images are present.
4. Dataset geographic coverage and Myanmar-specific performance are unknown.
5. Model-card training metrics are uploader claims and were not reproduced.
6. Synthetic fixture results must not be generalized to road imagery.

## Primary references

- Immutable model revision:
  <https://huggingface.co/joker5914/yolov8n-license-plate/tree/8286762929bd4b111a19186f2a05e0a5940b6088>
- Dataset card and CC BY 4.0 declaration:
  <https://huggingface.co/datasets/keremberke/license-plate-object-detection>
- Ultralytics license:
  <https://github.com/ultralytics/ultralytics/blob/main/LICENSE>
- ONNX Runtime MIT license:
  <https://github.com/microsoft/onnxruntime/blob/main/LICENSE>
- Official COCO class list:
  <https://docs.ultralytics.com/datasets/detect/coco/>
- OpenCV license:
  <https://github.com/opencv/opencv/blob/4.x/LICENSE>
