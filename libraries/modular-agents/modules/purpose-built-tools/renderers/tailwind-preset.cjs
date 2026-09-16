/**
 * Tailwind preset mapping the token variables onto the class names the
 * renderers use. Extend your config with it:
 *
 *   // tailwind.config.js
 *   module.exports = {
 *     presets: [require("./renderers/tailwind-preset.cjs")],
 *     content: ["./src/**\/*.tsx", "./renderers/**\/*.tsx"],
 *   };
 *
 * The `content` entry matters: without the renderer directory in it, Tailwind
 * finds no usage of these classes and purges every one of them, and the cards
 * render unstyled with a config that looks correct (GOTCHAS.md G17).
 *
 * Every value dereferences a CSS variable rather than hard-coding a colour, so
 * a consumer overriding a variable in their own stylesheet changes the cards
 * without touching this file or rebuilding the preset.
 */

module.exports = {
  theme: {
    extend: {
      colors: {
        neutral: {
          bg1: "var(--tool-neutral-bg1)",
          bg2: "var(--tool-neutral-bg2)",
          bg3: "var(--tool-neutral-bg3)",
        },
        text: {
          primary: "var(--tool-text-primary)",
          secondary: "var(--tool-text-secondary)",
          muted: "var(--tool-text-muted)",
        },
        border: "var(--tool-border)",
        accent: "var(--tool-accent)",
        brand: "var(--tool-brand)",
        status: {
          success: "var(--tool-status-success)",
          warning: "var(--tool-status-warning)",
          error: "var(--tool-status-error)",
        },
      },
      fontSize: {
        // Two sizes below Tailwind's `xs`, because a card packs badges, chips
        // and table metadata around body text and needs a scale under it.
        micro: ["0.6875rem", { lineHeight: "1rem" }],
        label: ["0.75rem", { lineHeight: "1rem" }],
      },
    },
  },
};
