import { defineConfig, devices } from "@playwright/test";

// The app under test: the compose stack sets BASE_URL=http://finally:8000;
// a local run can point at any host port (never the dev container on 8000
// unless that is what you mean to test).
const baseURL = process.env.BASE_URL || "http://localhost:8000";

export default defineConfig({
  testDir: "./e2e",
  // Specs share one database and run in file-name order (01-, 02-, ...).
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  forbidOnly: !!process.env.CI,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  outputDir: "test-results",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      // Desktop-only app (min width 1280px).
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 1000 } },
    },
  ],
});
