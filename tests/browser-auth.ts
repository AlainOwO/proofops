import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  expect,
  test as base,
  type APIRequestContext,
  type Page,
} from "../frontend/node_modules/@playwright/test";
import type { SessionInfo } from "../frontend/src/types";

type Role = "admin" | "viewer";
type Credentials = Record<Role, { username: string; password: string }>;
type StorageState = Awaited<ReturnType<APIRequestContext["storageState"]>>;

export function browserCredentials(): Credentials {
  const filename =
    process.env.PROOFOPS_BROWSER_AUTH_FILE ||
    resolve(__dirname, "../artifacts/private/browser-auth.json");
  try {
    const value = JSON.parse(readFileSync(filename, "utf8")) as Credentials;
    for (const role of ["admin", "viewer"] as const) {
      if (!value[role]?.username || !value[role]?.password) throw new Error();
    }
    return value;
  } catch {
    throw new Error(
      "Prepare local browser identities with scripts/prepare_browser_auth.py; credentials must never be committed.",
    );
  }
}

export async function loginApi(
  request: APIRequestContext,
  role: Role = "admin",
) {
  const challenge = await request.get("/api/v1/auth/login");
  expect(challenge.status()).toBe(200);
  const { csrf_token, public_demo } = await challenge.json();
  expect(
    public_demo,
    "These checks require the authenticated local workspace.",
  ).toBe(false);
  const response = await request.post("/api/v1/auth/login", {
    data: browserCredentials()[role],
    headers: { "X-CSRF-Token": csrf_token },
  });
  expect(response.status(), "Browser-test sign-in must succeed.").toBe(200);
  const session = (await response.json()) as SessionInfo;
  expect(session.role).toBe(role);
  return session;
}

export async function loginUi(page: Page, role: Role = "admin") {
  const credentials = browserCredentials()[role];
  await expect(
    page.getByRole("heading", { name: "Sign in to ProofOps" }),
  ).toBeVisible();
  await page.getByLabel("Username", { exact: true }).fill(credentials.username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
}

// Sessions stay in memory, never in storageState files or uploaded traces.
export const test = base.extend<{}, { authenticatedState: StorageState }>({
  authenticatedState: [
    async ({ playwright }, use, info) => {
      const request = await playwright.request.newContext({
        baseURL: info.project.use.baseURL,
        ignoreHTTPSErrors: info.project.use.ignoreHTTPSErrors,
      });
      await loginApi(request);
      await use(await request.storageState());
      await request.dispose();
    },
    { scope: "worker" },
  ],
  storageState: async ({ authenticatedState }, use) => {
    await use(authenticatedState);
  },
});

export { expect, type Page };
