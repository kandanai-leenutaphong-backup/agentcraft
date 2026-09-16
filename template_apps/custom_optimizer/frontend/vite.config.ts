import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const optimization = fileURLToPath(new URL("../../../libraries/agent-optimization", import.meta.url));
const terminal = fileURLToPath(new URL("../../../libraries/copilot-terminal", import.meta.url));
const sourceCode = fileURLToPath(new URL("../../../libraries/source-code", import.meta.url));
const modules = fileURLToPath(new URL("./node_modules", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@agentcraft/source-code": `${sourceCode}/frontend/index.ts`,
      "@xterm/xterm": `${modules}/@xterm/xterm`, "@xterm/addon-fit": `${modules}/@xterm/addon-fit` },
    dedupe: ["react", "react-dom", "lucide-react", "shiki", "@xterm/xterm", "@xterm/addon-fit"],
  },
  server: {
    host: "127.0.0.1", port: Number(process.env.CYBEREYE_FRONTEND_PORT ?? 5180), strictPort: true,
    proxy: { "/api": { target: `http://127.0.0.1:${process.env.CYBEREYE_PORT ?? 9012}`, changeOrigin: false } },
    fs: { allow: [optimization, terminal, sourceCode, fileURLToPath(new URL(".", import.meta.url))] },
  },
});