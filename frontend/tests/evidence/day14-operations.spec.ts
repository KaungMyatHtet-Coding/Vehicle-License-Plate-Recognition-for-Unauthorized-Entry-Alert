import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const output = path.resolve(process.cwd(), "../docs/evidence/day14");
const captureEvidence = process.env.CVPX_CAPTURE_DAY14_EVIDENCE === "1";
const summary = { correlation_id: "11111111-1111-4111-8111-111111111111", decision: "UNAUTHORIZED", reason: "VEHICLE_NOT_FOUND", reason_message: "No currently permitting vehicle record was found.", normalized_plate: "ABC123", confidence: 0.92, created_at: "2026-08-05T12:00:00Z", evidence_available: true };
const history = { items: [summary], page: 1, page_size: 10, total_items: 1, total_pages: 1, timezone: "UTC" };
const stats = { total_recognitions: 3, authorized: 1, unauthorized: 1, manual_review: 0, no_plate: 1, timezone: "UTC", trend_granularity: "day", trend: [{ bucket_start: "2026-08-05T00:00:00Z", authorized: 1, unauthorized: 1, manual_review: 0, no_plate: 1, total: 3 }] };
const emptyStats = { ...stats, total_recognitions: 0, authorized: 0, unauthorized: 0, no_plate: 0, trend: [] };
const alerts = { items: [{ ...summary, alert_type: "ENTRY_NOT_AUTHORIZED", message: "This record did not permit entry and may require operator review." }], page: 1, page_size: 10, total_items: 1, total_pages: 1, timezone: "UTC" };

async function mock(page: Page, route: string, body: object, status = 200) {
  await page.route(`**${route}*`, async (handler) => handler.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }));
}
async function shot(page: Page, name: string) {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  if (captureEvidence) {
    await page.screenshot({ path: path.join(output, name), fullPage: true });
  }
}

test("dashboard populated", async ({ page }) => { await mock(page, "/api/dashboard/statistics", stats); await page.goto("/dashboard"); await expect(page.getByText("Seven-day recognition trend")).toBeVisible(); await shot(page, "dashboard-populated.png"); });
test("dashboard empty", async ({ page }) => { await mock(page, "/api/dashboard/statistics", emptyStats); await page.goto("/dashboard"); await expect(page.getByText("No recognition activity")).toBeVisible(); await shot(page, "dashboard-empty.png"); });
test("history populated", async ({ page }) => { await mock(page, "/api/detections", history); await page.goto("/history"); await expect(page.getByText("ABC123")).toBeVisible(); await shot(page, "history-populated.png"); });
test("history detail", async ({ page }) => { await mock(page, "/api/detections", history); await mock(page, "/api/detections/11111111-1111-4111-8111-111111111111", { ...summary, timings: { ocr_ms: 2 }, evidence_access: "restricted" }); await page.goto("/history"); await page.getByRole("button", { name: "View" }).click(); await expect(page.getByText("Available, but access is restricted")).toBeVisible(); await shot(page, "history-detail.png"); });
test("history detail not found", async ({ page }) => { await mock(page, "/api/detections", history); await mock(page, "/api/detections/11111111-1111-4111-8111-111111111111", { error: { code: "HTTP_ERROR", message: "The detection record was not found." } }, 404); await page.goto("/history"); await page.getByRole("button", { name: "View" }).click(); await expect(page.getByText("Detection not found")).toBeVisible(); await shot(page, "history-detail-not-found.png"); });
test("history invalid filter", async ({ page }) => { await mock(page, "/api/detections", history); await page.goto("/history"); await page.getByLabel("Normalized plate").fill("ABC-123"); await page.getByRole("button", { name: "Apply filters" }).click(); await expect(page.getByText("Use only letters A–Z and numbers 0–9 for the normalized plate.")).toBeVisible(); await page.getByRole("heading", { name: "Detection history" }).click(); await shot(page, "history-invalid-filter.png"); });
test("alerts populated", async ({ page }) => { await mock(page, "/api/alerts", alerts); await page.goto("/alerts"); await expect(page.getByText("Entry not authorized")).toBeVisible(); await shot(page, "alerts-populated.png"); });
test("server failure", async ({ page }) => { await mock(page, "/api/dashboard/statistics", { error: { code: "SERVICE_UNAVAILABLE", message: "Dashboard statistics are temporarily unavailable." } }, 503); await page.goto("/dashboard"); await expect(page.getByText("Dashboard statistics could not be loaded.")).toBeVisible(); await shot(page, "server-failure.png"); });
