import { test, expect } from "@playwright/test";

test.describe("Smoke Tests", () => {
  test("login page loads and shows Welcome back", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("text=Welcome back")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("login form has email and password fields", async ({ page }) => {
    await page.goto("/login");
    await expect(
      page.locator('input[type="email"], input[name="email"]').first()
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.locator('input[type="password"], input[name="password"]').first()
    ).toBeVisible();
  });

  test("register link exists on login page", async ({ page }) => {
    await page.goto("/login");
    const registerLink = page.locator('a[href="/register"]');
    await expect(registerLink).toBeVisible({ timeout: 10_000 });
    await expect(registerLink).toHaveText(/Sign up/i);
  });

  test("Continue with GitHub button is visible", async ({ page }) => {
    await page.goto("/login");
    const githubButton = page.locator("text=Continue with GitHub");
    await expect(githubButton).toBeVisible({ timeout: 10_000 });
  });

  test("navigation to register page works", async ({ page }) => {
    await page.goto("/login");
    const registerLink = page.locator('a[href="/register"]');
    await registerLink.click();
    await expect(page).toHaveURL(/\/register/);
    await expect(page.locator("text=Create account")).toBeVisible({
      timeout: 10_000,
    });
  });
});
