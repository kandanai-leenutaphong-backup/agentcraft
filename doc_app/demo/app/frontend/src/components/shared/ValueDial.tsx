/**
 * ValueDial — generic SVG rotary knob shared by detector controls.
 *
 * Replaces the older single-purpose window dial plus range sliders with
 * one aligned three-dial control row: Window, Max Alarms, Max SCADA.
 */

import { useCallback, useRef, useState } from "react";

interface ValueDialProps {
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  step?: number;
  defaultValue: number;
  label: string;
  formatValue: (v: number) => string;
  ticks?: readonly number[];
  size?: number;
  ariaLabel: string;
  unit?: string;
  testId?: string;
}

const ANGLE_START = -135;
const ANGLE_END = 135;
const ANGLE_RANGE = ANGLE_END - ANGLE_START;

function valueToAngle(value: number, min: number, max: number): number {
  const ratio = Math.max(0, Math.min(1, (value - min) / (max - min)));
  return ANGLE_START + ratio * ANGLE_RANGE;
}

function angleToValue(angle: number, min: number, max: number, step: number): number {
  let a = angle;
  while (a < -180) a += 360;
  while (a > 180) a -= 360;
  if (a < ANGLE_START) a = ANGLE_START;
  if (a > ANGLE_END) a = ANGLE_END;
  const ratio = (a - ANGLE_START) / ANGLE_RANGE;
  const raw = min + ratio * (max - min);
  return Math.round(raw / step) * step;
}

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg - 90) * (Math.PI / 180);
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const start = polar(cx, cy, r, endDeg);
  const end = polar(cx, cy, r, startDeg);
  const sweep = endDeg - startDeg;
  const largeArc = sweep > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}

export function ValueDial({
  value,
  onChange,
  min,
  max,
  step = 1,
  defaultValue,
  label,
  formatValue,
  ticks = [],
  size = 80,
  ariaLabel,
  unit,
  testId,
}: ValueDialProps) {
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

  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const mag = e.shiftKey ? step * 10 : step;
    stepBy(e.deltaY < 0 ? mag : -mag);
  };

  const handleKeyDown = (e: React.KeyboardEvent<SVGSVGElement>) => {
    const mag = e.shiftKey ? step * 10 : step;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") {
      e.preventDefault(); stepBy(mag);
    } else if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
      e.preventDefault(); stepBy(-mag);
    } else if (e.key === "Home") {
      e.preventDefault(); onChange(min);
    } else if (e.key === "End") {
      e.preventDefault(); onChange(max);
    } else if (e.key === "Backspace" || e.key === "Delete" || e.key.toLowerCase() === "r") {
      e.preventDefault(); onChange(defaultValue);
    }
  };

  const handleContextMenu = (e: React.MouseEvent<SVGSVGElement>) => {
    e.preventDefault();
    onChange(defaultValue);
  };

  const pointAt = (clientX: number, clientY: number): number | null => {
    const el = ref.current;
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = clientX - cx;
    const dy = clientY - cy;
    return Math.atan2(dy, dx) * (180 / Math.PI) + 90;
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

  const SIZE = size;
  const CX = SIZE / 2;
  const CY = SIZE / 2;
  const R_TRACK = SIZE * 0.40;
  const R_TICK_INNER = SIZE * 0.34;
  const R_TICK_OUTER = SIZE * 0.40;
  const R_INDICATOR_INNER = SIZE * 0.22;
  const R_INDICATOR_OUTER = SIZE * 0.40;

  const trackArc = describeArc(CX, CY, R_TRACK, ANGLE_START, ANGLE_END);
  const filledArc = describeArc(CX, CY, R_TRACK, ANGLE_START, angle);
  const indicatorInner = polar(CX, CY, R_INDICATOR_INNER, angle);
  const indicatorOuter = polar(CX, CY, R_INDICATOR_OUTER, angle);
  const tickValues = ticks.filter((v) => v >= min && v <= max);
  const gradientId = `vd-bp-${testId ?? label.replace(/\s+/g, "-").toLowerCase()}-${SIZE}`;

  const title =
    `${label}: ${formatValue(clampedValue)}. ` +
    `Drag to set; wheel/arrows to step; right-click or 'r' to reset to ${formatValue(defaultValue)}.`;

  return (
    <div
      data-testid={testId}
      className="flex flex-col items-center gap-1 text-xs text-text-secondary"
    >
      <span className="font-medium text-text-secondary tracking-wide" title={title}>
        {label}
      </span>
      <svg
        ref={ref}
        role="slider"
        tabIndex={0}
        aria-label={ariaLabel}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={clampedValue}
        aria-valuetext={formatValue(clampedValue)}
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className={`shrink-0 cursor-grab ${dragging ? "cursor-grabbing" : ""} focus:outline-none focus-visible:ring-2 focus-visible:ring-brand rounded-full transition-transform hover:scale-[1.03] active:scale-[0.98]`}
        onWheel={handleWheel}
        onKeyDown={handleKeyDown}
        onContextMenu={handleContextMenu}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <defs>
          <radialGradient id={gradientId} cx="50%" cy="40%" r="65%">
            <stop offset="0%" stopColor="rgb(var(--neutral-bg3-rgb, 28 35 47))" stopOpacity="1" />
            <stop offset="100%" stopColor="rgb(var(--neutral-bg1-rgb, 12 17 24))" stopOpacity="1" />
          </radialGradient>
        </defs>
        <circle cx={CX} cy={CY} r={R_TRACK + 3} fill={`url(#${gradientId})`} className="stroke-border" strokeWidth={1} />
        <path d={trackArc} className="stroke-border" strokeWidth={3} fill="none" strokeLinecap="round" />
        <path d={filledArc} className="stroke-brand" strokeWidth={3.5} fill="none" strokeLinecap="round" />

        {tickValues.map((tickValue) => {
          const tickAngle = valueToAngle(tickValue, min, max);
          const p1 = polar(CX, CY, R_TICK_INNER, tickAngle);
          const p2 = polar(CX, CY, R_TICK_OUTER, tickAngle);
          return (
            <line
              key={tickValue}
              x1={p1.x}
              y1={p1.y}
              x2={p2.x}
              y2={p2.y}
              className="stroke-text-muted"
              strokeWidth={1.5}
            />
          );
        })}

        <line
          x1={indicatorInner.x}
          y1={indicatorInner.y}
          x2={indicatorOuter.x}
          y2={indicatorOuter.y}
          className="stroke-brand"
          strokeWidth={3.5}
          strokeLinecap="round"
        />
        <circle cx={CX} cy={CY} r={SIZE * 0.06} className="fill-brand" />
        <text
          x={CX}
          y={unit ? CY + SIZE * 0.05 : CY + SIZE * 0.08}
          textAnchor="middle"
          className="fill-text-primary font-mono font-bold"
          style={{ fontSize: SIZE * 0.20 }}
        >
          {formatValue(clampedValue)}
        </text>
        {unit && (
          <text
            x={CX}
            y={CY + SIZE * 0.22}
            textAnchor="middle"
            className="fill-text-muted font-mono"
            style={{ fontSize: SIZE * 0.11 }}
          >
            {unit}
          </text>
        )}
      </svg>
    </div>
  );
}
