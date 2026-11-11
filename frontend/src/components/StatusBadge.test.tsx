import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunStatus } from "../api";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each<[RunStatus, string]>([
    ["queued", "Queued"],
    ["reading", "Reading"],
    ["classifying", "Classifying"],
    ["validating", "Validating"],
  ])("shows %s as an in-progress info pill", (status, label) => {
    render(<StatusBadge status={status} />);

    expect(screen.getByText(label)).toHaveClass("pill", "pill--info");
  });

  it("shows done as a plain pill", () => {
    render(<StatusBadge status="done" />);

    const pill = screen.getByText("Done");
    expect(pill).toHaveClass("pill");
    expect(pill).not.toHaveClass("pill--info");
    expect(pill).not.toHaveClass("pill--danger");
  });

  it("shows failed in danger", () => {
    render(<StatusBadge status="failed" />);

    expect(screen.getByText("Failed")).toHaveClass("pill", "pill--danger");
  });
});
