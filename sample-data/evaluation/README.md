# Day 4 detector-evaluation fixtures

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
