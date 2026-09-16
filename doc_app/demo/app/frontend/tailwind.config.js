/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    /* ── Font sizes — centralized via CSS vars from tokens.css ────── */
    fontSize: {
      micro: ["var(--font-size-micro)", { lineHeight: "1rem" }],
      label: ["var(--font-size-label)", { lineHeight: "1rem" }],
      xs:    ["var(--font-size-xs)",    { lineHeight: "1rem" }],
      sm:    ["var(--font-size-sm)",    { lineHeight: "1.25rem" }],
      base:  ["var(--font-size-base)",  { lineHeight: "1.5rem" }],
      lg:    ["var(--font-size-lg)",    { lineHeight: "1.75rem" }],
      xl:    ["var(--font-size-xl)",    { lineHeight: "1.75rem" }],
      display: ["var(--font-size-display)", { lineHeight: "1.75rem" }],
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      colors: {
        /* ── Stock Tailwind hues, bent to Developer Dark ──────────── */
        /* A handful of components reach past the semantic tokens for a raw
           utility like `text-emerald-400`. Rather than chase 36 call sites,
           the hues those utilities resolve to are redefined here, so every
           one of them lands inside the palette. */
        emerald: {
          200: "#a6c8b1", 300: "#8cba9a", 400: "#78a887",
          500: "#78a887", 600: "#659476", 700: "#527f63",
        },
        green: {
          400: "#78a887", 500: "#78a887", 600: "#659476",
        },
        teal: {
          300: "#8fbcd6", 400: "#71a7c4", 500: "#71a7c4",
        },
        amber: {
          50: "rgba(196, 154, 90, 0.10)", 100: "rgba(196, 154, 90, 0.18)",
          200: "#dcbb8c", 300: "#d4ac70", 400: "#c49a5a",
          500: "#c49a5a", 600: "#b0873f", 700: "#8f6c2f",
        },
        yellow: {
          300: "#d4ac70", 400: "#c49a5a", 500: "#c49a5a",
        },
        orange: {
          300: "#f5c99a", 400: "#f2b880", 500: "#f2b880",
        },
        red: {
          300: "#f09c9c", 400: "#e98a8a", 500: "#e98a8a",
          600: "#d97676", 700: "#c46161",
        },
        rose: {
          400: "#e98a8a", 500: "#e98a8a",
        },
        cyan: {
          300: "#8fbcd6", 400: "#71a7c4", 500: "#71a7c4",
        },
        sky: {
          300: "#8fbcd6", 400: "#71a7c4", 500: "#71a7c4",
        },
        blue: {
          300: "#8fbcd6", 400: "#71a7c4", 500: "#71a7c4", 600: "#5b93b1",
        },
        indigo: {
          300: "#a99ec9", 400: "#9387b5", 500: "#9387b5",
        },
        violet: {
          300: "#a99ec9", 400: "#9387b5", 500: "#9387b5",
        },
        purple: {
          300: "#a99ec9", 400: "#9387b5", 500: "#9387b5",
        },
        gray: {
          200: "#b2b9c1", 300: "#9aa2ac", 400: "#7d8794",
          600: "#56616d", 700: "#3a424b", 800: "#22272e", 900: "#171a1f",
        },
        slate: {
          200: "#b2b9c1", 300: "#9aa2ac", 400: "#7d8794",
          600: "#56616d", 700: "#3a424b", 800: "#22272e", 900: "#171a1f",
        },

        /* ── Core palette (existing) ─────────────────────────────── */
        brand: {
          DEFAULT: "var(--color-brand)",
          hover: "var(--color-brand-hover)",
          light: "var(--color-brand-light)",
          subtle: "var(--color-brand-subtle)",
        },
        neutral: {
          bg1: "var(--color-bg-1)",
          bg2: "var(--color-bg-2)",
          bg3: "var(--color-bg-3)",
          bg4: "var(--color-bg-4)",
          bg5: "var(--color-bg-5)",
          bg6: "var(--color-bg-6)",
        },
        text: {
          primary: "var(--color-text-primary)",
          secondary: "var(--color-text-secondary)",
          muted: "var(--color-text-muted)",
          tertiary: "var(--color-text-tertiary)",
        },
        border: {
          subtle: "var(--color-border-subtle)",
          DEFAULT: "var(--color-border-default)",
          strong: "var(--color-border-strong)",
        },
        // Tone-shift line for visible-but-quiet dividers (panel resize
        // handles, tab-group separators, markdown hr). Distinct from
        // `border-*` which is now transparent under the borderless
        // philosophy. Use `bg-divider` exclusively for these affordances.
        divider: "var(--color-divider)",
        status: {
          success: "var(--color-success)",
          warning: "var(--color-warning)",
          error: "var(--color-error)",
          info: "var(--color-info)",
          "success-surface": "var(--color-success-surface)",
          "warning-surface": "var(--color-warning-surface)",
          "error-surface": "var(--color-error-surface)",
          "info-surface": "var(--color-info-surface)",
        },
        header: {
          bg: "var(--color-header-bg)",
          text: "var(--color-header-text)",
          border: "var(--color-header-border)",
        },

        /* ── New semantic groups ─────────────────────────────────── */
        app: {
          bg: "var(--color-bg-app)",
        },
        "center-panel": {
          bg: "var(--color-bg-center-panel)",
        },
        on: {
          accent: "var(--color-on-accent)",
        },
        priority: {
          critical:        "var(--color-priority-critical)",
          "critical-text": "var(--color-priority-critical-text)",
          "critical-surface": "var(--color-priority-critical-surface)",
          "critical-border":  "var(--color-priority-critical-border)",
          "critical-hover":   "var(--color-priority-critical-hover)",
          urgent:          "var(--color-priority-urgent)",
          "urgent-text":   "var(--color-priority-urgent-text)",
          "urgent-surface":   "var(--color-priority-urgent-surface)",
          "urgent-border":    "var(--color-priority-urgent-border)",
          "urgent-hover":     "var(--color-priority-urgent-hover)",
          standard:        "var(--color-priority-standard)",
          "standard-text": "var(--color-priority-standard-text)",
          low:             "var(--color-priority-low)",
          "low-text":      "var(--color-priority-low-text)",
          info:            "var(--color-priority-info)",
          "info-text":     "var(--color-priority-info-text)",
          done:            "var(--color-priority-done)",
        },
        severity: {
          credible:       "var(--color-severity-credible)",
          "non-credible": "var(--color-severity-non-credible)",
          protected:      "var(--color-severity-protected)",
          uncertain:      "var(--color-severity-uncertain)",
          na:             "var(--color-severity-na)",
          "count-bg":     "var(--color-severity-count-bg)",
        },
        watcher: {
          "dormant-bg":    "var(--color-watcher-dormant-bg)",
          "dormant-text":  "var(--color-watcher-dormant-text)",
          "assessing-bg":  "var(--color-watcher-assessing-bg)",
          "assessing-text":"var(--color-watcher-assessing-text)",
          "alerting-bg":   "var(--color-watcher-alerting-bg)",
          "alerting-text": "var(--color-watcher-alerting-text)",
          "flash-ring":    "var(--color-watcher-flash-ring)",
          "flash-shadow":  "var(--color-watcher-flash-shadow)",
          icon:            "var(--color-watcher-icon)",
        },
        delegation: {
          bg:     "var(--color-delegation-bg)",
          text:   "var(--color-delegation-text)",
          border: "var(--color-delegation-border)",
          label:  "var(--color-delegation-label)",
        },
        situation: {
          critical:             "var(--color-situation-critical)",
          "critical-text":      "var(--color-situation-critical-text)",
          major:                "var(--color-situation-major)",
          "major-text":         "var(--color-situation-major-text)",
          serious:              "var(--color-situation-serious)",
          "serious-text":       "var(--color-situation-serious-text)",
          investigate:          "var(--color-situation-investigate)",
          "investigate-text":   "var(--color-situation-investigate-text)",
        },
        tag: {
          "alarm-bg":    "var(--color-tag-alarm-bg)",
          "alarm-text":  "var(--color-tag-alarm-text)",
          "scada-bg":    "var(--color-tag-scada-bg)",
          "scada-text":  "var(--color-tag-scada-text)",
          "pattern-bg":  "var(--color-tag-pattern-bg)",
          "pattern-text":"var(--color-tag-pattern-text)",
        },
        placeholder: {
          DEFAULT: "var(--color-placeholder)",
        },
        sim: {
          "inject-bg":     "var(--color-sim-inject-bg)",
          "inject-hover":  "var(--color-sim-inject-hover)",
          "disabled-bg":   "var(--color-sim-disabled-bg)",
          "disabled-text": "var(--color-sim-disabled-text)",
          "reset-bg":      "var(--color-sim-reset-bg)",
          "reset-text":    "var(--color-sim-reset-text)",
          "reset-hover":   "var(--color-sim-reset-hover)",
        },
        section: {
          "gradient-from": "var(--color-section-gradient-from)",
          "gradient-via":  "var(--color-section-gradient-via)",
          "gradient-hover":"var(--color-section-gradient-hover)",
          label:           "var(--color-section-label)",
          indicator:       "var(--color-section-indicator)",
          empty:           "var(--color-section-empty)",
        },
        subsection: {
          "gradient-from": "var(--color-subsection-gradient-from)",
          "gradient-via":  "var(--color-subsection-gradient-via)",
          "gradient-hover":"var(--color-subsection-gradient-hover)",
        },
        overlay: {
          bg:               "var(--color-overlay-bg)",
          border:           "var(--color-overlay-border)",
          hover:            "var(--color-overlay-hover)",
          "backdrop-light": "var(--color-overlay-backdrop-light)",
          backdrop:         "var(--color-overlay-backdrop)",
          "backdrop-heavy": "var(--color-overlay-backdrop-heavy)",
        },
        "error-page": {
          bg:        "var(--color-error-page-bg)",
          text:      "var(--color-error-page-text)",
          secondary: "var(--color-error-page-secondary)",
          "button-bg": "var(--color-error-page-button-bg)",
          "code-bg":   "var(--color-error-page-code-bg)",
          "code-text": "var(--color-error-page-code-text)",
        },
        teams: {
          backdrop:    "var(--color-teams-backdrop)",
          avatar:      "var(--color-teams-avatar)",
          status:      "var(--color-teams-status)",
          text:        "var(--color-teams-text)",
          "text-muted":"var(--color-teams-text-muted)",
          "control-bg":"var(--color-teams-control-bg)",
          "control-hover":"var(--color-teams-control-hov)",
          mute:        "var(--color-teams-mute)",
          "mute-hover":"var(--color-teams-mute-hover)",
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.4s infinite ease-in-out both",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 80%, 100%": { transform: "scale(0.6)", opacity: "0.4" },
          "40%": { transform: "scale(1)", opacity: "1" },
        },
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography"),
    /* Couturier R9 (2026-05-17): container queries enable the
       SituationCard head row to reflow as the surrounding
       react-resizable-panels column narrows. Viewport-based breakpoints
       are useless here because the viewport never changes when the
       operator drags the splitter. */
    require("@tailwindcss/container-queries"),
  ],
};
