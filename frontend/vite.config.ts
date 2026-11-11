/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { configDefaults } from "vitest/config";
import { defineConfig } from "vite";
import { pagesAssets, pycore } from "./vite.pages";

// `VITE_MODE=static` builds the GitHub Pages app: everything runs in the browser (see src/api/static).
const STATIC = process.env.VITE_MODE === "static";
/** Where GitHub Pages serves the static build (the repository's project page). */
export const PAGES_BASE = "/pharma-ocr-date-rag/";

export default defineConfig({
  base: STATIC ? PAGES_BASE : "/",
  plugins: [react(), pycore(), ...(STATIC ? [pagesAssets()] : [])],
  worker: { format: "es", plugins: () => [pycore()] },
  server: {
    // The FastAPI backend (`uvicorn --factory pharma_dates.api:create_app`) listens on :8000.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    // Playwright owns e2e/ and e2e-static/.
    exclude: [...configDefaults.exclude, "e2e/**", "e2e-static/**"],
  },
});
