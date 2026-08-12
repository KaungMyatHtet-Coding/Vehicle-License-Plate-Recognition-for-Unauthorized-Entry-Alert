# Day 7 local OCR evaluation

> Phase 7 classification: the four synthetic crops and their 24 variants per
> mode are development/regression fixtures reused during implementation. They
> are not an independent evaluation set and do not support real-world or
> Myanmar-specific OCR claims.

## Decision

Use RapidOCR 3.9.2 in **recognition-only mode** as the primary OCR baseline for
already detected plate crops. Keep RapidOCR's full
detection/classification/recognition mode as the fallback when a crop includes
padding or its text-line boundary is unreliable.

This is a research choice, not an application integration. Day 7 adds no HTTP
endpoint, schema, model initialization, normalization service, authorization
decision, persistence, alert, camera, video, or frontend behavior.

## Reproducible method

The benchmark consumes the legal project-generated fixtures and labels in
`sample-data/evaluation/ground_truth.json`. It uses the manifest's
exclusive-edge boxes to copy four labeled plate crops; the no-plate image is
retained as a fixture control but correctly supplies no OCR crop. No detector
output is used, so OCR errors are not mixed with detector errors.

For each crop, `scripts/benchmark_ocr.py` measures the untouched original and
the Day 6 grayscale, aspect-preserving 320-pixel resize, bilateral denoise,
CLAHE contrast, and Otsu threshold variants. Each variant is independently
derived from the untouched crop through `PlatePreprocessingService`; there is
no implicit preprocessing chain.

Two modes are measured:

- `rapidocr_recognition_only`: text recognition over the complete known plate
  crop, with text detection and orientation classification disabled.
- `rapidocr_full`: local text detection, classification, and recognition over
  the plate crop.

Normalization for evaluation uppercases text and retains only `A-Z`, `0-9`,
and hyphen. It does not guess ambiguous characters. Character accuracy is
derived from Levenshtein edit distance:
`max(0, expected length - distance) / expected length`. All aggregate values
are computed from the retained raw records.

Run:

```powershell
python -m pip install -r backend\requirements-dev.txt
python -m pip install --no-deps rapidocr==3.9.2
python scripts\benchmark_ocr.py --help
python scripts\benchmark_ocr.py --input sample-data\evaluation
```

The development requirements pin RapidOCR's non-OpenCV dependencies to the
versions in the measured environment. The `--no-deps` installation is
intentional: it prevents RapidOCR's GUI `opencv-python` package-name
requirement from adding a second OpenCV distribution beside the repository's
declared `opencv-python-headless==4.12.0.88`.

The second command overwrites only `docs/day7_ocr_benchmark.json`. That file
contains every raw OCR string, normalized string, confidence, exact-match
outcome, character count, and latency, plus environment and artifact metadata.

## Locally measured results

Environment: Windows 11, Python 3.12.0, OpenCV 4.12.0, ONNX Runtime 1.26.0,
RapidOCR 3.9.2, `CPUExecutionProvider`. The three bundled ONNX files total
31,749,509 bytes. No GPU or network OCR service was used.

| Candidate | Exact matches | Character accuracy | Mean measured latency |
|---|---:|---:|---:|
| RapidOCR recognition-only | 24 / 24 | 240 / 240 (1.000) | 23.374 ms |
| RapidOCR full pipeline | 24 / 24 | 240 / 240 (1.000) | 1997.182 ms |

There are 24 measurements per candidate: four crops times six variants. Every
variant reached 4/4 exact matches in both modes. Recognition-only confidence
ranged down to 0.961860; full-pipeline confidence ranged down to 0.994280.
These engine scores are retained as reported confidence values and are not
claimed to be calibrated probabilities.

The primary is recognition-only because detection already supplies one plate
crop and the measured mean was about 85 times lower on this environment while
accuracy tied. The full pipeline remains a functional local fallback because
it independently locates the text line inside a less precise crop. This
fallback is not an alternate vendor or model family and therefore does not
protect against failures shared by the bundled PP-OCR models.

## Candidate comparison

| Option | License and locality | Size/CPU/confidence | Character evidence | Render assessment | Result |
|---|---|---|---|---|---|
| RapidOCR 3.9.2 | Apache-2.0 project; bundled OCR models are credited to Baidu; entirely local | Published wheel is about 27.3 MB; measured bundled ONNX models are 31.75 MB; ONNX Runtime CPU; returns text scores | 48 real measurements retained for the project's ASCII plate alphabet | Python-compatible and model files ship with the package; no runtime download observed. A deployment smoke test was not performed | Selected: recognition-only primary, full pipeline fallback |
| Tesseract 5 | Apache-2.0; local native binary and trained-data files | CPU native engine; TSV output includes confidence | Not measured because no Tesseract binary was installed in the verified environment | Requires an additional system binary/trained-data installation, increasing native-runtime setup risk | Not selected; no metric claimed |
| EasyOCR | Apache-2.0; local PyTorch models downloaded separately | CPU mode is supported; returns detailed scores; PyTorch/model footprint is materially larger than the selected stack | Not measured or downloaded | Model download/cache and PyTorch increase free-instance cold-start and build risk | Not selected; no metric claimed |

Primary-source references:

- [RapidOCR repository, install, CPU build, credits, and license](https://github.com/RapidAI/RapidOCR)
- [RapidOCR installation and bundled-model size](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/install/)
- [Tesseract repository, formats, language support, and Apache-2.0 license](https://github.com/tesseract-ocr/tesseract)
- [EasyOCR repository, CPU mode and model-download behavior](https://github.com/JaidedAI/EasyOCR)
- [Render FastAPI deployment guide](https://render.com/docs/deploy-fastapi)
- [Render free-service limits and cold starts](https://render.com/docs/free)

## Render feasibility and dependency boundary

Render documents native Python/FastAPI deployment with a requirements-file
build and a Uvicorn start command. RapidOCR's bundled models avoid an
ephemeral-filesystem runtime download. However, no Render deployment or memory
measurement was part of Day 7, and free services spin down after inactivity,
so OCR initialization would add to cold-start latency.

RapidOCR declares the GUI `opencv-python` distribution even though this
repository deliberately uses `opencv-python-headless`. The local benchmark was
run with the existing pinned headless build and worked. The documented
development setup installs RapidOCR 3.9.2 with `--no-deps` after installing its
pinned non-OpenCV dependencies. `python -m pip check` therefore reports the
known metadata-level missing `opencv-python` requirement even though the
compatible headless module is present and the benchmark passes. A deployment
dependency strategy must still be smoke-tested before production OCR
integration. RapidOCR remains development-only; backend production
requirements and imports are unchanged.

## Limitations

- Four synthetic crops and 24 variant samples per mode are enough to compare
  code paths, not to estimate real-world accuracy.
- Fixtures contain clean Latin uppercase letters, digits, spaces, and hyphens.
  Myanmar script, non-Latin plates, blur, glare, rain, night exposure,
  occlusion, severe perspective, and damaged plates were not tested.
- Ground-truth crops avoid detector error. End-to-end accuracy is deferred.
- Timings are single-run wall-clock observations after one engine
  initialization; they are not a throughput, concurrency, memory, or cold-start
  benchmark.
- The no-plate fixture verifies that the manifest has a control, but OCR is not
  called without a labeled crop.
- Confidence thresholds, OCR normalization, empty/low-confidence review
  behavior, and service integration belong to Day 8 and were not implemented.
