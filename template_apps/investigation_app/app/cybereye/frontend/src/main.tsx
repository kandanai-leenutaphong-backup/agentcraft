import { createRoot } from "react-dom/client";
import App from "./app/App";
// Import order is the cascade: these files were authored against this sequence, so it is
// preserved exactly as the layout moved beneath it.
import "./shared/styles/styles.css";
import "./shared/styles/markdown.css";
import "./features/scanner/scanner.css";
import "./features/scanner/scanner-responsive.css";
import "./shared/agent-output/tool-renders.css";
import "./shared/styles/derived.css";
import "./shared/styles/primitives.css";
import "./shared/styles/workspace.css";

createRoot(document.getElementById("root")!).render(<App />);
