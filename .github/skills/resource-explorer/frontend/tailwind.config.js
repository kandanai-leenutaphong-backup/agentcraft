/**
 * Tailwind, bound to the role tokens rather than to literal colours.
 *
 * `text-primary` means the same thing in both themes because it resolves to a
 * variable the theme block swaps. A component that reaches for a Tailwind
 * palette colour instead has left the design system.
 *
 * @type {import('tailwindcss').Config}
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--ds-canvas)",
        canvas2: "var(--ds-canvas2)",
        surface: "var(--ds-surface)",
        surface2: "var(--ds-surface2)",
        primary: "var(--ds-primary)",
        secondary: "var(--ds-secondary)",
        border: "var(--ds-border)",
        "border-soft": "var(--ds-border-soft)",
        muted: "var(--ds-muted)",
        flow: "var(--ds-flow)",
        group: "var(--ds-group)",
        success: "var(--ds-success)",
        warning: "var(--ds-warning)",
        critical: "var(--ds-critical)",
        focus: "var(--ds-focus)",
        "flow-tint": "var(--ds-flow-tint)",
        "warning-tint": "var(--ds-warning-tint)",
        "critical-tint": "var(--ds-critical-tint)",
      },
      borderRadius: {
        DEFAULT: "3px",
        sm: "2px",
        md: "3px",
        lg: "4px",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
