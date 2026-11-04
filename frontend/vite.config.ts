import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Relative asset paths: the URL base (e.g. /rutrackarr) is only known at runtime;
// the backend injects <base href> into index.html when serving it.
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    proxy: { "/api": "http://127.0.0.1:8787" },
  },
})
