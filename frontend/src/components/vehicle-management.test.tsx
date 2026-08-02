import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VehicleManagement } from "@/components/vehicle-management";
import { createVehicle, getVehicles, setVehicleStatus } from "@/lib/api/vehicles";

vi.mock("@/lib/api/vehicles", () => ({ createVehicle: vi.fn(), getVehicles: vi.fn(), setVehicleStatus: vi.fn() }));
const vehicle = { id: "11111111-1111-4111-8111-111111111111", normalized_plate: "ABC123", description: "Staff", status: "ACTIVE" as const, valid_from: null, valid_until: null, created_at: "2026-08-06T12:00:00Z", updated_at: "2026-08-06T12:00:00Z" };

describe("Day 15 vehicle management", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(getVehicles).mockResolvedValue({ items: [vehicle], total_items: 1 }); vi.spyOn(window, "confirm").mockReturnValue(true); });

  it("loads and filters server records", async () => {
    render(<VehicleManagement />);
    expect(await screen.findByText("ABC123")).toBeDefined();
    fireEvent.change(screen.getByLabelText("Search plate"), { target: { value: "abc-123" } });
    fireEvent.change(screen.getByLabelText("Status", { selector: "#vehicle-filter-status" }), { target: { value: "ACTIVE" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(getVehicles).toHaveBeenLastCalledWith({ search: "ABC123", status_filter: "ACTIVE" }, expect.any(AbortSignal)));
  });

  it("creates a vehicle and reloads", async () => {
    vi.mocked(createVehicle).mockResolvedValue(vehicle);
    render(<VehicleManagement />); await screen.findByText("ABC123");
    fireEvent.change(screen.getByLabelText("Plate number"), { target: { value: "ABC-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Add vehicle" }));
    await waitFor(() => expect(createVehicle).toHaveBeenCalledWith(expect.objectContaining({ plate_number: "ABC-123", status: "ACTIVE" })));
    expect(await screen.findByText("Authorized vehicle created.")).toBeDefined();
  });

  it("requires confirmation before an important status change", async () => {
    vi.mocked(setVehicleStatus).mockResolvedValue({ ...vehicle, status: "BLOCKED" });
    render(<VehicleManagement />); await screen.findByText("ABC123");
    fireEvent.change(screen.getByLabelText("Change status for ABC123"), { target: { value: "BLOCKED" } });
    await waitFor(() => expect(window.confirm).toHaveBeenCalledWith("Change ABC123 to BLOCKED?"));
    await waitFor(() => expect(setVehicleStatus).toHaveBeenCalledWith(vehicle.id, "BLOCKED"));
  });

  it("does not change status when confirmation is declined", async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    render(<VehicleManagement />); await screen.findByText("ABC123");
    fireEvent.change(screen.getByLabelText("Change status for ABC123"), { target: { value: "INACTIVE" } });
    expect(setVehicleStatus).not.toHaveBeenCalled();
  });
});
