/**
 * Foundation constants — zero-dependency shared primitives.
 *
 * Module role:
 *   Single source of truth for the backend API base URL. Every module
 *   that makes HTTP requests imports BASE from here instead of resolving
 *   ``import.meta.env.VITE_API_URL`` inline.
 *
 * Dependency rules:
 *   This file MUST have zero imports — it is loaded before any other
 *   module (including by consoleInterceptor which runs before React).
 *
 * Dependents:
 *   api/client.ts, auth/authConfig.ts, hooks/useScenario.ts,
 *   hooks/useTopology.ts, utils/consoleInterceptor.ts,
 *   stores/observabilityStore.ts, components/sidebar/ServiceHealth.tsx
 */

/** Backend API base URL — resolves from VITE_API_URL env var or falls back to "/api". */
export const BASE = import.meta.env.VITE_API_URL ?? "/api";

/**
 * Kiosk mode flag — when true, the bundle ships as a self-contained demo
 * with no backend. Every code path that would otherwise call /api/* must
 * gate on this flag and either no-op or use bundled fixtures.
 *
 * Set at build time by `VITE_KIOSK_MODE=true npm run build` and consumed
 * here as a literal so Vite tree-shakes dead branches in the kiosk bundle.
 */
export const IS_KIOSK = import.meta.env.VITE_KIOSK_MODE === "true";

