import { useCallback, useRef, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

const STORE = "cybereye.sections";

function readStore(): Record<string, boolean> {
  try {
    const raw = window.localStorage.getItem(STORE);
    return raw ? JSON.parse(raw) as Record<string, boolean> : {};
  } catch {
    return {};
  }
}

/** Folding a section should survive the next situation, so the choice is remembered per id. */
export function useSectionState(id: string, defaultOpen: boolean) {
  const [open, setOpen] = useState(() => readStore()[id] ?? defaultOpen);
  const toggle = useCallback(() => {
    setOpen((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(STORE, JSON.stringify({ ...readStore(), [id]: next }));
      } catch { /* a full or blocked store must not break the panel */ }
      return next;
    });
  }, [id]);
  return [open, toggle] as const;
}

interface Props {
  id: string;
  title: string;
  /** Shown in the header whenever the section is folded, so folding never hides the answer. */
  digest?: ReactNode;
  badge?: ReactNode;
  hint?: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}

function readHeight(id: string): number {
  const saved = Number(window.localStorage.getItem(`cybereye.height.${id}`) ?? 0);
  return Number.isFinite(saved) && saved > 60 ? saved : 0;
}

export function Section({ id, title, digest, badge, hint, defaultOpen = true, className = "", children }: Props) {
  const [open, toggle] = useSectionState(id, defaultOpen);
  const [height, setHeight] = useState(() => readHeight(id));
  const body = useRef<HTMLDivElement>(null);
  const bodyId = `section-${id}`;

  function startResize(event: React.PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = body.current?.getBoundingClientRect().height ?? 0;
    const move = (moveEvent: PointerEvent) => {
      setHeight(Math.max(60, Math.min(1200, startHeight + (moveEvent.clientY - startY))));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      const measured = Math.round(body.current?.getBoundingClientRect().height ?? 0);
      window.localStorage.setItem(`cybereye.height.${id}`, String(measured));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  return (
    <section className={`fold ${className} ${open ? "open" : "closed"}`} aria-label={title}>
      <header className="fold-head">
        {hint}
        <button type="button" className="fold-toggle" aria-expanded={open} aria-controls={bodyId} onClick={toggle}>
          <ChevronDown size={12} className={open ? "" : "closed"} />
          <b>{title}</b>
        </button>
        {badge}
        {!open && digest && <span className="fold-digest">{digest}</span>}
        {open && height > 0 && (
          <button
            type="button" className="fold-reset" title="Restore natural height"
            onClick={() => { setHeight(0); window.localStorage.removeItem(`cybereye.height.${id}`); }}
          >auto</button>
        )}
      </header>
      {open && (
        <>
          <div
            className="fold-body" id={bodyId} ref={body}
            style={height ? { height, overflowY: "auto" } : undefined}
          >{children}</div>
          <div
            className="fold-grip" role="separator" aria-orientation="horizontal"
            aria-label={`Resize ${title}`} onPointerDown={startResize}
          />
        </>
      )}
    </section>
  );
}

