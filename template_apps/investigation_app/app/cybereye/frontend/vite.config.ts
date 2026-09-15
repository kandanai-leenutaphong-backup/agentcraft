import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Component frontends live outside this project root, so the dev server has to
// be told it may serve them. The alias is the only way in: it is declared here,
// in tsconfig.app.json and in architecture.json, so a reach past a component's
// barrel is a checker failure rather than a convention nobody enforces.
const components = fileURLToPath(new URL("../../components", import.meta.url));
const foundations = fileURLToPath(new URL("../../../../shared/src/template_foundations", import.meta.url));
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
      "@components": components,
      "@foundations": foundations,
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
    fs: { allow: [components, foundations, fileURLToPath(new URL(".", import.meta.url))] },
  },
});
