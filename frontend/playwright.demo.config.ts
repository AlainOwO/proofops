import { defineConfig } from "@playwright/test";
import shared from "./playwright.config";

export default defineConfig({
  ...shared,
  testDir: "../tests/screenshots",
  outputDir: "../artifacts/playwright-demo",
  reporter: [
    ["list"],
    ["json", { outputFile: "../artifacts/checks/demo-screenshots.json" }],
  ],
  use: shared.use,
});
