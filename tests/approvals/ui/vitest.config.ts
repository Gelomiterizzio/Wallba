import { defineConfig } from "vitest/config"
import { fileURLToPath } from "node:url"

const resolve = (file: string) => fileURLToPath(new URL(file, import.meta.url))

export default defineConfig({
  resolve: {
    alias: [
      { find: /^react$/, replacement: resolve("./node_modules/react/index.js") },
      { find: /^react\/jsx-runtime$/, replacement: resolve("./node_modules/react/jsx-runtime.js") },
      { find: /^react\/jsx-dev-runtime$/, replacement: resolve("./node_modules/react/jsx-dev-runtime.js") },
    ],
  },
  esbuild: { jsx: "automatic" },
  test: { environment: "jsdom", globals: true, setupFiles: ["./setup.ts"], include: ["*.test.ts", "*.test.tsx"] },
})
