import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { DocumentSummary } from "../api";
import { DocumentTable } from "./DocumentTable";

function summary(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id: 1,
    name: "coa-lot-4471.pdf",
    pages: 3,
    status: "done",
    error: null,
    n_dates: 12,
    n_flags: 2,
    n_needs_review: 5,
    created_at: "2026-11-11T09:05:00",
    ...overrides,
  };
}

function renderTable(documents: DocumentSummary[]) {
  return render(
    <MemoryRouter>
      <DocumentTable documents={documents} />
    </MemoryRouter>,
  );
}

function row(name: string) {
  return screen.getByRole("link", { name }).closest("tr")!;
}

describe("DocumentTable", () => {
  it("has one column per figure", () => {
    renderTable([summary()]);

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Name", "Pages", "Status", "Dates", "Flags", "Needs review", "Uploaded"]);
  });

  it("renders each document's counts and status", () => {
    renderTable([summary(), summary({ id: 2, name: "sop-112.pdf", n_dates: 4, n_flags: 0, n_needs_review: 0 })]);

    const first = within(row("coa-lot-4471.pdf"));
    expect(first.getByRole("cell", { name: "3" })).toBeInTheDocument();
    expect(first.getByRole("cell", { name: "12" })).toBeInTheDocument();
    expect(first.getByRole("cell", { name: "2" })).toBeInTheDocument();
    expect(first.getByText("5")).toHaveClass("pill--review");
    expect(first.getByText("Done")).toHaveClass("pill");
    expect(first.getByRole("cell", { name: "2026-11-11 09:05" })).toBeInTheDocument();

    const second = within(row("sop-112.pdf"));
    expect(second.getByRole("cell", { name: "4" })).toBeInTheDocument();
    // A plain 0, not the accent pill.
    expect(second.getAllByRole("cell", { name: "0" })).toHaveLength(2);
    expect(row("sop-112.pdf").querySelector(".pill--review")).toBeNull();
  });

  it("links each name to its review screen", () => {
    renderTable([summary({ id: 7 })]);

    expect(screen.getByRole("link", { name: "coa-lot-4471.pdf" })).toHaveAttribute("href", "/documents/7");
  });

  it("shows a dash for counts that are not known yet", () => {
    renderTable([summary({ status: "classifying", pages: 3, n_dates: 0, n_flags: 0, n_needs_review: 0 })]);

    const cells = within(row("coa-lot-4471.pdf"));
    expect(cells.getByText("Classifying")).toHaveClass("pill--info");
    expect(cells.getAllByRole("cell", { name: "No value yet" })).toHaveLength(3);
  });

  it("shows the server's message on a failed row", () => {
    renderTable([
      summary({
        status: "failed",
        pages: 0,
        error: "This PDF is encrypted. Remove the password and upload it again.",
        n_dates: 0,
        n_flags: 0,
        n_needs_review: 0,
      }),
    ]);

    const cells = within(row("coa-lot-4471.pdf"));
    expect(cells.getByText("Failed")).toHaveClass("pill--danger");
    expect(cells.getByText("This PDF is encrypted. Remove the password and upload it again.")).toBeInTheDocument();
  });
});
