/**
 * useGlobalShortcuts \u2014 install document-level keyboard shortcuts.
 *
 * Role:
 *   Mounted once in App.tsx. Listens on `document` (capture phase) for the
 *   shortcut table documented in HelpOverlay.tsx. Ignores key events whose
 *   target is an editable surface (input, textarea, contentEditable) so
 *   typing a message never triggers a tab switch.
 *
 * Bindings:
 *   - \u2318K / Ctrl+K  toggle command palette
 *   - ?           open help overlay
 *   - 1..6        switch centre tab (priorities / situation / status /
 *                 topology / data / detector tuning)
 *   - /           focus chat input (queries [data-testid=chat-input])
 *   - Esc         close palette or help overlay
 */

import { useEffect } from "react";
import { usePanelStore } from "@/stores/panelStore";
import type { CenterTab } from "@/stores/panelStore";
import { usePaletteStore } from "@/stores/paletteStore";

/** Map digit keys to centre-tab ids. Used by the `1..5` bindings. */
const DIGIT_TAB: Record<string, CenterTab> = {
  "1": "priorities",
  "2": "situation",
  "3": "status",
  "4": "topology",
  "5": "data",
  "6": "tuning",
};

/** True when the event originated inside an editable surface and we should
 *  not intercept the keystroke. */
function isEditableTarget(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (t.isContentEditable) return true;
  return false;
}

export function useGlobalShortcuts() {
  useEffect(() => {
    const togglePalette = usePaletteStore.getState().togglePalette;
    const closeAll = () => {
      const s = usePaletteStore.getState();
      if (s.open) s.close();
      if (s.helpOpen) s.closeHelp();
    };
    const openHelp = usePaletteStore.getState().openHelp;
    const setCenterTab = usePanelStore.getState().setCenterTab;

    const handler = (e: KeyboardEvent) => {
      /* Palette is cross-cutting: \u2318K / Ctrl+K always toggles, even from
         inside an input. Mirrors user expectation from VS Code, Linear,
         Notion, etc. */
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        togglePalette();
        return;
      }

      /* Esc closes any open overlay. Safe inside inputs \u2014 if no overlay
         is open, default behaviour (blur) remains. */
      if (e.key === "Escape") {
        const s = usePaletteStore.getState();
        if (s.open || s.helpOpen) { e.preventDefault(); closeAll(); return; }
      }

      /* All other shortcuts must not fire while typing. */
      if (isEditableTarget(e)) return;
      /* Skip modifier-bearing keys (Ctrl/Alt/Meta combos are reserved for
         future bindings and browser accelerators). */
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      if (e.key === "?") {
        e.preventDefault();
        openHelp();
        return;
      }

      if (e.key === "/") {
        /* Focus the first chat input on the page. Using the testid used
           across the e2e suite rather than a fragile CSS path. */
        const target = document.querySelector('[data-testid="chat-input-textarea"], [data-testid="chat-input"] textarea') as HTMLElement | null;
        if (target) { e.preventDefault(); target.focus(); }
        return;
      }

      const tab = DIGIT_TAB[e.key];
      if (tab) {
        e.preventDefault();
        setCenterTab(tab);
      }
    };

    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);
}
