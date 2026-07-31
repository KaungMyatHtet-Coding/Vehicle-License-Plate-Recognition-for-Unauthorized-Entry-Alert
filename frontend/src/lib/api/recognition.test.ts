import { describe, expect, it } from "vitest";

import { parseRecognitionResponse } from "@/lib/api/recognition";

const noPlate = {
  correlation_id: "11111111-1111-4111-8111-111111111111",
  status: "no_plate_detected",
  message: "No plate detected.",
  detection_count: 0,
  selected_plate: null,
  ocr: null,
  logging: null,
  timings: { detection_ms: 1, ocr_ms: 0, total_ms: 1 },
};

describe("recognition runtime contract", () => {
  it("accepts a consistent no-plate response", () => {
    expect(parseRecognitionResponse(noPlate)).toEqual(noPlate);
  });

  it.each([
    { ...noPlate, detection_count: 1 },
    { ...noPlate, status: "completed" },
    { ...noPlate, timings: { detection_ms: -1, ocr_ms: 0, total_ms: 1 } },
    { ...noPlate, private_provider_detail: "secret" },
  ])("rejects an invalid or inconsistent response %#", (payload) => {
    expect(() => parseRecognitionResponse(payload)).toThrow();
  });
});
