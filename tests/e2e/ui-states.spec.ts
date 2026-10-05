import { expect, test, type Page } from "../browser-auth";
import type { Analytics, Detail, Summary } from "../../frontend/src/types";

// Browser-only responses for empty and transport states. reviews.spec.ts runs
// the real imports, worker, deterministic reports and persisted actions.
const emptyAnalytics: Analytics = {
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
    basis: "No provider attempts.",
  },
  bounds: "Local workspace.",
  billing: { totals: [], groups: [], note: "No imported rows." },
};

const job: Summary = {
  id: "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
  bundle_id: "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb",
  state: "queued",
  stage: "queued",
  mode: "replay",
  outcome: null,
  origin: null,
  service: "reporting-api",
  candidate_commit: "c".repeat(40),
  created_at: "2026-10-05T00:00:00Z",
  updated_at: "2026-10-05T00:00:00Z",
  error_code: null,
};

async function workspace(page: Page, items: Summary[] = []) {
  await page.route("**/api/v1/reviews?*", (route) =>
    route.fulfill({ json: { items, total: items.length } }),
  );
  await page.route("**/api/v1/analytics", (route) =>
    route.fulfill({ json: emptyAnalytics }),
  );
  await page.route("**/readyz", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
}

function gate() {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
}

test("loading reviews becomes an actionable empty workspace without showing false zeros", async ({
  page,
}) => {
  await workspace(page);
  const response = gate();
  await page.route("**/api/v1/reviews?*", async (route) => {
    await response.promise;
    await route.fulfill({ json: { items: [], total: 0 } });
  });
  try {
    await page.goto("/#/reviews");
    await expect(
      page.getByRole("heading", { name: "Loading reviews", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".metric").first()).toContainText("Loading");
    await expect(
      page.getByRole("heading", { name: "Your first review starts here" }),
    ).toHaveCount(0);
    response.release();
    await expect(
      page.getByRole("heading", { name: "Your first review starts here" }),
    ).toBeVisible();
    await expect(page.locator(".metric").first().locator("strong")).toHaveText(
      "0",
    );
    await expect(
      page.getByRole("heading", { name: "How this works" }),
    ).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "Skip to content" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("main")).toBeFocused();
    await expect(page).toHaveURL(/#\/reviews$/);
    await page.getByRole("button", { name: "Choose a scenario" }).click();
    await expect(page.getByLabel("Review scenario")).toBeFocused();
  } finally {
    response.release();
  }
});

test("unavailable workspace data stays unknown and retry only reloads data", async ({
  page,
}) => {
  await workspace(page);
  let unavailable = true;
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") writes.push(request.url());
  });
  await page.route("**/api/v1/analytics", (route) =>
    unavailable
      ? route.fulfill({
          status: 503,
          json: { detail: "Local analytics are unavailable." },
        })
      : route.fulfill({ json: emptyAnalytics }),
  );
  await page.goto("/#/reviews");
  await expect(
    page.getByRole("heading", { name: "Reviews unavailable" }),
  ).toBeVisible();
  await expect(
    page.getByText("Backend unavailable", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("503");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "Unavailable",
  );
  await expect(page.getByText(/of null reviews/)).toHaveCount(0);
  unavailable = false;
  await page.getByRole("button", { name: "Retry loading reviews" }).click();
  await expect(
    page.getByRole("heading", { name: "Your first review starts here" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible();
  expect(writes).toEqual([]);
});

test("outcomes distinguishes loading and failure from an empty result", async ({
  page,
}) => {
  await workspace(page);
  const response = gate();
  let unavailable = true;
  await page.route("**/api/v1/analytics", async (route) => {
    await response.promise;
    await route.fulfill(
      unavailable
        ? { status: 503, json: { detail: "Local analytics are unavailable." } }
        : { json: emptyAnalytics },
    );
  });
  try {
    await page.goto("/#/outcomes");
    await expect(
      page.getByRole("heading", { name: "Loading outcomes" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "No projections yet" }),
    ).toHaveCount(0);
    response.release();
    await expect(
      page.getByRole("heading", { name: "Outcomes unavailable" }),
    ).toBeVisible();
    await expect(page.locator(".metric").nth(2).locator("strong")).toHaveText(
      "Not available",
    );
    unavailable = false;
    await page.getByRole("button", { name: "Retry loading outcomes" }).click();
    await expect(
      page.getByRole("heading", { name: "No projections yet" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "No observed outcomes recorded" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "No billing rows imported" }),
    ).toBeVisible();
  } finally {
    response.release();
  }
});

test("filter recovery and navigation preserve the review setup", async ({
  page,
}) => {
  await workspace(page, [job]);
  await page.goto("/#/reviews");
  await page.getByLabel("Review scenario").selectOption("unsafe-resize");
  await page.getByLabel("Filter displayed reviews").fill("no-such-service");
  await expect(
    page.getByRole("heading", { name: "No matching reviews" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear filter" }).click();
  await expect(
    page.getByRole("button", { name: /reporting-api/ }),
  ).toBeVisible();
  await expect(page.getByLabel("Filter displayed reviews")).toHaveValue("");
  await page.getByRole("link", { name: "Outcomes", exact: true }).click();
  await page.getByRole("link", { name: /^Reviews/ }).click();
  await expect(page.getByLabel("Review scenario")).toHaveValue("unsafe-resize");
});

test("retrying an unavailable job resumes polling without creating another review", async ({
  page,
}) => {
  await workspace(page);
  let unavailable = true;
  let state = "queued";
  const writes: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") writes.push(request.url());
  });
  await page.route(`**/api/v1/reviews/${job.id}`, (route) => {
    const detail: Detail = {
      job: {
        ...job,
        state,
        stage: state,
        error_code: state === "failed" ? "invalid_input" : null,
      },
      report: null,
      explanation: null,
    };
    return unavailable
      ? route.fulfill({
          status: 503,
          json: { detail: "Review storage is unavailable." },
        })
      : route.fulfill({ json: detail });
  });
  await page.goto(`/#/reviews/${job.id}`);
  await expect(
    page.getByRole("heading", { name: "Review unavailable" }),
  ).toBeVisible();
  await expect(page.locator(".job-panel .spin")).toHaveCount(0);
  unavailable = false;
  await page
    .getByRole("button", { name: "Retry loading review", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Review queued" }),
  ).toBeVisible();
  await expect(
    page.getByText(/A queued job needs the ProofOps worker/),
  ).toBeVisible();
  state = "running";
  await expect(
    page.getByRole("heading", { name: "Building the evidence report" }),
  ).toBeVisible();
  state = "failed";
  await expect(
    page.getByRole("heading", { name: "Review could not complete" }),
  ).toBeVisible();
  await expect(page.locator(".job-panel")).toContainText("invalid_input");
  await expect(page.locator(".job-panel .spin")).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("a late response cannot replace the newly selected review", async ({
  page,
}) => {
  const nextJob = {
    ...job,
    id: "dddddddd-dddd-4ddd-addd-dddddddddddd",
    stage: "new_review",
  };
  await workspace(page, [nextJob]);
  const oldResponse = gate();
  await page.route(`**/api/v1/reviews/${job.id}`, async (route) => {
    await oldResponse.promise;
    await route.fulfill({
      json: {
        job: { ...job, state: "failed", error_code: "old_review_failure" },
        report: null,
        explanation: null,
      },
    });
  });
  await page.route(`**/api/v1/reviews/${nextJob.id}`, (route) =>
    route.fulfill({ json: { job: nextJob, report: null, explanation: null } }),
  );
  try {
    await page.goto(`/#/reviews/${job.id}`);
    await expect(
      page.getByRole("heading", { name: "Loading review", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "All reviews", exact: true })
      .click();
    await page.getByRole("button", { name: /reporting-api/ }).click();
    await expect(
      page.getByRole("heading", { name: "Review queued" }),
    ).toBeVisible();
    const delivered = page.waitForResponse((response) =>
      response.url().endsWith(job.id),
    );
    oldResponse.release();
    await delivered;
    await expect(page.locator(".job-panel")).toContainText("new review");
    await expect(
      page.getByRole("heading", { name: "Review could not complete" }),
    ).toHaveCount(0);
    await expect(page.getByRole("alert")).toHaveCount(0);
  } finally {
    oldResponse.release();
  }
});
