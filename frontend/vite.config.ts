import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // El service worker de MSW vive fuera de public/: nunca llega al build de distribución.
  publicDir: command === "serve" ? "public-dev" : false,
  server: {
    proxy: { "/api": process.env.WALLBA_API_PROXY ?? "http://127.0.0.1:8000" },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // Estas dos suites de P2 usan node:test y corren con `npm run test:node`.
    exclude: ["src/features/policies/__tests__/**", "node_modules/**"],
  },
}))
