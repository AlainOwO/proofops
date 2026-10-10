import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

const privateDirectory = fileURLToPath(
  new URL("../artifacts/hosted-full/private", import.meta.url),
);
process.env.PROOFOPS_BROWSER_AUTH_FILE = resolve(
  privateDirectory,
  "browser-auth.json",
);

export default defineConfig({
  ...base,
  testDir: "../tests",
  testMatch: ["**/e2e/*.spec.ts", "**/hosted_browser/*.spec.ts"],
  outputDir: "../artifacts/hosted-full/browser",
  reporter: "list",
  use: {
    ...base.use,
    baseURL: "https://full.localhost:15443",
    // The disposable internal issuer is not installed in the host trust store.
    ignoreHTTPSErrors: true,
    launchOptions: {
      args: [
        "--host-resolver-rules=MAP full.localhost 127.0.0.1, MAP demo.localhost 127.0.0.1",
        "--no-proxy-server",
      ],
    },
    trace: "off",
    video: "off",
  },
});
