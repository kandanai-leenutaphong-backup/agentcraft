import { fileURLToPath } from "node:url";

export default {
  build: {
    lib: {
      entry: fileURLToPath(new URL("./modules/purpose-built-tools/renderers/index.ts", import.meta.url)),
      formats: ["es"],
      fileName: "modular-agents",
    },
    rollupOptions: { external: (name) => name === "react" || name.startsWith("react/") },
  },
};