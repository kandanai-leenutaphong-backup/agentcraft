import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const frontendPackage = JSON.parse(readFileSync(new URL("./component-package.json", import.meta.url), "utf8"));
const externalPackages = ["react-dom", ...Object.keys(frontendPackage.peerDependencies)];

export default {
  resolve: {
    alias: {
      "@components": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  build: {
    outDir: "dist-skillpack-check",
    emptyOutDir: false,
    lib: {
      entry: fileURLToPath(new URL("./agent_optimization/frontend/index.ts", import.meta.url)),
      formats: ["es"],
      fileName: "agent-optimization",
    },
    rollupOptions: {
      external: (specifier) => externalPackages.some(name => specifier === name || specifier.startsWith(`${name}/`)),
    },
  },
};