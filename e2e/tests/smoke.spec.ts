import { test, expect } from "@playwright/test";

test.describe("Smoke Tests", () => {
  test("homepage loads and shows login page", async ({ page }) => {
    await page.goto("/");
    // Should redirect to login or show auth UI
    await expect(
      page.locator("text=Login").or(page.locator("text=Sign in")).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("login page has email and password fields", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator('input[type="email"], input[name="email"]').first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      page.locator('input[type="password"], input[name="password"]').first()
    ).toBeVisible();
  });

  test("login form shows error on invalid credentials", async ({ page }) => {
    await page.goto("/login");
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    const passwordInput = page.locator('input[type="password"], input[name="password"]').first();

    await emailInput.fill("invalid@example.com");
    await passwordInput.fill("wrongpassword");

    const submitButton = page.locator('button[type="submit"]').first();
    await submitButton.click();

    // Should show some error indication (toast, inline error, etc.)
    await expect(
      page
        .locator("text=failed")
        .or(page.locator("text=error"))
        .or(page.locator("text=incorrect"))
        .or(page.locator("text=invalid"))
        .or(page.locator('[role="alert"]'))
        .first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("register page is accessible", async ({ page }) => {
    await page.goto("/register");
    await expect(
      page.locator("text=Register").or(page.locator("text=Sign up")).first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("API Health", () => {
  test("backend health endpoint responds", async ({ request }) => {
    const apiBase = process.env.API_URL || "http://localhost:8001";
    const response = await request.get(`${apiBase}/health`);
    expect(response.ok()).toBeTruthy();
  });
});
