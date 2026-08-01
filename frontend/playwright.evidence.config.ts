import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/evidence",
  testMatch: "day13-recognition.spec.ts",
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:3100",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 1100 },
    screenshot: "off",
    trace: "off",
    video: "off",
  },
  webServer: {
    command: "npm.cmd run dev -- --hostname 127.0.0.1 --port 3100",
    url: "http://127.0.0.1:3100/recognition",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
