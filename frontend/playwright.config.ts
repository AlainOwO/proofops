import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "../tests/e2e",
  outputDir: "../artifacts/playwright",
  timeout: 45_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["json", { outputFile: "../artifacts/checks/playwright.json" }],
  ],
  use: {
    baseURL: process.env.PROOFOPS_WEB_URL || "http://127.0.0.1:5173",
    // Network traces include session cookies and login bodies. Keep them off.
    trace: "off",
    video: "off",
    screenshot: "only-on-failure",
    ...devices["Desktop Chrome"],
    viewport: { width: 1440, height: 1050 },
  },
  projects: [{ name: "chromium" }],
});
