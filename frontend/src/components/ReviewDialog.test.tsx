import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DateRecord, ReviewAction } from "../api";
import { makeLabels } from "../dateDisplay";
import { TAXONOMY, ambiguousDate, dateRecord, monthDate } from "../test-fixtures";
import { REVIEWER_KEY, ReviewDialog } from "./ReviewDialog";

const labels = makeLabels(TAXONOMY);

function renderDialog(date: DateRecord, action: Exclude<ReviewAction, "reopen">, onSubmit = vi.fn().mockResolvedValue(undefined)) {
  const onClose = vi.fn();
  render(<ReviewDialog date={date} action={action} taxonomy={TAXONOMY} labels={labels} onSubmit={onSubmit} onClose={onClose} />);
  return { onSubmit, onClose, dialog: screen.getByRole("dialog") };
}

function type(label: string | RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("ReviewDialog", () => {
  it("requires a reviewer and a reason", async () => {
    const { onSubmit } = renderDialog(dateRecord(), "accept");

    fireEvent.click(screen.getByRole("button", { name: "Accept date" }));

    expect(await screen.findByText("Enter your name.")).toBeInTheDocument();
    expect(screen.getByText("Say why, in a few words.")).toBeInTheDocument();
    expect(screen.getByLabelText("Reviewer")).toHaveAttribute("aria-invalid", "true");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("sends an accept with the reviewer and reason, and remembers the reviewer", async () => {
    const { onSubmit } = renderDialog(dateRecord(), "accept");
    type("Reviewer", "  J. Doe ");
    type("Reason", "Matches the page");

    fireEvent.click(screen.getByRole("button", { name: "Accept date" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ action: "accept", reviewer: "J. Doe", reason: "Matches the page" }),
    );
    expect(localStorage.getItem(REVIEWER_KEY)).toBe("J. Doe");
  });

  it("fills in the remembered reviewer", () => {
    localStorage.setItem(REVIEWER_KEY, "A. Reviewer");
    renderDialog(dateRecord(), "reject");

    expect(screen.getByLabelText("Reviewer")).toHaveValue("A. Reviewer");
  });

  it("still works when the browser blocks storage", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { onSubmit } = renderDialog(dateRecord(), "reject");
    type("Reviewer", "J. Doe");
    type("Reason", "Not a date");

    fireEvent.click(screen.getByRole("button", { name: "Reject date" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ action: "reject", reviewer: "J. Doe", reason: "Not a date" }));
  });

  it("groups the type picker by family", () => {
    renderDialog(dateRecord(), "correct");

    const picker = screen.getByLabelText("Date type") as HTMLSelectElement;
    const groups = Array.from(picker.querySelectorAll("optgroup")).map((g) => g.label);
    expect(groups).toEqual(["Product / batch", "Document control", "Signature", "Other"]);
    expect(within(picker.querySelector("optgroup")!).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Manufacture date",
      "Expiry date",
    ]);
    expect(picker).toHaveValue("manufacture_date");
  });

  it("offers only the listed readings of an ambiguous date", async () => {
    const { onSubmit } = renderDialog(ambiguousDate(), "correct");

    const readings = screen.getAllByRole("radio");
    expect(readings.map((r) => (r as HTMLInputElement).value)).toEqual(["2026-09-10", "2026-10-09"]);
    expect(screen.queryByLabelText(/^Value/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "2026-10-09" }));
    type("Reviewer", "J. Doe");
    type("Reason", "Signed in October per the cover letter");
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        action: "correct",
        reviewer: "J. Doe",
        reason: "Signed in October per the cover letter",
        new_type: null,
        new_value: "2026-10-09",
      }),
    );
  });

  it("offers the readings of a resolved two-way date with the current one chosen", () => {
    renderDialog(ambiguousDate({ current_value: "2026-10-09" }), "correct");

    expect(screen.getByRole("radio", { name: "2026-10-09" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "2026-09-10" })).not.toBeChecked();
    expect(screen.queryByLabelText(/^Value/)).not.toBeInTheDocument();
  });

  it("sends only what a correction changes", async () => {
    const { onSubmit } = renderDialog(dateRecord(), "correct");
    fireEvent.change(screen.getByLabelText("Date type"), { target: { value: "expiry_date" } });
    type("Reviewer", "J. Doe");
    type("Reason", "Label says expiry");

    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        action: "correct",
        reviewer: "J. Doe",
        reason: "Label says expiry",
        new_type: "expiry_date",
        new_value: null,
      }),
    );
  });

  it("refuses a correction that changes nothing, or an invalid value", async () => {
    const { onSubmit } = renderDialog(monthDate(), "correct");
    type("Reviewer", "J. Doe");
    type("Reason", "Typo");

    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(await screen.findByText("Change the type or the value, or cancel.")).toBeInTheDocument();

    type(/^Value/, "2027-13");
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(await screen.findByText("Write the date as YYYY-MM-DD, or YYYY-MM for a month-only date.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("never lets a month-only date gain a day", async () => {
    const { onSubmit } = renderDialog(monthDate(), "correct");
    type("Reviewer", "J. Doe");
    type("Reason", "Label says April");

    type(/^Value/, "2027-04-30");
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    expect(await screen.findByText("The page gives a month only. Write YYYY-MM, without a day.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    type(/^Value/, "2027-04");
    fireEvent.click(screen.getByRole("button", { name: "Save correction" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ new_value: "2027-04" })));
  });

  it("shows the server's refusal and stays open", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("a reason is required"));
    const { onClose } = renderDialog(dateRecord(), "accept", onSubmit);
    type("Reviewer", "J. Doe");
    type("Reason", "ok");

    fireEvent.click(screen.getByRole("button", { name: "Accept date" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("a reason is required");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on cancel", () => {
    const { onClose } = renderDialog(dateRecord(), "accept");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalled();
  });
});
