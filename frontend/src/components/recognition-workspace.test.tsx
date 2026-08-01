import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RecognitionWorkspace } from "@/components/recognition-workspace";
import { ApiRequestError } from "@/lib/api/client";
import type {
  DecisionReason,
  DecisionStatus,
  RecognitionResponse,
} from "@/lib/api/types";

const CORRELATION_ID = "11111111-1111-4111-8111-111111111111";
const CROP = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ";

function response(
  decision: DecisionStatus = "AUTHORIZED",
  reason: DecisionReason = "ACTIVE_MATCH",
): RecognitionResponse {
  const message = {
    AUTHORIZED: "The vehicle record permits entry at this time.",
    UNAUTHORIZED: "No matching vehicle record permits entry.",
    MANUAL_REVIEW: "Plate text confidence is too low; manual review is required.",
  }[decision];
  return {
    correlation_id: CORRELATION_ID,
    status: "completed",
    message,
    detection_count: 1,
    selected_plate: {
      bbox: { x1: 1, y1: 2, x2: 40, y2: 18 },
      confidence: 0.92,
      label: "license_plate",
      crop: {
        media_type: "image/png",
        base64_data: CROP,
        width: 39,
        height: 16,
      },
    },
    ocr: {
      correlation_id: CORRELATION_ID,
      status: decision === "MANUAL_REVIEW" ? "manual_review" : "recognized",
      review_reason: decision === "MANUAL_REVIEW" ? "OCR_LOW_CONFIDENCE" : null,
      raw_text: "ABC 123",
      normalized_text: "ABC123",
      confidence: decision === "MANUAL_REVIEW" ? 0.62 : 0.94,
      mode: "recognition_only",
      inference_ms: 3,
      total_ms: 4,
      image_width: 39,
      image_height: 16,
    },
    logging: {
      decision: {
        correlation_id: CORRELATION_ID,
        decision,
        reason,
        message,
        normalized_plate: "ABC123",
        confidence: decision === "MANUAL_REVIEW" ? 0.62 : 0.94,
        vehicle_id: decision === "AUTHORIZED" ? "vehicle-id" : null,
        evaluated_at: "2026-08-04T09:00:00Z",
      },
      status: "completed",
      failures: [],
      log_persisted: true,
      evidence_available: true,
      completed_at: "2026-08-04T09:00:01Z",
    },
    timings: { detection_ms: 2, ocr_ms: 4, total_ms: 7 },
  };
}

function noPlate(): RecognitionResponse {
  return {
    correlation_id: CORRELATION_ID,
    status: "no_plate_detected",
    message: "No license plate was detected; try another image or review it manually.",
    detection_count: 0,
    selected_plate: null,
    ocr: null,
    logging: null,
    timings: { detection_ms: 2, ocr_ms: 0, total_ms: 2 },
  };
}

function file(name = "vehicle.jpg", type = "image/jpeg") {
  return new File(["image"], name, { type });
}

function choose(selected = file()) {
  fireEvent.change(screen.getByLabelText("Select vehicle image"), {
    target: { files: [selected] },
  });
}

describe("recognition workspace", () => {
  const createObjectURL = vi.fn();
  const revokeObjectURL = vi.fn();

  beforeEach(() => {
    createObjectURL.mockClear();
    let previewNumber = 0;
    createObjectURL.mockImplementation(() => {
      previewNumber += 1;
      return `blob:preview-${previewNumber}`;
    });
    revokeObjectURL.mockClear();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });
  });

  it.each([
    ["AUTHORIZED", "ACTIVE_MATCH", "AUTHORIZED"],
    ["UNAUTHORIZED", "VEHICLE_NOT_FOUND", "UNAUTHORIZED"],
    ["MANUAL_REVIEW", "OCR_LOW_CONFIDENCE", "MANUAL REVIEW"],
  ] as const)("renders the authoritative %s result", async (decision, reason, label) => {
    render(<RecognitionWorkspace analyze={vi.fn().mockResolvedValue(response(decision, reason))} />);
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Analyze image" }));

    expect(await screen.findByRole("heading", { name: label })).toBeDefined();
    expect(screen.getByText(reason)).toBeDefined();
    expect(screen.getByAltText("Detected license plate crop")).toBeDefined();
    expect(screen.getByText(/Evidence: stored privately/)).toBeDefined();
  });

  it("renders the no-plate outcome without inventing a decision", async () => {
    render(<RecognitionWorkspace analyze={vi.fn().mockResolvedValue(noPlate())} />);
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Analyze image" }));

    expect(await screen.findByText("No plate detected")).toBeDefined();
    expect(screen.queryByText("Authoritative result")).toBeNull();
  });

  it("rejects an invalid local file before sending it", () => {
    const analyze = vi.fn();
    render(<RecognitionWorkspace analyze={analyze} />);
    choose(file("notes.txt", "text/plain"));

    expect(screen.getByRole("alert").textContent).toContain("Choose a JPEG or PNG image.");
    expect(
      (screen.getByRole("button", { name: "Analyze image" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(analyze).not.toHaveBeenCalled();
  });

  it.each([
    [
      new ApiRequestError(
        "RECOGNITION_FAILED",
        "Recognition could not be completed.",
        500,
        CORRELATION_ID,
      ),
      "Recognition unavailable",
      CORRELATION_ID,
    ],
    [
      new ApiRequestError("API_REQUEST_TIMEOUT", "timed out", null, null),
      "Recognition timed out",
      "",
    ],
    [
      new ApiRequestError("API_UNAVAILABLE", "unavailable", null, null),
      "Network unavailable",
      "",
    ],
  ])("shows a safe request failure", async (failure, title, reference) => {
    render(<RecognitionWorkspace analyze={vi.fn().mockRejectedValue(failure)} />);
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Analyze image" }));

    expect(await screen.findByRole("heading", { name: title })).toBeDefined();
    if (reference) expect(screen.getByText(`Reference: ${reference}`)).toBeDefined();
  });

  it("previews, replaces, removes, and resets while revoking object URLs", async () => {
    const analyze = vi.fn().mockResolvedValue(response());
    render(<RecognitionWorkspace analyze={analyze} />);
    choose(file("first.jpg"));
    expect(screen.getByAltText("Preview of first.jpg")).toBeDefined();

    choose(file("second.png", "image/png"));
    expect(screen.getByAltText("Preview of second.png")).toBeDefined();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:preview-1");

    fireEvent.click(screen.getByRole("button", { name: "Analyze image" }));
    await screen.findByText("Authoritative result");
    fireEvent.click(screen.getByRole("button", { name: "Analyze another image" }));

    expect(screen.getByText("No image selected")).toBeDefined();
    expect(screen.queryByAltText("Preview of second.png")).toBeNull();
    expect(revokeObjectURL).toHaveBeenCalledTimes(2);
  });

  it("prevents duplicate submissions while a request is pending", async () => {
    let resolve: ((value: RecognitionResponse) => void) | undefined;
    const analyze = vi.fn(
      () =>
        new Promise<RecognitionResponse>((done) => {
          resolve = done;
        }),
    );
    render(<RecognitionWorkspace analyze={analyze} />);
    choose();
    const submit = screen.getByRole("button", { name: "Analyze image" });
    fireEvent.click(submit);
    fireEvent.click(submit);

    expect(analyze).toHaveBeenCalledOnce();
    expect(
      (screen.getByRole("button", { name: "Analyzing…" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    resolve?.(response());
    await waitFor(() => expect(screen.getByText("Authoritative result")).toBeDefined());
  });
});
