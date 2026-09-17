import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

interface HeightDragOptions {
  storageKey: string;
  direction: "up" | "down";
  min: number;
  max: number;
  fallbackHeight?: number;
}

export function useHeightDrag<Element extends HTMLElement>({
  storageKey, direction, min, max, fallbackHeight = 0,
}: HeightDragOptions) {
  const ref = useRef<Element>(null);
  const cleanup = useRef<(() => void) | null>(null);
  const [height, setHeight] = useState(() => {
    try {
      const saved = Number(window.localStorage.getItem(storageKey) ?? 0);
      return Number.isFinite(saved) && saved >= min ? Math.min(max, saved) : 0;
    } catch { return 0; }
  });

  useEffect(() => () => cleanup.current?.(), [storageKey]);

  function resetHeight() {
    cleanup.current?.();
    setHeight(0);
    try { window.localStorage.removeItem(storageKey); } catch {}
  }

  function startResize(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    cleanup.current?.();
    const startY = event.clientY;
    const pointerId = event.pointerId;
    const startHeight = ref.current?.getBoundingClientRect().height ?? fallbackHeight;
    let nextHeight = startHeight;
    const move = (moveEvent: PointerEvent) => {
      if (moveEvent.pointerId !== pointerId) return;
      const delta = (moveEvent.clientY - startY) * (direction === "down" ? 1 : -1);
      nextHeight = Math.max(min, Math.min(max, startHeight + delta));
      setHeight(nextHeight);
    };
    const release = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("blur", release);
      cleanup.current = null;
    };
    const stop = (stopEvent: PointerEvent) => {
      if (stopEvent.pointerId !== pointerId) return;
      release();
      try { window.localStorage.setItem(storageKey, String(Math.round(Math.max(min, Math.min(max, nextHeight))))); }
      catch {}
    };
    const cancel = (cancelEvent: PointerEvent) => {
      if (cancelEvent.pointerId === pointerId) release();
    };
    cleanup.current = release;
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("blur", release);
  }

  return { ref, height, startResize, resetHeight };
}