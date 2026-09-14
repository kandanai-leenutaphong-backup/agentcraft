/**
 * Theme, as the two halves of one token set.
 *
 * The role tokens are identical in both; only the foundation block swaps, so
 * no component branches on the theme. The choice is a display preference and
 * the only thing this app stores locally — no estate data is ever persisted.
 */

export type Theme = "sand" | "dark";

const STORAGE_KEY = "resource-explorer-theme";

export function readTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "sand" || stored === "dark") return stored;
  } catch {
    // A blocked storage is not a reason to fail to render.
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "sand";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset["theme"] = theme;
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Preference is cosmetic; losing it costs nothing.
  }
}
