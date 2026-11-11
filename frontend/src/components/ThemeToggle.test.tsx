import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { THEME_KEY, ThemeToggle } from "./ThemeToggle";

const root = document.documentElement;

beforeEach(() => {
  localStorage.clear();
  delete root.dataset.theme;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ThemeToggle", () => {
  it("follows the system theme by default", () => {
    render(<ThemeToggle />);

    expect(screen.getByRole("radio", { name: "System" })).toBeChecked();
    expect(root.dataset.theme).toBeUndefined();
  });

  it("forces a theme on <html> and remembers it", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("radio", { name: "Dark" }));

    expect(root.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
  });

  it("goes back to the system theme", () => {
    localStorage.setItem(THEME_KEY, "light");
    render(<ThemeToggle />);
    expect(screen.getByRole("radio", { name: "Light" })).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: "System" }));

    expect(root.dataset.theme).toBeUndefined();
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
  });

  it("still switches when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("radio", { name: "Light" }));

    expect(root.dataset.theme).toBe("light");
  });
});
