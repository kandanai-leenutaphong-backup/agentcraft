import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const resourceExplorer = fileURLToPath(new URL("../../../../../libraries/resource-explorer", import.meta.url));
const eventStream = fileURLToPath(new URL("../../../../../libraries/event-stream", import.meta.url));
const sourceCode = fileURLToPath(new URL("../../../../../libraries/source-code", import.meta.url));
const modules = fileURLToPath(new URL("./node_modules", import.meta.url));

// dev.sh exports both, so a port override moves the backend and this proxy together.
const backendPort = process.env.CYBEREYE_PORT ?? "9000";
const frontendPort = Number(process.env.CYBEREYE_FRONTEND_PORT ?? 5173);

export default defineConfig({
  plugins: [react()],
  resolve: {
    // The terminal component imports xterm and its stylesheet by bare specifier from
    // outside this project, where a node_modules walk finds nothing. These aliases are
    // prefix rules, so the deep CSS import resolves through them too.
    alias: {
      "@agentcraft/resource-explorer": `${resourceExplorer}/frontend/index.ts`,
      "@agentcraft/event-stream": `${eventStream}/frontend/index.ts`,
      "@agentcraft/source-code": `${sourceCode}/frontend/index.ts`,
      "@xterm/xterm": `${modules}/@xterm/xterm`,
      "@xterm/addon-fit": `${modules}/@xterm/addon-fit`,
    },
    // Component sources sit outside this project, so bare `react` would resolve
    // upward from their own directory and find nothing. One React instance,
    // this project's.
    dedupe: ["react", "react-dom", "lucide-react", "shiki", "@xterm/xterm", "@xterm/addon-fit"],
  },
  server: {
    // Loopback only, and no silent shift to another port: the backend admits this machine.
    host: "127.0.0.1",
    port: frontendPort,
    strictPort: true,
    proxy: { "/api": { target: `http://127.0.0.1:${backendPort}`, changeOrigin: false } },
    fs: { allow: [resourceExplorer, eventStream, sourceCode, fileURLToPath(new URL(".", import.meta.url))] },
  },
});
