# Day 4 detector-evaluation fixtures

## Phase 7 evaluation classification

This directory contains exactly four project-generated synthetic educational
fixtures: three positive images, one negative/no-plate image, and four labeled
plate instances. The same fixtures were used during development and regression
tests, so they are not an independent evaluation set and must not support
real-world precision, recall, OCR, or latency claims.

The fixtures represent clean programmatic plate-like rectangles with Latin
uppercase text, digits, and simple colors. They do not represent blur, glare,
rain, night exposure, occlusion, perspective, damaged plates, Myanmar script,
traffic scenes, or demographic/owner data. No legally independent evaluation
set is present in this repository. The fixture generator and labels are
project-owned educational material; the repository has no top-level license,
so broader redistribution rights remain unresolved. A future independent set
must be legally usable, consent-aware where private images are involved, and
must not be committed without an explicit provenance decision.

The four PNG files in this directory are project-generated test fixtures.
`scripts/generate_test_fixtures.py` creates every pixel programmatically and
writes the matching `ground_truth.json`; no third-party photograph, dataset,
model output, personal data, or external artwork is incorporated.

The repository owner supplied and controls these project fixtures for use in
this project and its educational demonstration. The repository currently has
no top-level license, so this provenance statement does not grant third parties
a broader redistribution license. A future repository-wide license decision
must be made by the repository owner.

Bounding boxes use integer `(x1, y1, x2, y2)` pixel coordinates in the original
image. `x1, y1` are inclusive and `x2, y2` are exclusive. Every box is clipped
to its image bounds and has positive width and height.
