import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorState, LoadingState } from "@/components/feedback";

describe("feedback primitives", () => {
  it("announces loading state without leaking internal detail", () => {
    render(<LoadingState label="Loading secure workspace" />);

    expect(screen.getByRole("status").textContent).toContain(
      "Loading secure workspace",
    );
  });

  it("offers an accessible retry action with a sanitized message", () => {
    const retry = vi.fn();
    render(<ErrorState retry={retry} />);

    expect(screen.getByRole("alert").textContent).not.toContain(
      "C:\\private\\provider.log",
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
