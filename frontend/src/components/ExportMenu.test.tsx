import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { api } from "../api";
import { ExportMenu } from "./ExportMenu";

function open() {
  fireEvent.click(screen.getByRole("button", { name: "Export" }));
}

describe("ExportMenu", () => {
  it("is closed until the button is pressed", () => {
    render(<ExportMenu runId={4} />);

    expect(screen.getByRole("button", { name: "Export" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: /Export CSV/ })).not.toBeInTheDocument();
  });

  it("links to the run's CSV and JSON exports", () => {
    render(<ExportMenu runId={4} />);
    open();

    expect(screen.getByRole("button", { name: "Export" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: /Export CSV/ })).toHaveAttribute("href", api.exportUrl(4, "csv"));
    expect(screen.getByRole("link", { name: /Export JSON/ })).toHaveAttribute("href", api.exportUrl(4, "json"));
    expect(api.exportUrl(4, "csv")).not.toBe(api.exportUrl(4, "json"));
  });

  it("exports the run it is given, not the latest one", () => {
    render(<ExportMenu runId={3} />);
    open();

    expect(screen.getByRole("link", { name: /Export CSV/ })).toHaveAttribute("href", api.exportUrl(3, "csv"));
  });

  it("closes on Escape and returns focus to the button", () => {
    render(<ExportMenu runId={4} />);
    open();

    fireEvent.keyDown(screen.getByRole("link", { name: /Export CSV/ }), { key: "Escape" });

    expect(screen.queryByRole("link", { name: /Export CSV/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export" })).toHaveFocus();
  });

  it("closes when a format is chosen or the reviewer clicks elsewhere", () => {
    render(
      <>
        <p>Outside</p>
        <ExportMenu runId={4} />
      </>,
    );
    open();
    fireEvent.click(screen.getByRole("link", { name: /Export JSON/ }));
    expect(screen.queryByRole("link", { name: /Export JSON/ })).not.toBeInTheDocument();

    open();
    fireEvent.pointerDown(screen.getByText("Outside"));
    expect(screen.queryByRole("link", { name: /Export JSON/ })).not.toBeInTheDocument();
  });
});
