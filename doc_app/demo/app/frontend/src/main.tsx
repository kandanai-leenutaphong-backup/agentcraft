/**
 * Application entry point — mounts the React app to the DOM.
 *
 * Module role:
 *   Creates the React root, wraps the App component in StrictMode (enables
 *   development-only checks), and imports global CSS (Tailwind base + custom
 *   theme tokens). Theme is dark-only — the light mode toggle was removed
 *   2026-04-17; tokens.css ships dark tokens at :root.
 *
 * Render target: <div id="root"> in index.html
 *
 * Key collaborators:
 *   - App.tsx          — the application shell
 *   - index.css        — Tailwind base + CSS custom properties
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { AuthProvider, initAuth } from "./auth";
import "./index.css";

/* Initialise auth before React renders.
   Wrapped in async IIFE — top-level await requires build.target="esnext"
   in vite.config.ts which the project does not currently set.
   When AUTH_ENABLED=false, initAuth() is a fast no-op (one fetch). */
(async () => {
  await initAuth();

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ErrorBoundary>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ErrorBoundary>
    </StrictMode>,
  );
})();
