import { useCallback, useEffect, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";

/**
 * Expands one panel to the whole viewport. Only one may be expanded at a time, so the
 * key is held here rather than in each panel.
 */
export function useFullscreen(key: string) {
  const [active, setActive] = useState(false);

  const exit = useCallback(() => setActive(false), []);

  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setActive(false); };
    window.addEventListener("keydown", onKey);
    document.body.classList.add("has-fullscreen");
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.classList.remove("has-fullscreen");
    };
  }, [active]);

  const toggle = useCallback(() => setActive((current) => !current), []);
  return { active, toggle, exit, key };
}

export function FullscreenButton({ active, onToggle, label }: { active: boolean; onToggle: () => void; label: string }) {
  return (
    <button
      type="button" className="fullscreen-toggle"
      aria-pressed={active}
      title={active ? `Restore ${label} (Esc)` : `Expand ${label} to full screen`}
      aria-label={active ? `Restore ${label}` : `Expand ${label} to full screen`}
      onClick={onToggle}
    >
      {active ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
    </button>
  );
}

export function FullscreenExit({ onExit, label }: { onExit: () => void; label: string }) {
  return (
    <button type="button" className="fullscreen-exit" onClick={onExit}>
      <Minimize2 size={13} /> Exit full screen <kbd>Esc</kbd>
      <span className="sr-only">{label}</span>
    </button>
  );
}
