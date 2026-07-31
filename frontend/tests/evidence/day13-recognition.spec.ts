import { expect, test, type Page } from "@playwright/test";
import { readFile } from "node:fs/promises";
import path from "node:path";

const correlationId = "11111111-1111-4111-8111-111111111111";
const screenshotDirectory = path.resolve(
  process.cwd(),
  "../docs/evidence/day13",
);
const vehicleFixture = path.resolve(
  process.cwd(),
  "../sample-data/evaluation/synthetic_plate_white.png",
);

type Decision = "AUTHORIZED" | "UNAUTHORIZED" | "MANUAL_REVIEW";

const decisionDetails = {
  AUTHORIZED: {
    reason: "ACTIVE_MATCH",
    message: "The vehicle record permits entry at this time.",
    confidence: 0.94,
    vehicleId: "22222222-2222-4222-8222-222222222222",
  },
  UNAUTHORIZED: {
    reason: "VEHICLE_NOT_FOUND",
    message: "No matching vehicle record permits entry.",
    confidence: 0.92,
    vehicleId: null,
  },
  MANUAL_REVIEW: {
    reason: "OCR_LOW_CONFIDENCE",
    message: "Plate text confidence is too low; manual review is required.",
    confidence: 0.62,
    vehicleId: null,
  },
} as const;

async function completedResponse(decision: Decision) {
  const detail = decisionDetails[decision];
  const crop = (await readFile(vehicleFixture)).toString("base64");
  return {
    correlation_id: correlationId,
    status: "completed",
    message: detail.message,
    detection_count: 1,
    selected_plate: {
      bbox: { x1: 120, y1: 150, x2: 520, y2: 260 },
      confidence: 0.96,
      label: "license_plate",
      crop: {
        media_type: "image/png",
        base64_data: crop,
        width: 640,
        height: 360,
      },
    },
    ocr: {
      correlation_id: correlationId,
      status: decision === "MANUAL_REVIEW" ? "manual_review" : "recognized",
      review_reason:
        decision === "MANUAL_REVIEW" ? "OCR_LOW_CONFIDENCE" : null,
      raw_text: "YGN 5A-1234",
      normalized_text: "YGN5A1234",
      confidence: detail.confidence,
      mode: "recognition_only",
      inference_ms: 42.4,
      total_ms: 48.8,
      image_width: 400,
      image_height: 110,
    },
    logging: {
      decision: {
        correlation_id: correlationId,
        decision,
        reason: detail.reason,
        message: detail.message,
        normalized_plate: "YGN5A1234",
        confidence: detail.confidence,
        vehicle_id: detail.vehicleId,
        evaluated_at: "2026-08-04T09:00:00Z",
      },
      status: "completed",
      failures: [],
      log_persisted: true,
      evidence: {
        bucket: "redacted-private-bucket",
        object_path: "redacted/private-object.jpg",
      },
      signed_access: null,
      completed_at: "2026-08-04T09:00:01Z",
    },
    timings: {
      detection_ms: 71.2,
      ocr_ms: 48.8,
      total_ms: 126.5,
    },
  };
}

function noPlateResponse() {
  return {
    correlation_id: correlationId,
    status: "no_plate_detected",
    message:
      "No license plate was detected; try another image or review it manually.",
    detection_count: 0,
    selected_plate: null,
    ocr: null,
    logging: null,
    timings: {
      detection_ms: 68.1,
      ocr_ms: 0,
      total_ms: 68.3,
    },
  };
}

async function openWithVehicle(page: Page) {
  await page.goto("/recognition");
  await page
    .getByLabel("Select vehicle image")
    .setInputFiles(vehicleFixture);
  await expect(page.getByAltText(/Preview of/)).toBeVisible();
}

async function capture(page: Page, filename: string) {
  await expect(
    page.getByRole("heading", { name: "Recognition", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(screenshotDirectory, filename),
    fullPage: true,
    animations: "disabled",
  });
}

for (const state of [
  ["AUTHORIZED", "authorized.png"],
  ["UNAUTHORIZED", "unauthorized.png"],
  ["MANUAL_REVIEW", "manual-review.png"],
] as const) {
  test(`captures ${state[0].toLowerCase()} rendering`, async ({ page }) => {
    await page.route("**/api/recognition/analyze", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(await completedResponse(state[0])),
      });
    });
    await openWithVehicle(page);
    await page.getByRole("button", { name: "Analyze image" }).click();
    await expect(
      page.getByRole("heading", {
        name: state[0].replace("_", " "),
      }),
    ).toBeVisible();
    await expect(page.getByText(decisionDetails[state[0]].reason)).toBeVisible();
    await expect(page.getByText("YGN5A1234")).toBeVisible();
    await capture(page, state[1]);
  });
}

test("captures no-plate rendering", async ({ page }) => {
  await page.route("**/api/recognition/analyze", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(noPlateResponse()),
    });
  });
  await openWithVehicle(page);
  await page.getByRole("button", { name: "Analyze image" }).click();
  await expect(page.getByText("No plate detected")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Manual inspection needed" }),
  ).toBeVisible();
  await capture(page, "no-plate.png");
});

test("captures invalid-file rendering", async ({ page }) => {
  await page.goto("/recognition");
  await page.getByLabel("Select vehicle image").setInputFiles({
    name: "unsupported.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not an image"),
  });
  const alert = page.locator(
    'section[aria-labelledby="recognition-result"] [role="alert"]',
  );
  await expect(alert).toContainText("Image not accepted");
  await expect(alert).toContainText(
    "Choose a JPEG or PNG image.",
  );
  await capture(page, "invalid-file.png");
});

test("captures sanitized server-failure rendering", async ({ page }) => {
  await page.route("**/api/recognition/analyze", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "RECOGNITION_FAILED",
          message: "Recognition could not be completed.",
          correlation_id: correlationId,
        },
      }),
    });
  });
  await openWithVehicle(page);
  await page.getByRole("button", { name: "Analyze image" }).click();
  await expect(
    page.getByRole("heading", { name: "Recognition unavailable" }),
  ).toBeVisible();
  const alert = page.locator(
    'section[aria-labelledby="recognition-result"] [role="alert"]',
  );
  await expect(alert).toContainText(
    "Recognition could not be completed.",
  );
  await expect(alert).toContainText(correlationId);
  await capture(page, "server-failure.png");
});
