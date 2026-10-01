import { defineConfig, devices } from "@playwright/test";

// Frontend E2E against the Vite dev server; the API and realtime socket are mocked per test.
export default defineConfig({
  testDir: "tests/e2e",
  // One worker: parallel browsers starve the shared Vite dev server and time out on first load.
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: { command: "npm run dev", url: "http://localhost:5173", reuseExistingServer: true, timeout: 60_000 },
});
