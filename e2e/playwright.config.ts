import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  timeout: 30_000,

  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  /* Optionally start dev servers before tests */
  // webServer: [
  //   {
  //     command: "cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8001",
  //     port: 8001,
  //     reuseExistingServer: !process.env.CI,
  //   },
  //   {
  //     command: "cd ../frontend && npm run dev",
  //     port: 3000,
  //     reuseExistingServer: !process.env.CI,
  //   },
  // ],
});
