import { randomUUID } from "node:crypto";
import { test, expect } from "../../frontend/node_modules/@playwright/test";
import { loginApi, loginUi } from "../browser-auth";
import type { SessionInfo } from "../../frontend/src/types";

test("protected routes require login; invalid credentials have one generic error", async ({
  page,
  request,
}) => {
  const workspaceReads: string[] = [];
  page.on("request", (request) => {
    if (/\/api\/v1\/(reviews|analytics)/.test(request.url()))
      workspaceReads.push(request.url());
  });
  await page.goto("/#/outcomes");
  await expect(
    page.getByRole("heading", { name: "Sign in to ProofOps" }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  expect(workspaceReads).toEqual([]);
  expect((await request.get("/api/v1/reviews")).status()).toBe(401);
  expect(
    (
      await request.post("/api/v1/bundles", {
        data: { replay: "valid-resize" },
      })
    ).status(),
  ).toBe(401);
  await page
    .getByLabel("Username", { exact: true })
    .fill(`unknown-${randomUUID()}`);
  await page.getByLabel("Password", { exact: true }).fill(randomUUID());
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "Invalid username or password.",
  );
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue("");
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
});

test("admin login survives reload and logout protects the workspace again", async ({
  page,
}) => {
  await page.goto("/#/outcomes");
  await loginUi(page);
  await expect(
    page.getByRole("heading", { name: "Outcomes, with context." }),
  ).toBeVisible();
  await expect(page.locator(".local-pill")).toHaveText("ADMIN");
  const cookie = (await page.context().cookies()).find((cookie) =>
    cookie.name.endsWith("proofops_session"),
  );
  expect(Boolean(cookie)).toBe(true);
  expect(cookie!.httpOnly).toBe(true);
  expect(cookie!.sameSite).toBe("Lax");
  expect(cookie!.expires).toBeGreaterThan(Date.now() / 1000);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Load billing sample" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to ProofOps" }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/reviews")).status()).toBe(401);
  await page.goto("/#/reviews");
  await expect(page.getByRole("button", { name: "New review" })).toHaveCount(0);
});

test("viewer can inspect and export a real review but cannot perform admin writes", async ({
  page,
  request,
}) => {
  const admin = await loginApi(request);
  const headers = { "X-CSRF-Token": admin.csrf_token! };
  const imported = await request.post("/api/v1/bundles", {
    headers,
    data: { replay: "unsafe-resize" },
  });
  expect(imported.status()).toBe(201);
  const queued = await request.post("/api/v1/reviews", {
    headers: { ...headers, "Idempotency-Key": randomUUID() },
    data: {
      bundle_id: (await imported.json()).bundle_id,
      ai_preference: "off",
    },
  });
  expect(queued.status()).toBe(202);
  const id = (await queued.json()).review_id;
  await expect
    .poll(
      async () =>
        (await (await request.get(`/api/v1/reviews/${id}`)).json()).job.state,
    )
    .toBe("completed");
  await page.goto(`/#/reviews/${id}`);
  await loginUi(page, "viewer");
  await expect(page.locator(".local-pill")).toHaveText("VIEWER · READ-ONLY");
  await expect(
    page.getByRole("heading", { name: "Revise the change", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "What determines the result" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Prepare guard draft" }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Record an operator disposition", { exact: true }),
  ).toHaveCount(0);
  const viewer: SessionInfo = await (
    await page.request.get("/api/v1/auth/session")
  ).json();
  for (const [path, data] of [
    ["/api/v1/bundles", { replay: "valid-resize" }],
    [`/api/v1/reviews/${id}/guard-drafts`, { ai_preference: "off" }],
    ["/api/v1/admin/reset-demo-data", { confirm: true }],
  ] as const) {
    expect(
      (
        await page.request.post(path, {
          data,
          headers: { "X-CSRF-Token": viewer.csrf_token! },
        })
      ).status(),
    ).toBe(403);
  }
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export review bundle" }).click();
  expect((await download).suggestedFilename()).toBe(`proofops-${id}.zip`);
  await page.getByRole("button", { name: "All reviews" }).click();
  await expect(
    page.getByRole("region", { name: "Recent reviews", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "New review" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Run review", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Outcomes", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Load billing sample" }),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 320, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("a 401 removes cached workspace data and asks for sign-in", async ({
  page,
}) => {
  await page.goto("/#/reviews");
  await loginUi(page);
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible();
  await page.context().clearCookies();
  await page.getByRole("button", { name: "Refresh backend data" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to ProofOps" }),
  ).toBeVisible();
  await expect(
    page.getByText("Your session expired. Sign in again."),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Recent reviews", exact: true }),
  ).toHaveCount(0);
});

test("a real 403 after a session role change refreshes viewer controls", async ({
  page,
}) => {
  await page.goto("/#/reviews");
  await loginUi(page);
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible();
  // Another tab can change the browser's session while this page still shows admin controls.
  await loginApi(page.request, "viewer");
  await page.getByRole("button", { name: "Run review", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Administrator access required.",
  );
  await expect(page.locator(".local-pill")).toHaveText("VIEWER · READ-ONLY");
  await expect(page.getByRole("button", { name: "New review" })).toHaveCount(0);
});

test("the session expiry timer closes the workspace while the page is idle", async ({
  page,
}) => {
  await page.clock.install();
  await page.goto("/#/reviews");
  await loginUi(page);
  await page.route("**/api/v1/auth/session", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: {
        ...(await response.json()),
        expires_at: new Date(Date.now() + 30_000).toISOString(),
      },
    });
  });
  await page.reload();
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible();
  await page.clock.fastForward(31_000);
  await expect(
    page.getByRole("heading", { name: "Sign in to ProofOps" }),
  ).toBeVisible();
  await expect(
    page.getByText("Your session expired. Sign in again."),
  ).toBeVisible();
});

test("unavailable authentication fails closed and can be retried", async ({
  page,
}) => {
  await page.route("**/api/v1/auth/session", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Authentication is unavailable." },
    }),
  );
  await page.goto("/#/reviews");
  await expect(
    page.getByRole("heading", { name: "Sign-in service unavailable" }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveCount(0);
  await page.unroute("**/api/v1/auth/session");
  await page.getByRole("button", { name: "Retry sign-in service" }).click();
  await expect(
    page.getByRole("heading", { name: "Sign in to ProofOps" }),
  ).toBeVisible();
});

test("public demo session renders read-only navigation with no login or billing controls", async ({
  page,
}) => {
  // Browser presentation contract; real demo membership and every endpoint are exercised in test_public_demo.py.
  await page.route("**/api/v1/auth/session", (route) =>
    route.fulfill({
      json: {
        role: "viewer",
        username: null,
        csrf_token: null,
        expires_at: null,
        public_demo: true,
      },
    }),
  );
  await page.route("**/readyz", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
  await page.route("**/api/v1/reviews?*", (route) =>
    route.fulfill({ json: { total: 0, items: [] } }),
  );
  await page.route("**/api/v1/analytics", (route) =>
    route.fulfill({
      json: {
        review_counts: {},
        review_count: 0,
        projected_comparisons: [],
        observed_outcomes: [],
        model: {
          attempts: 0,
          actual_usd: "0",
          pending_reserved_usd: "0",
          p50_seconds: null,
          p95_seconds: null,
          basis: "Seeded template results only.",
        },
        billing: {
          totals: [],
          groups: [],
          note: "Workspace billing is not part of the public demo.",
        },
        bounds: "Seeded results only.",
      },
    }),
  );
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") writes.push(request.url());
  });
  await page.goto("/#/reviews");
  await expect(page.locator(".local-pill")).toHaveText("DEMO · READ-ONLY");
  await expect(
    page.getByRole("heading", { name: "No saved reviews" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "New review" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Outcomes", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Outcomes, with context." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Billing sample reconciliation" }),
  ).toHaveCount(0);
  expect(writes).toEqual([]);
});
