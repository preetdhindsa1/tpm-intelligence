import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState, ErrorState, LoadingState } from "./States";

describe("screen states", () => {
  it("shows the failure it was given and nothing else", () => {
    render(<ErrorState title="Portfolio could not be loaded" detail="GET /portfolio failed" />);
    expect(screen.getByRole("alert").textContent).toContain("GET /portfolio failed");
  });

  it("names an empty screen and a loading screen", () => {
    render(<EmptyState title="No programs yet" body="No team has a release." />);
    render(<LoadingState label="Loading the simulator…" />);
    expect(screen.getByText("No programs yet")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("Loading the simulator…");
  });
});
