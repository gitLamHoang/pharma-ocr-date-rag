import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import * as versions from "./versions";

const pkg = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../package.json"), "utf-8"));
const lock = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../package-lock.json"), "utf-8"));

describe("pinned engine assets", () => {
  it("load the same versions the package lock installs", () => {
    expect(pkg.devDependencies.pyodide).toBe(versions.PYODIDE_VERSION);
    expect(lock.packages["node_modules/tesseract.js-core"].version).toBe(versions.TESSERACT_CORE_VERSION);
  });

  it("name an exact version in every CDN URL", () => {
    for (const url of [versions.PYODIDE_INDEX_URL, versions.TESSERACT_CORE_PATH, versions.TESSERACT_LANG_PATH]) {
      expect(url).toMatch(/^https:\/\/cdn\.jsdelivr\.net\/.*[@v]\d+\.\d+\.\d+/);
    }
  });
});
