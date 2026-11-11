/**
 * Guards the design tokens: every role exists, light and dark both define it, and the pairs that
 * carry words or marks meet WCAG contrast (4.5:1 for text, 3:1 for marks on the page images).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(import.meta.dirname, "tokens.css"), "utf8");

/** Every `--name: value;` declaration in the file (later declarations win). */
function declarations(): Map<string, string> {
  const out = new Map<string, string>();
  for (const [, name, value] of css.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)) out.set(name, value.trim());
  return out;
}

const tokens = declarations();

/** Resolve a token to a hex colour for one theme, following `var()` and `light-dark()`. */
function colour(name: string, theme: "light" | "dark"): string {
  const declared = tokens.get(name);
  if (declared === undefined) throw new Error(`${name} is not defined`);
  let value: string = declared;
  for (let depth = 0; depth < 10; depth++) {
    const pair: RegExpMatchArray | null = value.match(/^light-dark\(\s*([^,]+?)\s*,\s*(.+?)\s*\)$/);
    if (pair) value = theme === "light" ? pair[1]! : pair[2]!;
    const ref = value.match(/^var\((--[a-z0-9-]+)\)$/);
    if (ref) {
      const next = tokens.get(ref[1]);
      if (next === undefined) throw new Error(`${ref[1]} (used by ${name}) is not defined`);
      value = next;
      continue;
    }
    if (/^#[0-9a-f]{6}$/i.test(value)) return value.toUpperCase();
    if (!pair) break;
  }
  throw new Error(`${name} does not resolve to a #rrggbb colour (${value})`);
}

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const FAMILIES = ["product", "document", "signature", "legal", "audit", "logistics", "other"];
const THEMES = ["light", "dark"] as const;

describe("palette", () => {
  it("anchors the three brand colours in their scales", () => {
    expect(tokens.get("--navy-900")?.toUpperCase()).toBe("#1B2447");
    expect(tokens.get("--powder-200")?.toUpperCase()).toBe("#C5D0EE");
    expect(tokens.get("--sun-400")?.toUpperCase()).toBe("#FFC93C");
  });

  it.each(["navy", "powder", "sun"])("has a full %s scale", (scale) => {
    for (const step of [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]) {
      expect(tokens.has(`--${scale}-${step}`), `--${scale}-${step}`).toBe(true);
    }
  });
});

describe.each(THEMES)("%s theme", (theme) => {
  const c = (name: string) => colour(name, theme);

  it("defines every semantic role", () => {
    for (const role of ["--bg", "--surface", "--text", "--muted", "--accent", "--focus", "--danger", "--warning", "--info"]) {
      expect(() => c(role), role).not.toThrow();
    }
  });

  it.each(["--bg", "--surface", "--surface-2"])("text and muted text read on %s", (ground) => {
    expect(contrast(c("--text"), c(ground))).toBeGreaterThanOrEqual(7);
    expect(contrast(c("--muted"), c(ground))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(["--danger", "--warning", "--info", "--positive"])("%s text reads on the sheet and on its own tint", (role) => {
    expect(contrast(c(role), c("--surface"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c(role), c(`${role}-bg`))).toBeGreaterThanOrEqual(4.5);
  });

  it("puts readable ink on the sunflower accent", () => {
    expect(contrast(c("--accent-ink"), c("--accent"))).toBeGreaterThanOrEqual(7);
    expect(contrast(c("--accent-ink"), c("--accent-hover"))).toBeGreaterThanOrEqual(7);
  });

  it("draws a focus ring that stands out from the sheet", () => {
    // The ring is a sunflower halo around a 2px edge; the edge carries the 3:1 non-text contrast.
    expect(contrast(c("--focus-edge"), c("--surface"))).toBeGreaterThanOrEqual(3);
    expect(contrast(c("--focus-edge"), c("--bg"))).toBeGreaterThanOrEqual(3);
  });

  it("gives form controls a visible edge", () => {
    expect(contrast(c("--control"), c("--surface"))).toBeGreaterThanOrEqual(3);
  });

  it.each(FAMILIES)("family %s has a readable UI colour", (family) => {
    expect(contrast(c(`--fam-${family}-ui`), c("--surface"))).toBeGreaterThanOrEqual(4.5);
  });
});

describe("family highlight colours on page images", () => {
  // Page images are rendered paper: near-white ground, black ink. Boxes are drawn on them in both themes.
  const PAPER = ["#FFFFFF", "#F2F0EA"];

  it.each(FAMILIES)("%s stands out from paper", (family) => {
    const hex = colour(`--fam-${family}`, "light");
    expect(colour(`--fam-${family}`, "dark")).toBe(hex);
    for (const paper of PAPER) expect(contrast(hex, paper)).toBeGreaterThanOrEqual(4.5);
  });

  it("uses seven distinct colours, none of them the sunflower selection colour", () => {
    const hexes = FAMILIES.map((f) => colour(`--fam-${f}`, "light"));
    expect(new Set(hexes).size).toBe(7);
    expect(hexes).not.toContain(colour("--sun-400", "light"));
  });
});

describe("type", () => {
  it("names a condensed display face, a grotesk UI face and a mono for dates", () => {
    expect(tokens.get("--font-display")).toMatch(/Archivo/);
    expect(tokens.get("--font-display-stretch")).toMatch(/%$/);
    expect(tokens.get("--font-ui")).toMatch(/Archivo/);
    expect(tokens.get("--font-mono")).toMatch(/Fragment Mono/);
  });
});
