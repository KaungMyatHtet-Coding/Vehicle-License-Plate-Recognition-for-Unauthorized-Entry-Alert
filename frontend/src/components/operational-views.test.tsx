import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AlertsView, DashboardView, HistoryView } from "@/components/operational-views";
import { getAlerts, getDetection, getHistory, getStatistics } from "@/lib/api/operations";
import { ApiRequestError } from "@/lib/api/client";

vi.mock("@/lib/api/operations", () => ({ getAlerts: vi.fn(), getDetection: vi.fn(), getHistory: vi.fn(), getStatistics: vi.fn() }));

const summary = { correlation_id: "11111111-1111-4111-8111-111111111111", decision: "UNAUTHORIZED" as const, reason: "VEHICLE_NOT_FOUND" as const, reason_message: "No currently permitting vehicle record was found.", normalized_plate: "ABC123", confidence: 0.9, created_at: "2026-08-05T12:00:00Z", evidence_available: true };
const stats = { total_recognitions: 2, authorized: 0, unauthorized: 1, manual_review: 0, no_plate: 1, timezone: "UTC" as const, trend_granularity: "day" as const, trend: [{ bucket_start: "2026-08-05T00:00:00Z", authorized: 0, unauthorized: 1, manual_review: 0, no_plate: 1, total: 2 }] };
const history = { items: [summary], page: 1, page_size: 10, total_items: 1, total_pages: 1, timezone: "UTC" as const };
const alerts = { items: [{ ...summary, alert_type: "ENTRY_NOT_AUTHORIZED" as const, message: "This record may require operator review." }], page: 1, page_size: 10, total_items: 1, total_pages: 1, timezone: "UTC" as const };
const detail = { ...summary, timings: { ocr_ms: 2 }, evidence_access: "restricted" as const };

describe("Day 14 operational views", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders dashboard loading then server statistics and UTC", async () => {
    vi.mocked(getStatistics).mockResolvedValue(stats);
    render(<DashboardView />);
    expect(screen.getByRole("status").textContent).toContain("Loading server-derived statistics");
    expect(await screen.findByText("All totals and daily trend boundaries are calculated by the backend in UTC.")).toBeDefined();
    expect(screen.getByText("2", { selector: "p" })).toBeDefined();
  });

  it("renders dashboard empty and failure states", async () => {
    vi.mocked(getStatistics).mockResolvedValueOnce({ ...stats, total_recognitions: 0, unauthorized: 0, no_plate: 0, trend: [] });
    const { unmount } = render(<DashboardView />);
    expect(await screen.findByText("No recognition activity")).toBeDefined();
    unmount();
    vi.mocked(getStatistics).mockRejectedValue(new Error("private provider detail"));
    render(<DashboardView />);
    expect((await screen.findByRole("alert")).textContent).toContain("Dashboard statistics could not be loaded");
    expect(screen.queryByText(/provider detail/i)).toBeNull();
  });

  it("renders, filters, paginates, and shows restricted history detail", async () => {
    vi.mocked(getHistory).mockResolvedValue({ ...history, total_pages: 2 });
    vi.mocked(getDetection).mockResolvedValue(detail);
    render(<HistoryView />);
    expect(await screen.findByText("ABC123")).toBeDefined();
    expect(screen.getAllByText(/UTC/).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "UNAUTHORIZED" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(getHistory).toHaveBeenLastCalledWith(expect.objectContaining({ decision: "UNAUTHORIZED" }), expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    expect(await screen.findByText("Available, but access is restricted")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(getHistory).toHaveBeenLastCalledWith(expect.objectContaining({ page: "2" }), expect.any(AbortSignal)));
  });

  it("shows detail loading before a successful restricted detail", async () => {
    let resolveDetail!: (value: typeof detail) => void;
    vi.mocked(getHistory).mockResolvedValue(history);
    vi.mocked(getDetection).mockReturnValue(new Promise((resolve) => { resolveDetail = resolve; }));
    render(<HistoryView />);
    await screen.findByText("ABC123");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    expect(screen.getByRole("status").textContent).toContain("Loading event detail");
    resolveDetail(detail);
    expect(await screen.findByText("Available, but access is restricted")).toBeDefined();
  });

  it.each([
    [new ApiRequestError("HTTP_ERROR", "internal repository secret", 404, null), "Detection not found", "This detection record is no longer available."],
    [new ApiRequestError("HTTP_ERROR", "provider /private/path", 503, null), "Detection detail unavailable", "The detection details could not be loaded."],
    [new ApiRequestError("API_RESPONSE_INVALID", "raw response body", 200, null), "Detection detail unavailable", "The detection details could not be verified safely."],
    [new ApiRequestError("API_REQUEST_TIMEOUT", "internal timeout detail", null, null), "Detection detail timed out", "The detection detail request timed out."],
  ])("renders a sanitized detail failure without removing history", async (failure, title, message) => {
    vi.mocked(getHistory).mockResolvedValue(history);
    vi.mocked(getDetection).mockRejectedValue(failure);
    render(<HistoryView />);
    await screen.findByText("ABC123");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    expect(await screen.findByText(title)).toBeDefined();
    expect(screen.getByText(new RegExp(message))).toBeDefined();
    expect(screen.getByText("ABC123")).toBeDefined();
    expect(screen.queryByText(/secret|provider|private\/path|raw response|internal timeout/i)).toBeNull();
  });

  it("recovers by opening a detail successfully after a failure", async () => {
    vi.mocked(getHistory).mockResolvedValue(history);
    vi.mocked(getDetection)
      .mockRejectedValueOnce(new ApiRequestError("HTTP_ERROR", "private", 404, null))
      .mockResolvedValueOnce(detail);
    render(<HistoryView />);
    await screen.findByText("ABC123");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    await screen.findByText("Detection not found");
    fireEvent.click(screen.getByRole("button", { name: "View" }));
    expect(await screen.findByText("Available, but access is restricted")).toBeDefined();
    expect(screen.queryByText("Detection not found")).toBeNull();
  });

  it("prevents an older detail request from overwriting a newer selection", async () => {
    let resolveFirst!: (value: typeof detail) => void;
    let resolveSecond!: (value: typeof detail) => void;
    vi.mocked(getHistory).mockResolvedValue(history);
    vi.mocked(getDetection)
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve; }))
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve; }));
    render(<HistoryView />);
    await screen.findByText("ABC123");
    const view = screen.getByRole("button", { name: "View" });
    fireEvent.click(view);
    fireEvent.click(view);
    resolveSecond({ ...detail, normalized_plate: "NEW123", reason_message: "Newer detail selected." });
    expect(await screen.findByText(/Newer detail selected/)).toBeDefined();
    resolveFirst({ ...detail, normalized_plate: "OLD123", reason_message: "Older detail must not render." });
    await waitFor(() => expect(screen.queryByText(/Older detail must not render/)).toBeNull());
    expect(screen.getByText(/Newer detail selected/)).toBeDefined();
  });

  it("blocks an invalid plate filter and clears feedback after correction", async () => {
    vi.mocked(getHistory).mockResolvedValue(history);
    render(<HistoryView />);
    await screen.findByText("ABC123");
    const initialCalls = vi.mocked(getHistory).mock.calls.length;
    const input = screen.getByLabelText("Normalized plate");
    fireEvent.change(input, { target: { value: "ABC-123" } });
    fireEvent.submit(screen.getByRole("form", { name: "History filters" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Use only letters A–Z and numbers 0–9 for the normalized plate.");
    expect(getHistory).toHaveBeenCalledTimes(initialCalls);
    fireEvent.change(input, { target: { value: "ABC123" } });
    expect(screen.queryByText(/Use only letters/)).toBeNull();
    fireEvent.submit(screen.getByRole("form", { name: "History filters" }));
    await waitFor(() => expect(getHistory).toHaveBeenLastCalledWith(expect.objectContaining({ normalized_plate: "ABC123" }), expect.any(AbortSignal)));
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.queryByText(/Use only letters/)).toBeNull();
  });

  it("renders history empty and sanitized failure states", async () => {
    vi.mocked(getHistory).mockResolvedValueOnce({ ...history, items: [], total_items: 0, total_pages: 0 });
    const { unmount } = render(<HistoryView />);
    expect(await screen.findByText("No matching detections")).toBeDefined();
    unmount();
    vi.mocked(getHistory).mockRejectedValue(new Error("database secret"));
    render(<HistoryView />);
    expect((await screen.findByRole("alert")).textContent).toContain("Detection history could not be loaded");
    expect(screen.queryByText(/database secret/i)).toBeNull();
  });

  it("renders backend-selected alert, empty, and failure states", async () => {
    vi.mocked(getAlerts).mockResolvedValueOnce(alerts);
    const { unmount } = render(<AlertsView />);
    expect(await screen.findByText("Entry not authorized")).toBeDefined();
    expect(screen.getByText(/Selected by the backend/)).toBeDefined();
    unmount();
    vi.mocked(getAlerts).mockResolvedValueOnce({ ...alerts, items: [], total_items: 0, total_pages: 0 });
    const empty = render(<AlertsView />);
    expect(await screen.findByText("No operational alerts")).toBeDefined();
    empty.unmount();
    vi.mocked(getAlerts).mockRejectedValue(new Error("provider"));
    render(<AlertsView />);
    expect((await screen.findByRole("alert")).textContent).toContain("Alerts could not be loaded");
  });
});
