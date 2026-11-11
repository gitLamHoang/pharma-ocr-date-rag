import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * The smoke test. By default it starts the API offline (`AI_ENABLED=false`) on :8001 with a fresh
 * data directory, serving the built frontend (`npm run build` first). Set `E2E_BASE_URL` to test a
 * server that is already running instead, such as `make dev` at http://localhost:5173.
 */
const external = process.env.E2E_BASE_URL;
// Set once in the main process; workers inherit it, so they all point at the same server.
process.env.E2E_DATA_DIR ??= resolve(import.meta.dirname, "../data/e2e", String(Date.now()));

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: external ?? "http://127.0.0.1:8001",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: external
    ? undefined
    : {
        command: "uv run uvicorn --factory pharma_dates.api:create_app --host 127.0.0.1 --port 8001",
        cwd: "../backend",
        url: "http://127.0.0.1:8001/api/health",
        env: { AI_ENABLED: "false", DATA_DIR: process.env.E2E_DATA_DIR },
        timeout: 120_000,
        reuseExistingServer: false,
      },
});
