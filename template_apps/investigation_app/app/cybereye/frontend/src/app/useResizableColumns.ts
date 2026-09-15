import { KeyboardEvent, PointerEvent, useRef, useState } from "react";

const MINIMUM = [18, 20];

/**
 * Three columns whose widths a person can move, by pointer or by keyboard.
 *
 * Pointer drag is continuous; the keyboard equivalent nudges in fixed steps. Both keep the
 * dragged pair's total width constant, so a move that would breach a minimum is simply
 * refused rather than pushing the loss onto a third column.
 */
export function useResizableColumns(initial: number[]) {
  const [columns, setColumns] = useState(initial);
  const shell = useRef<HTMLElement>(null);

  function resize(index: 0 | 1, event: PointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const width = shell.current?.getBoundingClientRect().width ?? window.innerWidth;
    const startX = event.clientX;
    const start = [...columns];
    const move = (next: globalThis.PointerEvent) => {
      const delta = ((next.clientX - startX) / width) * 100;
      const left = Math.max(MINIMUM[0], start[index] + delta);
      const right = Math.max(MINIMUM[1], start[index + 1] - delta);
      if (left + right !== start[index] + start[index + 1]) return;
      setColumns((current) => current.map((value, position) => position === index ? left : position === index + 1 ? right : value));
    };
    const stop = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", stop);
  }

  function nudge(index: 0 | 1, event: KeyboardEvent<HTMLDivElement>) {
    const step = event.key === "ArrowLeft" ? -2 : event.key === "ArrowRight" ? 2 : 0;
    if (step === 0) return;
    event.preventDefault();
    setColumns((current) => {
      const left = current[index] + step;
      const right = current[index + 1] - step;
      if (left < MINIMUM[0] || right < MINIMUM[1]) return current;
      return current.map((value, position) => position === index ? left : position === index + 1 ? right : value);
    });
  }

  function resizerProps(index: 0 | 1, label: string) {
    return {
      className: "column-resizer", role: "separator" as const, tabIndex: 0,
      "aria-label": label, "aria-orientation": "vertical" as const,
      "aria-valuenow": Math.round(columns[index]), "aria-valuemin": MINIMUM[0], "aria-valuemax": 80,
      "aria-valuetext": `${Math.round(columns[index])} percent`,
      onPointerDown: (event: PointerEvent<HTMLDivElement>) => resize(index, event),
      onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => nudge(index, event),
    };
  }

  return { columns, shell, resizerProps };
}
