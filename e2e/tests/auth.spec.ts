import { test, expect } from "@playwright/test";

test.describe("Auth Flow", () => {
  test("login with invalid credentials shows error", async ({ page }) => {
    await page.goto("/login");

    const emailInput = page
      .locator('input[type="email"], input[name="email"]')
      .first();
    const passwordInput = page
      .locator('input[type="password"], input[name="password"]')
      .first();

    await emailInput.fill("invalid@example.com");
    await passwordInput.fill("wrongpassword123");

    const submitButton = page.locator('button[type="submit"]').first();
    await submitButton.click();

    // Should show some error indication (toast, inline error, alert role, etc.)
    await expect(
      page
        .locator("text=/failed/i")
        .or(page.locator("text=/error/i"))
        .or(page.locator("text=/incorrect/i"))
        .or(page.locator("text=/invalid/i"))
        .or(page.locator('[role="alert"]'))
        .first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("register page loads correctly", async ({ page }) => {
    await page.goto("/register");

    await expect(page.locator("text=Create account")).toBeVisible({
      timeout: 10_000,
    });

    // Verify the register form has the expected input fields
    await expect(
      page.locator('input[type="email"], input[name="email"]').first()
    ).toBeVisible();
    await expect(
      page.locator('input[type="password"], input[name="password"]').first()
    ).toBeVisible();
  });

  test("register form validates required fields", async ({ page }) => {
    await page.goto("/register");

    // Try to submit the form without filling in any fields
    const submitButton = page.locator('button[type="submit"]').first();
    await submitButton.click();

    // HTML5 required validation should prevent submission.
    // Check that required input fields exist and are invalid (empty).
    const emailInput = page
      .locator('input[type="email"], input[name="email"]')
      .first();
    const passwordInput = page
      .locator('input[type="password"], input[name="password"]')
      .first();

    await expect(emailInput).toHaveAttribute("required", "");
    await expect(passwordInput).toHaveAttribute("required", "");

    // The page should still be on /register (form was not submitted)
    await expect(page).toHaveURL(/\/register/);
  });
});
