import { describe, expect, it } from "vitest";
import { parseVehicle, parseVehicles } from "@/lib/api/vehicles";

const vehicle = { id: "id", normalized_plate: "ABC123", description: null, status: "ACTIVE", valid_from: null, valid_until: null, created_at: "2026-08-06T12:00:00Z", updated_at: "2026-08-06T12:00:00Z" };
describe("vehicle response validation", () => {
  it("accepts the exact public contract", () => expect(parseVehicles({ items: [vehicle], total_items: 1 }).items[0].status).toBe("ACTIVE"));
  it.each([{ ...vehicle, status: "admin" }, { ...vehicle, private_key: "secret" }, { ...vehicle, normalized_plate: "ABC-123" }])("rejects invalid or private fields", (payload) => expect(() => parseVehicle(payload)).toThrow());
});
