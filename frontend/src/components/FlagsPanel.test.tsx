import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { flag } from "../test-fixtures";
import { FlagsPanel } from "./FlagsPanel";

describe("FlagsPanel", () => {
  it("lists errors first, then warnings, then info", () => {
    render(
      <FlagsPanel
        flags={[
          flag({ id: 1, severity: "info", message: "Info one" }),
          flag({ id: 2, severity: "warning", message: "Warning one" }),
          flag({ id: 3, severity: "error", message: "Error one" }),
          flag({ id: 4, severity: "info", message: "Info two" }),
          flag({ id: 5, severity: "error", message: "Error two" }),
        ]}
        activeFlagId={null}
        onSelectFlag={() => {}}
      />,
    );

    const items = screen.getAllByRole("listitem").map((li) => within(li).getByRole("button").textContent);
    expect(items).toEqual([
      "ErrorError one",
      "ErrorError two",
      "WarningWarning one",
      "InfoInfo one",
      "InfoInfo two",
    ]);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Flags5");
  });

  it("selects a flag's dates when it is clicked", () => {
    const onSelectFlag = vi.fn();
    const expiry = flag({ id: 9, severity: "error", message: "Expiry is before manufacture", date_ids: [3, 4] });
    render(<FlagsPanel flags={[expiry]} activeFlagId={null} onSelectFlag={onSelectFlag} />);

    fireEvent.click(screen.getByRole("button", { name: /Expiry is before manufacture/ }));

    expect(onSelectFlag).toHaveBeenCalledWith(expiry);
  });

  it("marks the active flag", () => {
    render(<FlagsPanel flags={[flag({ id: 1 }), flag({ id: 2 })]} activeFlagId={2} onSelectFlag={() => {}} />);

    const [first, second] = screen.getAllByRole("button");
    expect(first).toHaveAttribute("aria-pressed", "false");
    expect(second).toHaveAttribute("aria-pressed", "true");
  });

  it("folds a long list after the first five, errors first", () => {
    const many = Array.from({ length: 12 }, (_, i) => flag({ id: i + 1, severity: i === 11 ? "error" : "info", message: `Flag ${i + 1}` }));
    render(<FlagsPanel flags={many} activeFlagId={null} onSelectFlag={() => {}} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("Flag 12");

    fireEvent.click(screen.getByRole("button", { name: "Show all 12 flags" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(12);
  });

  it("says when a run has no flags", () => {
    render(<FlagsPanel flags={[]} activeFlagId={null} onSelectFlag={() => {}} />);

    expect(screen.getByText("No consistency flags on this run.")).toBeInTheDocument();
  });
});
