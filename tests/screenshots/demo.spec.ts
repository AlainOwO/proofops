import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test } from "../../frontend/node_modules/@playwright/test";
import type { Detail, Summary } from "../../frontend/src/types";

for (const [scenario, outcome, heading] of [
  ["valid-resize", "request_review", "Ready for engineering review"],
  ["unsafe-resize", "revise_change", "Revise the change"],
  ["incomplete-evidence", "collect_evidence", "Collect more evidence"],
]) {
  test(`${scenario}: capture the seeded result for README`, async ({
    page,
    request,
  }, testInfo) => {
    const appRoot = resolve(testInfo.config.rootDir, "../..");
    const response = await request.get("/api/v1/reviews");
    expect(response.ok()).toBe(true);
    const listing: { total: number; items: Summary[] } = await response.json();
    expect(
      listing.total,
      "Run proofops reset-demo-data before capturing the demo.",
    ).toBe(3);
    expect(listing.items).toHaveLength(3);
    const matches = listing.items.filter((item) => item.outcome === outcome);
    expect(matches).toHaveLength(1);
    const saved = await request.get(`/api/v1/reviews/${matches[0].id}`);
    expect(saved.ok()).toBe(true);
    const detail: Detail = await saved.json();
    const manifest = JSON.parse(
      await readFile(
        resolve(appRoot, "fixtures/replays", scenario, "manifest.json"),
        "utf8",
      ),
    );
    // Capture only unchanged supplied fixtures with template explanations.
    // No imports, review submissions, dispositions or model calls are made.
    expect(detail.report?.input_hashes).toEqual(manifest.files);
    expect(detail.report?.origin).toBe("synthetic_fixture");
    expect(detail.report?.mode).toBe("replay");
    expect(detail.job.state).toBe("completed");
    expect(detail.explanation?.status).toBe("template");
    expect(detail.guard_drafts).toEqual([]);

    await page.goto(`/#/reviews/${matches[0].id}`);
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Local backend ready", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Evidence coverage" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Workload comparison" }),
    ).toBeVisible();
    await page.screenshot({
      path: resolve(appRoot, "docs/screenshots", `${scenario}.png`),
      fullPage: true,
      animations: "disabled",
    });
  });
}
