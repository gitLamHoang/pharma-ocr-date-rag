import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { DateRecord } from "../api";
import { makeLabels } from "../dateDisplay";
import { TAXONOMY, ambiguousDate, dateRecord, monthDate } from "../test-fixtures";
import { DateList } from "./DateList";

const labels = makeLabels(TAXONOMY);

function renderList(dates: DateRecord[], props: Partial<Parameters<typeof DateList>[0]> = {}) {
  const onSelect = vi.fn();
  const onAction = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DateList
        dates={dates}
        labels={labels}
        selectedIds={[]}
        activeId={null}
        readOnly={false}
        onSelect={onSelect}
        onAction={onAction}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onSelect, onAction };
}

function row(id: number): HTMLElement {
  return document.querySelector<HTMLElement>(`[data-date-id="${id}"]`)!;
}

describe("DateList", () => {
  it("groups dates by family in taxonomy order, each heading with its count", () => {
    renderList([
      ambiguousDate({ id: 1 }),
      dateRecord({ id: 2 }),
      monthDate({ id: 3 }),
    ]);

    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Product / batch2", "Document control1"]);
  });

  it("shows an ambiguous date's two readings and no single value", () => {
    renderList([ambiguousDate({ id: 1 })]);

    const value = within(row(1)).getByTestId("date-value");
    expect(value).toHaveTextContent("2026-09-10 or 2026-10-09");
    expect(within(row(1)).queryByText("2026-09-10", { exact: true })).toBeInTheDocument();
    expect(within(row(1)).queryByText("2026-10-09", { exact: true })).toBeInTheDocument();
    expect(value.querySelectorAll(".mono")).toHaveLength(2);
  });

  it("shows a month-only date as its month, never a day", () => {
    renderList([monthDate({ id: 1 })]);

    const value = within(row(1)).getByTestId("date-value");
    expect(value).toHaveTextContent("2027-03");
    expect(value).toHaveTextContent("Mar 2027");
    expect(value.textContent).not.toMatch(/2027-03-\d\d/);
  });

  it("marks AI-only dates for verification and rule dates plainly", () => {
    renderList([dateRecord({ id: 1, source: "ai_only" }), dateRecord({ id: 2, source: "rules" })]);

    expect(within(row(1)).getByText("AI-only · verify")).toHaveClass("pill--info");
    expect(within(row(2)).queryByText("AI-only · verify")).not.toBeInTheDocument();
    expect(within(row(2)).getByText("Rules")).toBeInTheDocument();
  });

  it("shows the type label, the page's own words, the page and the confidence", () => {
    renderList([dateRecord({ id: 1, page: 2, confidence: 0.92 })]);

    expect(within(row(1)).getByText("Manufacture date")).toBeInTheDocument();
    expect(row(1).querySelector(".date-row__meta .mono")).toHaveTextContent(/^14\/03\/2026$/);
    expect(within(row(1)).getByText("Page 2")).toBeInTheDocument();
    expect(within(row(1)).getByText("0.92")).toBeInTheDocument();
    expect(within(row(1)).getByText("Needs review")).toBeInTheDocument();
  });

  it("shows the page's words around the date, the date itself in ink", () => {
    renderList([dateRecord({ id: 1, raw_text: "03/2027", context: "Product: Amoxicillin 500 mg capsules Batch number: 4471-B Expiry date: 03/2027 Retest date: 2026-09-30 Sampling date: 02/04/2026 Analysis report date: 09/10/2026" })]);

    const context = row(1).querySelector(".date-row__context")!;
    expect(context.textContent).toBe("…Batch number: 4471-B Expiry date: 03/2027 Retest date: 2026-09-30 Sampling date:…");
    expect(within(row(1)).getAllByText("03/2027").some((el) => el.classList.contains("date-row__match"))).toBe(true);
  });

  it("names the other reading of a date resolved from evidence", () => {
    renderList([ambiguousDate({ id: 1, current_value: "2026-10-09", evidence: "dates in this document are day first" })]);

    expect(within(row(1)).getByTestId("date-value")).toHaveTextContent(/^2026-10-09$/);
    expect(within(row(1)).getByText(/Also readable as/)).toHaveTextContent(
      "Also readable as 2026-09-10 · evidence “dates in this document are day first”",
    );
  });

  it("names a decision and a carried-over one", () => {
    renderList([dateRecord({ id: 1, status: "accepted", carried_from_run: 3 }), dateRecord({ id: 2, status: "rejected" })]);

    expect(within(row(1)).getByText("Accepted")).toHaveClass("pill--positive");
    expect(within(row(1)).getByText("Carried over from run 3")).toBeInTheDocument();
    expect(within(row(2)).getByText("Rejected")).toHaveClass("pill--danger");
  });

  it("selects a date when its row is clicked", () => {
    const { onSelect } = renderList([dateRecord({ id: 7 })]);

    fireEvent.click(within(row(7)).getByRole("button", { name: /Manufacture date/ }));

    expect(onSelect).toHaveBeenCalledWith(7);
  });

  it("offers accept, edit and reject on the active row only", () => {
    const { onAction } = renderList([dateRecord({ id: 1 }), dateRecord({ id: 2 })], { selectedIds: [2], activeId: 2 });

    expect(within(row(1)).queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument();
    fireEvent.click(within(row(2)).getByRole("button", { name: /^Accept/ }));
    fireEvent.click(within(row(2)).getByRole("button", { name: /^Edit/ }));
    fireEvent.click(within(row(2)).getByRole("button", { name: /^Reject/ }));

    expect(onAction.mock.calls.map(([d, a]) => [d.id, a])).toEqual([
      [2, "accept"],
      [2, "correct"],
      [2, "reject"],
    ]);
  });

  it("marks every selected row pressed and the active one current", () => {
    renderList([dateRecord({ id: 1 }), dateRecord({ id: 2 }), dateRecord({ id: 3 })], { selectedIds: [1, 3], activeId: 1 });

    const pressed = (id: number) => within(row(id)).getByRole("button", { name: /Manufacture date/ });
    expect(pressed(1)).toHaveAttribute("aria-pressed", "true");
    expect(pressed(1)).toHaveAttribute("aria-current", "true");
    expect(pressed(2)).toHaveAttribute("aria-pressed", "false");
    expect(pressed(3)).toHaveAttribute("aria-pressed", "true");
    expect(pressed(3)).not.toHaveAttribute("aria-current");
  });

  it("offers no decisions when read-only", () => {
    renderList([dateRecord({ id: 1 })], { selectedIds: [1], activeId: 1, readOnly: true });

    expect(within(row(1)).queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument();
    expect(within(row(1)).queryByRole("button", { name: /^Edit/ })).not.toBeInTheDocument();
    expect(within(row(1)).getByRole("button", { name: "History" })).toBeInTheDocument();
  });

  it("says so when the run found no dates", () => {
    renderList([]);

    expect(screen.getByText("No dates found in this document.")).toBeInTheDocument();
  });
});
