import { defineConfig } from "vite"
import { fileURLToPath } from "node:url"

const resolve = (file: string) => fileURLToPath(new URL(file, import.meta.url))
export default defineConfig({
  resolve: { alias: [
    { find: /^react$/, replacement: resolve("./node_modules/react/index.js") },
    { find: /^react\/jsx-runtime$/, replacement: resolve("./node_modules/react/jsx-runtime.js") },
    { find: /^react\/jsx-dev-runtime$/, replacement: resolve("./node_modules/react/jsx-dev-runtime.js") },
    { find: /^react-dom\/client$/, replacement: resolve("./node_modules/react-dom/client.js") },
  ] },
  esbuild: { jsx: "automatic" },
  server: { host: "127.0.0.1", port: 4173, strictPort: true, fs: { allow: [resolve("../../../")] } },
})
