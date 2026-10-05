import { expect, test, type Page } from "../browser-auth";

async function runReplay(page: Page, scenario: string, result: string) {
  await page.goto("/#/reviews");
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible();
  await page.getByLabel("Review scenario").selectOption(scenario);
  await page.getByRole("button", { name: "Run review", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: result, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Synthetic rate card · illustrative projection"),
  ).toBeVisible();
}

async function expectNoPageOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
}

async function expectProjection(
  page: Page,
  expected: {
    difference: string;
    reduction: string;
    candidate: string;
    ineligibleReason: string | null;
  },
  readyFontSize: string,
) {
  const card = page.getByRole("region", {
    name: "Projected compute difference",
    exact: true,
  });
  const amount = card.locator(".cost-highlight > strong");
  const percentage = card.locator(".cost-highlight > span");
  const baseline = card.locator(".cost-comparison strong").nth(0);
  const candidate = card.locator(".cost-comparison strong").nth(1);

  await expect(amount).toHaveText(expected.difference);
  await expect(percentage).toHaveText(expected.reduction);
  await expect(baseline).toHaveText("$280.32");
  await expect(candidate).toHaveText(expected.candidate);
  for (const value of [amount, percentage, baseline, candidate]) {
    await expect(value).toBeVisible();
  }

  if (expected.ineligibleReason) {
    await expect(
      card.getByText(expected.ineligibleReason, { exact: true }),
    ).toBeVisible();
    for (const value of [amount, percentage, baseline, candidate]) {
      await expect(value).toHaveCSS("color", "rgb(102, 102, 102)");
    }
    await expect(amount).toHaveCSS("font-size", "24px");
    await expect(amount).toHaveCSS("font-weight", "500");
    await expect(percentage).toHaveCSS(
      "background-color",
      "rgb(242, 242, 242)",
    );
  } else {
    await expect(card.getByText(/^Not eligible:/)).toHaveCount(0);
    await expect(amount).toHaveCSS("color", "rgb(72, 107, 56)");
    await expect(amount).toHaveCSS("font-size", readyFontSize);
    await expect(amount).toHaveCSS("font-weight", "550");
    await expect(percentage).toHaveCSS("color", "rgb(123, 148, 95)");
    await expect(percentage).toHaveCSS(
      "background-color",
      "rgb(242, 246, 235)",
    );
    for (const value of [baseline, candidate]) {
      await expect(value).toHaveCSS("color", "rgb(100, 123, 80)");
    }
  }
}

for (const scenario of [
  {
    id: "valid-resize",
    result: "Ready for engineering review",
    difference: "$140.16",
    reduction: "50.0% estimated reduction",
    candidate: "$140.16",
    ineligibleReason: null,
  },
  {
    id: "unsafe-resize",
    result: "Revise the change",
    difference: "$210.24",
    reduction: "75.0% estimated reduction",
    candidate: "$70.08",
    ineligibleReason: "Not eligible: resolve findings first",
  },
  {
    id: "incomplete-evidence",
    result: "Collect more evidence",
    difference: "$140.16",
    reduction: "50.0% estimated reduction",
    candidate: "$140.16",
    ineligibleReason: "Not eligible: evidence incomplete",
  },
]) {
  test(`${scenario.id}: real review, projection eligibility and reproducible download`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await runReplay(page, scenario.id, scenario.result);
    await expectProjection(page, scenario, "36px");
    await expect(
      page.getByRole("heading", { name: "Evidence coverage" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Workload comparison" }),
    ).toBeVisible();
    await page
      .getByText("Inspect cited facts and assumptions", { exact: true })
      .click();
    await expect(
      page.getByText("Task-hours: baseline", { exact: false }),
    ).toBeVisible();
    await page.screenshot({
      path: `../artifacts/screenshots/${scenario.id}.png`,
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expectProjection(page, scenario, "32px");
    await expectNoPageOverflow(page);
    const workload = page.getByRole("region", {
      name: "Workload comparison table",
      exact: true,
    });
    await workload.focus();
    await expect(workload).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect
      .poll(() => workload.evaluate((element) => element.scrollLeft))
      .toBeGreaterThan(0);
    await page.screenshot({
      path: `../artifacts/screenshots/${scenario.id}-mobile.png`,
      fullPage: true,
    });
    const download = page.waitForEvent("download");
    await page.getByRole("link", { name: "Export review bundle" }).click();
    expect((await download).suggestedFilename()).toMatch(/^proofops-.*\.zip$/);
    expect(errors).toEqual([]);
  });
}

test("guard fixtures and new commit invalidate applicability without activation", async ({
  page,
}) => {
  await runReplay(page, "unsafe-resize", "Revise the change");
  await page.getByRole("button", { name: "Prepare guard draft" }).click();
  await expect(page.getByText("Not active", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Run guard fixtures" }).click();
  await expect(
    page.getByRole("link", { name: "Export guard draft" }),
  ).toBeVisible();
  await expect(page.locator(".fixture-results > span")).toHaveCount(10);
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export guard draft" }).click();
  expect((await download).suggestedFilename()).toMatch(
    /^proofops-guard-.*\.zip$/,
  );
  await page
    .getByText("Check applicability to another commit", { exact: true })
    .click();
  await page
    .getByLabel("Candidate commit", { exact: true })
    .fill("c".repeat(40));
  await page
    .getByRole("button", { name: "Check applicability", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "does not apply to the new revision",
  );
});

test("outcomes preserve operator intent and sample billing totals", async ({
  page,
}) => {
  await runReplay(page, "valid-resize", "Ready for engineering review");
  await page
    .getByText("Record an operator disposition", { exact: true })
    .click();
  await page
    .getByLabel("Disposition", { exact: true })
    .selectOption("insufficient_evidence");
  await page
    .getByLabel("Reason", { exact: true })
    .fill("Browser test: live workload evidence still required.");
  await page
    .getByRole("button", { name: "Save disposition", exact: true })
    .click();
  await expect(
    page.getByText("Check Outcomes for the recorded disposition."),
  ).toBeVisible();
  await page.getByRole("link", { name: "Outcomes", exact: true }).click();
  await expect(
    page
      .getByText("Browser test: live workload evidence still required.")
      .first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Load billing sample" }).click();
  await expect(
    page.getByText("USD · 1,000 ROWS", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("$20.52023", { exact: true })).toBeVisible();
  await expect(page.getByText("$14.97651", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Load billing sample" }).click();
  await expect(
    page.getByText("USD · 1,000 ROWS", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../artifacts/screenshots/outcomes.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 320, height: 740 });
  await page
    .getByText("Inspect service and currency totals", { exact: true })
    .click();
  await expectNoPageOverflow(page);
  await expect(
    page.getByRole("region", { name: "Billing service and currency totals" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../artifacts/screenshots/outcomes-mobile.png",
    fullPage: true,
  });
});

test("reviews are usable on a narrow viewport and unavailable data is not zero", async ({
  page,
}) => {
  await page.goto("/#/reviews");
  await expect(page.getByText("Backend ready", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../artifacts/screenshots/reviews.png",
    fullPage: true,
  });
  for (const width of [320, 768, 390]) {
    await page.setViewportSize({ width, height: 844 });
    const runButton = page.getByRole("button", {
      name: "Run review",
      exact: true,
    });
    await expect(runButton).toBeVisible();
    await expectNoPageOverflow(page);
    const form = await page
      .getByRole("complementary", { name: "Start with a replay" })
      .boundingBox();
    const history = await page
      .getByRole("region", { name: "Recent reviews", exact: true })
      .boundingBox();
    expect(form!.y).toBeLessThan(history!.y);
    await page.getByRole("button", { name: "New review", exact: true }).click();
    await expect(page.getByLabel("Review scenario")).toBeFocused();
    await page.screenshot({
      path: `../artifacts/screenshots/reviews-${width}.png`,
      fullPage: true,
    });
  }
  await page.route("**/api/v1/analytics", (route) => route.abort());
  await page.reload();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.locator(".metric").first()).toContainText("Unavailable");
  await expectNoPageOverflow(page);
});
