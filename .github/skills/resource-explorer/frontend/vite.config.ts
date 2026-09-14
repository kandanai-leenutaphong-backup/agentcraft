/**
 * Vite configuration.
 *
 * The backend serves the built SPA from `/` and `/assets/{path}` only, so the
 * default `assets/` output directory is load-bearing, not cosmetic.
 */
import { readFileSync } from "node:fs";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const BACKEND = "http://127.0.0.1:8099";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "font-license-notice",
      generateBundle() {
        this.emitFile({
          type: "asset",
          fileName: "assets/THIRD_PARTY_NOTICES.txt",
          source: readFileSync(new URL("./THIRD_PARTY_NOTICES.txt", import.meta.url), "utf8"),
        });
      },
    },
  ],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
