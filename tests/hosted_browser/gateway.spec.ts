import { test, expect } from "../../frontend/node_modules/@playwright/test";
import { loginUi } from "../browser-auth";

test("the full hostname exposes application sign-in and requires an application session for API access", async ({
  page,
  playwright,
}) => {
  const outside = await playwright.request.newContext({
    baseURL: "https://full.localhost:15443",
    ignoreHTTPSErrors: true,
  });
  try {
    const loginPage = await outside.get("/");
    expect(loginPage.status()).toBe(200);
    expect(loginPage.headers()["content-type"]).toContain("text/html");
    expect(loginPage.headers()["www-authenticate"]).toBeUndefined();
    const denied = await outside.get("/api/v1/reviews");
    expect(denied.status()).toBe(401);
    expect(await denied.json()).toEqual({ detail: "Authentication required." });
    expect(denied.headers()["www-authenticate"]).toBeUndefined();
  } finally {
    await outside.dispose();
  }
  const navigation = await page.goto("/");
  expect(navigation?.status()).toBe(200);
  await expect(
    page.getByRole("heading", { name: "Sign in to ProofOps" }),
  ).toBeVisible();
  await loginUi(page);
  await expect(page.locator(".local-pill")).toHaveText("ADMIN");
  await expect(
    page.getByRole("button", { name: "New review", exact: true }),
  ).toBeVisible();
});

test("the public hostname stays anonymous and read-only alongside the writable workspace", async ({
  browser,
}) => {
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
  });
  try {
    const page = await context.newPage();
    await page.goto("https://demo.localhost:15443/");
    await expect(page.locator(".local-pill")).toHaveText("DEMO · READ-ONLY");
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "New review", exact: true }),
    ).toHaveCount(0);
    const listing = await page.request.get(
      "https://demo.localhost:15443/api/v1/reviews",
    );
    expect((await listing.json()).total).toBe(3);
    const write = await page.request.post(
      "https://demo.localhost:15443/api/v1/bundles",
      {
        data: { replay: "valid-resize" },
      },
    );
    expect(write.status()).toBe(403);
  } finally {
    await context.close();
  }
});
