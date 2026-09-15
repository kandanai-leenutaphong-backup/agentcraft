import { createRoot } from "react-dom/client";
import { FlaskConical } from "lucide-react";
import { OptimizationApiProvider, OptimizationWorkspace, createOptimizationApi } from "@components/agent_optimization/frontend";
import "./styles.css";

async function requestJson<Result>(path: string, options: RequestInit = {}): Promise<Result> {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`);
  }
  return response.json() as Promise<Result>;
}

const client = createOptimizationApi(requestJson);

function App() {
  return <div className="optimizer-app">
    <header className="optimizer-header">
      <FlaskConical size={23} aria-hidden="true" />
      <h1>Custom Optimizer</h1>
      <span>GUIDE / Historical experiments</span>
    </header>
    <main aria-label="Agent optimization">
      <OptimizationApiProvider client={client}><OptimizationWorkspace active /></OptimizationApiProvider>
    </main>
  </div>;
}

createRoot(document.getElementById("root")!).render(<App />);