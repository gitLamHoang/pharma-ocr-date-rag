import { describe, expect, it } from "vitest";
import { isDateValue, monthLabel, snippet } from "./dateDisplay";

describe("monthLabel", () => {
  it("reads a month value as its short name and year", () => {
    expect(monthLabel("2027-03")).toBe("Mar 2027");
    expect(monthLabel("2027-12")).toBe("Dec 2027");
  });

  it("leaves day values and nonsense alone", () => {
    expect(monthLabel("2027-03-31")).toBeNull();
    expect(monthLabel("2027-13")).toBeNull();
  });
});

describe("isDateValue", () => {
  it.each(["2026-03-14", "2027-03", "2024-02-29"])("accepts %s", (v) => expect(isDateValue(v)).toBe(true));
  it.each(["2026-3-14", "2027-00", "2025-02-29", "2026-04-31", "14/03/2026", ""])("refuses %s", (v) =>
    expect(isDateValue(v)).toBe(false),
  );
});

describe("snippet", () => {
  const context = "Certificate of Analysis Product: Amoxicillin 500 mg capsules Batch number: 4471-B Date of manufacture: 14/03/2026 Expiry date: EXP 03/2027 Retest date: 2026-09-30";

  it("centres the date and cuts at word boundaries with ellipses", () => {
    expect(snippet(context, "EXP 03/2027", 20)).toEqual({
      before: "…Expiry date: ",
      match: "EXP 03/2027",
      after: " Retest date:…",
    });
  });

  it("keeps a short context whole", () => {
    expect(snippet("Expiry date: 03/2027", "03/2027")).toEqual({ before: "Expiry date: ", match: "03/2027", after: "" });
  });

  it("shows the context as it is when the date is not in it", () => {
    expect(snippet("Lot 4471", "03/2027")).toEqual({ before: "Lot 4471", match: "", after: "" });
  });
});
