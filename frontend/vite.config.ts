/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { configDefaults } from "vitest/config";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // The FastAPI backend (`uvicorn --factory pharma_dates.api:create_app`) listens on :8000.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    // Playwright owns e2e/.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
