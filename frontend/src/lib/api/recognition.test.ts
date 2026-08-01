import { describe, expect, it } from "vitest";

import { parseRecognitionResponse } from "@/lib/api/recognition";

function withoutKey<T extends object, K extends keyof T>(value: T, key: K): T {
  const copy = { ...value };
  Reflect.deleteProperty(copy, key);
  return copy;
}

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

const completed = {
  correlation_id: noPlate.correlation_id,
  status: "completed",
  message: "No currently permitting vehicle record was found.",
  detection_count: 1,
  selected_plate: {
    bbox: { x1: 1, y1: 2, x2: 40, y2: 18 },
    confidence: 0.93,
    label: "license_plate",
    crop: { media_type: "image/png", base64_data: "cG5n", width: 39, height: 16 },
  },
  ocr: {
    correlation_id: noPlate.correlation_id,
    status: "recognized",
    review_reason: null,
    raw_text: "ABC123",
    normalized_text: "ABC123",
    confidence: 0.92,
    mode: "recognition_only",
    inference_ms: 2,
    total_ms: 3,
    image_width: 39,
    image_height: 16,
  },
  logging: {
    decision: {
      correlation_id: noPlate.correlation_id,
      decision: "UNAUTHORIZED",
      reason: "VEHICLE_NOT_FOUND",
      message: "No currently permitting vehicle record was found.",
      normalized_plate: "ABC123",
      confidence: 0.92,
      vehicle_id: null,
      evaluated_at: "2026-08-05T12:00:00Z",
    },
    status: "completed",
    failures: [],
    log_persisted: true,
    evidence_available: true,
    completed_at: "2026-08-05T12:00:01Z",
  },
  timings: { detection_ms: 1, ocr_ms: 3, total_ms: 5 },
};

describe("recognition runtime contract", () => {
  it("accepts a consistent no-plate response", () => {
    expect(parseRecognitionResponse(noPlate)).toEqual(noPlate);
  });

  it.each([
    ["AUTHORIZED", "ACTIVE_MATCH", "An active vehicle record permitted entry.", "recognized", null, "22222222-2222-4222-8222-222222222222"],
    ["UNAUTHORIZED", "VEHICLE_NOT_FOUND", "No currently permitting vehicle record was found.", "recognized", null, null],
    ["MANUAL_REVIEW", "OCR_LOW_CONFIDENCE", "Plate text confidence requires manual review.", "manual_review", "OCR_LOW_CONFIDENCE", null],
  ])("accepts a valid %s completed response", (decision, reason, message, ocrStatus, reviewReason, vehicleId) => {
    const payload = {
      ...completed,
      message,
      ocr: { ...completed.ocr, status: ocrStatus, review_reason: reviewReason },
      logging: {
        ...completed.logging,
        decision: {
          ...completed.logging.decision,
          decision,
          reason,
          message,
          vehicle_id: vehicleId,
        },
      },
    };
    expect(parseRecognitionResponse(payload)).toEqual(payload);
  });

  it.each([
    { ...completed, logging: { ...completed.logging, evidence: { object_path: "private/evidence.jpg" } } },
    { ...completed, logging: { ...completed.logging, signed_access: { token: "private" } } },
    { ...completed, logging: { ...completed.logging, private_evidence_path: "C:\\private\\evidence.jpg" } },
    { ...completed, logging: { ...completed.logging, decision: { ...completed.logging.decision, object_path: "private/evidence.jpg" } } },
    { ...completed, logging: { ...completed.logging, decision: { ...completed.logging.decision, signed_access: "private" } } },
    { ...completed, logging: { ...completed.logging, decision: { ...completed.logging.decision, message: undefined } } },
  ])("rejects legacy, private, unexpected, or incomplete completed fields %#", (payload) => {
    expect(() => parseRecognitionResponse(payload)).toThrow();
  });

  it.each([
    ["selected plate", { ...completed, selected_plate: { ...completed.selected_plate, evidence_reference: "private" } }],
    ["bounding box", { ...completed, selected_plate: { ...completed.selected_plate, bbox: { ...completed.selected_plate.bbox, bucket: "private" } } }],
    ["crop object path", { ...completed, selected_plate: { ...completed.selected_plate, crop: { ...completed.selected_plate.crop, object_path: "private/evidence.jpg" } } }],
    ["crop object key", { ...completed, selected_plate: { ...completed.selected_plate, crop: { ...completed.selected_plate.crop, object_key: "private-key" } } }],
    ["crop signed access", { ...completed, selected_plate: { ...completed.selected_plate, crop: { ...completed.selected_plate.crop, signed_access: { token: "private" } } } }],
    ["OCR", { ...completed, ocr: { ...completed.ocr, storage_provider: "private-provider" } }],
    ["timings", { ...completed, timings: { ...completed.timings, token: "private-token" } }],
  ])("rejects an unexpected private field in %s", (_, payload) => {
    expect(() => parseRecognitionResponse(payload)).toThrow("invalid fields");
  });

  it.each([
    ["selected plate", { ...completed, selected_plate: withoutKey(completed.selected_plate, "label") }],
    ["bounding box", { ...completed, selected_plate: { ...completed.selected_plate, bbox: withoutKey(completed.selected_plate.bbox, "x1") } }],
    ["crop", { ...completed, selected_plate: { ...completed.selected_plate, crop: withoutKey(completed.selected_plate.crop, "media_type") } }],
    ["OCR", { ...completed, ocr: withoutKey(completed.ocr, "status") }],
    ["timings", { ...completed, timings: withoutKey(completed.timings, "total_ms") }],
  ])("rejects a missing required field in %s", (_, payload) => {
    expect(() => parseRecognitionResponse(payload)).toThrow("invalid fields");
  });

  it("does not include rejected private payload content in its error", () => {
    const payload = {
      ...completed,
      ocr: { ...completed.ocr, storage_provider: "raw-private-provider-value" },
    };
    try {
      parseRecognitionResponse(payload);
      throw new Error("parser unexpectedly accepted private content");
    } catch (error) {
      expect(error).toBeInstanceOf(Error);
      expect((error as Error).message).toBe("invalid fields");
      expect((error as Error).message).not.toContain("raw-private-provider-value");
    }
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
