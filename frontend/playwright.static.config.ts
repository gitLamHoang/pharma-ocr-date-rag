import { defineConfig, devices } from "@playwright/test";
import { PAGES_PORT, PREVIEW_PORT as PORT } from "./e2e-static/ports";

/**
 * The static (GitHub Pages) build's smoke test: `VITE_MODE=static npm run build` first; this
 * serves dist/ with `vite preview` under the Pages base path and drives the in-browser engine.
 * Pyodide and the Tesseract core/language data load from jsDelivr (pinned), so this needs network.
 */

export default defineConfig({
  testDir: "./e2e-static",
  timeout: 240_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never", outputFolder: "playwright-report-static" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}/pharma-ocr-date-rag/`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // VITE_MODE=static makes vite.config.ts serve dist/ under /pharma-ocr-date-rag/.
      command: `npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
      env: { VITE_MODE: "static" },
      url: `http://127.0.0.1:${PORT}/pharma-ocr-date-rag/`,
      timeout: 60_000,
      reuseExistingServer: false,
    },
    {
      // dist/ as GitHub Pages serves it (no SPA fallback; 404.html for unknown paths).
      command: `node e2e-static/pagesServer.mjs ${PAGES_PORT}`,
      url: `http://127.0.0.1:${PAGES_PORT}/pharma-ocr-date-rag/`,
      timeout: 30_000,
      reuseExistingServer: false,
    },
  ],
});
