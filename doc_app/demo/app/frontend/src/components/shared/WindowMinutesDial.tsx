/**
 * WindowMinutesDial — cute fun knob for the detector bucket size.
 *
 * 2026-05-24 operator brief: dial sits to the LEFT of the Input rows
 * slider in SituationControlBar. Controls `window_minutes` — the
 * inner detector bucket the signals/synthesis layers aggregate into,
 * NOT the operator's scan range (that's the date-range picker).
 *
 * Interaction:
 *   - Wheel up / down — step the value (±1, ±10 with Shift).
 *   - Click + drag (anywhere on the dial) — rotate to set.
 *   - Arrow Up / Down — keyboard step (±1, ±10 with Shift).
 *   - Right-click — reset to 10 (the backend default).
 *
 * Visual:
 *   - 48 × 48 SVG knob.
 *   - Outer track ring + filled arc from 12 o'clock CW proportional
 *     to (value − min) / (max − min).
 *   - Indicator notch at the current angle.
 *   - Tick marks at 5 / 15 / 30 / 60 min.
 *   - Centred numeric label "10m".
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface WindowMinutesDialProps {
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  step?: number;
  /** Default-reset value used by the right-click and the title tooltip. */
  defaultValue?: number;
  /** Visible label; pass null when a parent renders the label externally. */
  label?: string | null;
}

/* Sweep angles. We reserve a small gap at the bottom (270° dead zone
   centred on 6 o'clock) so the eye reads start + end clearly. The
   filled arc grows clockwise from the start angle. */
const ANGLE_START = -135; // -y axis = 12 o'clock; start at 7:30 position
const ANGLE_END = 135;    // end at 4:30 position
const ANGLE_RANGE = ANGLE_END - ANGLE_START; // 270°

function valueToAngle(value: number, min: number, max: number): number {
  const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)));
  return ANGLE_START + ratio * ANGLE_RANGE;
}

function angleToValue(angle: number, min: number, max: number, step: number): number {
  /* Clamp angle to the sweep. Angles outside the dead zone get snapped
     to the nearer rail so a drag past the bottom does not wrap. */
  let a = angle;
  while (a < -180) a += 360;
  while (a > 180) a -= 360;
  if (a < ANGLE_START) a = ANGLE_START;
  if (a > ANGLE_END) a = ANGLE_END;
  const ratio = (a - ANGLE_START) / ANGLE_RANGE;
  const raw = min + ratio * (max - min);
  return Math.round(raw / step) * step;
}

/* Convert a polar (cx, cy, r, angleDeg) to cartesian. SVG y grows
   downward, so we flip the y sign relative to standard math. */
function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg - 90) * (Math.PI / 180); // -90 so 0° is 12 o'clock
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const start = polar(cx, cy, r, endDeg);
  const end = polar(cx, cy, r, startDeg);
  const sweep = endDeg - startDeg;
  const largeArc = sweep > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}

export function WindowMinutesDial({
  value,
  onChange,
  min,
  max,
  step = 1,
  defaultValue = 10,
  label = "Detection Window",
}: WindowMinutesDialProps) {
  const ref = useRef<SVGSVGElement | null>(null);
  const [dragging, setDragging] = useState(false);

  const clampedValue = Math.max(min, Math.min(max, value));
  const angle = valueToAngle(clampedValue, min, max);

  const stepBy = useCallback(
    (delta: number) => {
      const next = Math.max(min, Math.min(max, clampedValue + delta));
      if (next !== clampedValue) onChange(next);
    },
    [clampedValue, max, min, onChange],
  );

  /* Wheel — preventDefault so the surrounding scroll container does
     not steal the gesture. Shift speeds up to ±10. */
  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const mag = e.shiftKey ? 10 : step;
    stepBy(e.deltaY < 0 ? mag : -mag);
  };

  /* Arrow keys — same step + shift convention. */
  const handleKeyDown = (e: React.KeyboardEvent<SVGSVGElement>) => {
    const mag = e.shiftKey ? 10 : step;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") {
      e.preventDefault();
      stepBy(mag);
    } else if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
      e.preventDefault();
      stepBy(-mag);
    } else if (e.key === "Home") {
      e.preventDefault();
      onChange(min);
    } else if (e.key === "End") {
      e.preventDefault();
      onChange(max);
    }
  };

  /* Right-click resets to default. */
  const handleContextMenu = (e: React.MouseEvent<SVGSVGElement>) => {
    e.preventDefault();
    onChange(defaultValue);
  };

  /* Click + drag rotation. We compute the angle from the dial centre
     to the pointer and snap to the value. */
  const pointAt = (clientX: number, clientY: number): number | null => {
    const el = ref.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = clientX - cx;
    const dy = clientY - cy;
    // atan2 returns from -π to π measured from +x axis CCW. We want
    // 0° at 12 o'clock (-y axis) with CW positive. Hence add 90°.
    const deg = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
    return deg;
  };

  const handlePointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    e.preventDefault();
    (e.target as Element).setPointerCapture(e.pointerId);
    setDragging(true);
    const deg = pointAt(e.clientX, e.clientY);
    if (deg != null) onChange(angleToValue(deg, min, max, step));
  };

  const handlePointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!dragging) return;
    const deg = pointAt(e.clientX, e.clientY);
    if (deg != null) {
      const next = angleToValue(deg, min, max, step);
      if (next !== clampedValue) onChange(next);
    }
  };

  const handlePointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    setDragging(false);
    try { (e.target as Element).releasePointerCapture(e.pointerId); } catch { /* ignored */ }
  };

  /* SVG geometry. Viewport 48 × 48; centre (24, 24). */
  const SIZE = 48;
  const CX = SIZE / 2;
  const CY = SIZE / 2;
  const R_TRACK = 18;
  const R_TICK_INNER = 15;
  const R_TICK_OUTER = 18;
  const R_INDICATOR_INNER = 10;
  const R_INDICATOR_OUTER = 18;
  /* Bottom-of-track inset by 4 px keeps the active arc from touching
     the dead zone visually. */
  const trackArc = describeArc(CX, CY, R_TRACK, ANGLE_START, ANGLE_END);
  const filledArc = describeArc(CX, CY, R_TRACK, ANGLE_START, angle);
  const indicatorInner = polar(CX, CY, R_INDICATOR_INNER, angle);
  const indicatorOuter = polar(CX, CY, R_INDICATOR_OUTER, angle);

  /* Tick marks at canonical operator values (5/15/30/60). Skipped
     when out of range. */
  const tickValues = [5, 15, 30, 60].filter((v) => v >= min && v <= max);

  /* Click-to-reset hint in title. */
  const title =
    `Detector bucket size: ${clampedValue} min. ` +
    `Drag to set, wheel/arrows to step, right-click to reset to ${defaultValue} min.`;

  /* Auto-blur on Tab is the default — no extra effect needed. */
  useEffect(() => {
    /* `dragging` state is React-only; pointer capture handles the
       global move/up events so we do not attach window listeners. */
  }, [dragging]);

  return (
    <div
      data-testid="window-minutes-dial-control"
      className="flex flex-col items-center gap-1 text-xs text-text-secondary"
    >
      {label && (
        <span
          className="font-medium text-text-secondary"
          title={title}
        >
          {label}
        </span>
      )}
      <svg
        ref={ref}
        data-testid="window-minutes-dial"
        role="slider"
        tabIndex={0}
        aria-label="Detector bucket size in minutes"
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={clampedValue}
        aria-valuetext={`${clampedValue} minutes`}
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className={`shrink-0 cursor-grab ${dragging ? "cursor-grabbing" : ""} focus:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-full`}
        onWheel={handleWheel}
        onKeyDown={handleKeyDown}
        onContextMenu={handleContextMenu}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {/* Backplate — soft circle so the dial reads as a knob, not a
            ring. Catches the pointer across the whole circle. */}
        <circle cx={CX} cy={CY} r={R_TRACK + 3} className="fill-neutral-bg1" />

        {/* Track (un-filled portion of the sweep). */}
        <path d={trackArc} className="stroke-border" strokeWidth={2} fill="none" strokeLinecap="round" />

        {/* Filled arc — value indicator. Brand-coloured. */}
        <path d={filledArc} className="stroke-brand" strokeWidth={2.5} fill="none" strokeLinecap="round" />

        {/* Tick marks. */}
        {tickValues.map((v) => {
          const a = valueToAngle(v, min, max);
          const p1 = polar(CX, CY, R_TICK_INNER, a);
          const p2 = polar(CX, CY, R_TICK_OUTER, a);
          return (
            <line
              key={v}
              x1={p1.x}
              y1={p1.y}
              x2={p2.x}
              y2={p2.y}
              className="stroke-text-muted"
              strokeWidth={1}
            />
          );
        })}

        {/* Indicator notch — the pointer. */}
        <line
          x1={indicatorInner.x}
          y1={indicatorInner.y}
          x2={indicatorOuter.x}
          y2={indicatorOuter.y}
          className="stroke-brand"
          strokeWidth={2.5}
          strokeLinecap="round"
        />

        {/* Centred value label. */}
        <text
          x={CX}
          y={CY + 4}
          textAnchor="middle"
          className="fill-text-primary font-mono font-bold"
          style={{ fontSize: 11 }}
          data-testid="window-minutes-dial-value"
        >
          {clampedValue}m
        </text>
      </svg>
    </div>
  );
}
