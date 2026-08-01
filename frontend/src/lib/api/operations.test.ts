import { describe, expect, it } from "vitest";

import { parseAlerts, parseHistory, parseStatistics } from "@/lib/api/operations";

const summary = {
  correlation_id: "11111111-1111-4111-8111-111111111111",
  decision: "UNAUTHORIZED",
  reason: "VEHICLE_NOT_FOUND",
  reason_message: "No currently permitting vehicle record was found.",
  normalized_plate: "ABC123",
  confidence: 0.9,
  created_at: "2026-08-05T12:00:00Z",
  evidence_available: true,
};

describe("Day 14 runtime contracts", () => {
  it("accepts sanitized history and rejects private fields", () => {
    const payload = { items: [summary], page: 1, page_size: 10, total_items: 1, total_pages: 1, timezone: "UTC" };
    expect(parseHistory(payload).items[0].decision).toBe("UNAUTHORIZED");
    expect(() => parseHistory({ ...payload, items: [{ ...summary, object_path: "private/x.jpg" }] })).toThrow();
  });

  it("validates server-derived statistics", () => {
    const payload = { total_recognitions: 1, authorized: 0, unauthorized: 1, manual_review: 0, no_plate: 0, timezone: "UTC", trend_granularity: "day", trend: [{ bucket_start: "2026-08-05T00:00:00Z", authorized: 0, unauthorized: 1, manual_review: 0, no_plate: 0, total: 1 }] };
    expect(parseStatistics(payload).total_recognitions).toBe(1);
    expect(() => parseStatistics({ ...payload, timezone: "local" })).toThrow();
  });

  it("accepts only backend-selected unauthorized alerts", () => {
    const payload = { items: [{ ...summary, alert_type: "ENTRY_NOT_AUTHORIZED", message: "Operator review may be required." }], page: 1, page_size: 10, total_items: 1, total_pages: 1, timezone: "UTC" };
    expect(parseAlerts(payload).items).toHaveLength(1);
    expect(() => parseAlerts({ ...payload, items: [{ ...payload.items[0], decision: "AUTHORIZED" }] })).toThrow();
  });
});
