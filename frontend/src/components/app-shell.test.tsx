import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/history",
}));

describe("AppShell", () => {
  it("provides accessible navigation for every Day 12 route", () => {
    render(
      <AppShell>
        <h1>Page content</h1>
      </AppShell>,
    );

    const navigation = screen.getByRole("navigation", {
      name: "Primary navigation",
    });
    expect(navigation).toBeDefined();
    const expectedLinks = [
      ["Dashboard", "/dashboard"],
      ["Recognition", "/recognition"],
      ["Detection history", "/history"],
      ["Alerts", "/alerts"],
      ["Authorized vehicles", "/authorized-vehicles"],
    ];
    for (const [name, href] of expectedLinks) {
      expect(
        screen.getByRole("link", { name: new RegExp(name) }).getAttribute("href"),
      ).toBe(href);
    }
    const currentLinks = screen
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(currentLinks).toHaveLength(1);
    expect(currentLinks[0]?.getAttribute("href")).toBe("/history");
    for (const link of screen.getAllByRole("link")) {
      if (link.getAttribute("href") !== "/history") {
        expect(link.hasAttribute("aria-current")).toBe(false);
      }
    }
    expect(
      screen
        .getByRole("link", { name: "Skip to main content" })
        .getAttribute("href"),
    ).toBe("#main-content");
    expect(screen.getByRole("main").getAttribute("id")).toBe(
      "main-content",
    );
  });
});
