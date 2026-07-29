import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AlertsPage from "@/app/alerts/page";
import AuthorizedVehiclesPage from "@/app/authorized-vehicles/page";
import DashboardPage from "@/app/dashboard/page";
import HistoryPage from "@/app/history/page";
import RecognitionPage from "@/app/recognition/page";
import Home from "@/app/page";

const redirect = vi.hoisted(() =>
  vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
);

vi.mock("next/navigation", () => ({ redirect }));

describe("Day 12 route foundations", () => {
  it.each([
    ["Dashboard", DashboardPage],
    ["Recognition", RecognitionPage],
    ["Detection history", HistoryPage],
    ["Alerts", AlertsPage],
    ["Authorized vehicles", AuthorizedVehiclesPage],
  ])("renders the %s route with one descriptive heading", (title, Page) => {
    render(<Page />);

    expect(screen.getByRole("heading", { level: 1, name: title })).toBeDefined();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("redirects the root route to the dashboard", () => {
    expect(() => Home()).toThrow("NEXT_REDIRECT");
    expect(redirect).toHaveBeenCalledWith("/dashboard");
  });
});
