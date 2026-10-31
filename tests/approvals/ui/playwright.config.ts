import { defineConfig } from "@playwright/test"

export default defineConfig({
  testDir: ".", testMatch: "*.browser.ts", fullyParallel: false, workers: 1,
  outputDir: ".artifacts/browser-results",
  use: { baseURL: "http://127.0.0.1:4173", browserName: "chromium", headless: true },
  webServer: { command: "npm run preview:fixtures", url: "http://127.0.0.1:4173", reuseExistingServer: false, timeout: 30000 },
  reporter: [["list"], ["json", { outputFile: ".artifacts/browser-results.json" }]],
})
