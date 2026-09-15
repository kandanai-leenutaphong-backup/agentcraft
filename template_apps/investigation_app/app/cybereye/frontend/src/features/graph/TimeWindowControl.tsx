import { useEffect, useMemo, useState } from "react";
import { Clock3, Infinity as InfinityIcon, Play, Target } from "lucide-react";

const BUCKET_MS = 15 * 60 * 1000;

export interface TimeWindow { start: string; end: string; }

interface Props {
  extentStart: string;
  extentEnd: string;
  window: TimeWindow | null;
  eventEdgeCount: number;
  followedScenario: string;
  onChange: (window: TimeWindow | null) => void;
}

const iso = (ms: number) => new Date(ms).toISOString().slice(0, 16);
const label = (ms: number) => new Date(ms).toISOString().slice(0, 16).replace("T", " ") + "Z";

/** Range control over the export's observed extent, quantised to the 15-minute bucket. */
export function TimeWindowControl({ extentStart, extentEnd, window: active, eventEdgeCount, followedScenario, onChange }: Props) {
  const floor = useMemo(() => Math.floor(Date.parse(extentStart) / BUCKET_MS) * BUCKET_MS, [extentStart]);
  const ceiling = useMemo(() => Math.ceil(Date.parse(extentEnd) / BUCKET_MS) * BUCKET_MS, [extentEnd]);
  const buckets = Math.max(1, Math.round((ceiling - floor) / BUCKET_MS));
  const [range, setRange] = useState<[number, number]>([0, buckets]);

  useEffect(() => {
    if (!active) return;
    setRange([
      Math.max(0, Math.round((Date.parse(`${active.start}:00Z`) - floor) / BUCKET_MS)),
      Math.min(buckets, Math.round((Date.parse(`${active.end}:00Z`) - floor) / BUCKET_MS)),
    ]);
  }, [active, floor, buckets]);

  if (!Number.isFinite(floor) || !Number.isFinite(ceiling)) return null;

  const emit = (next: [number, number]) => {
    setRange(next);
    onChange({ start: iso(floor + next[0] * BUCKET_MS), end: iso(floor + next[1] * BUCKET_MS) });
  };
  const move = (index: 0 | 1) => (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = Number(event.target.value);
    const next: [number, number] = index === 0
      ? [Math.min(value, range[1] - 1), range[1]]
      : [range[0], Math.max(value, range[0] + 1)];
    emit(next);
  };

  const spanHours = ((range[1] - range[0]) * BUCKET_MS) / 3_600_000;

  return (
    <section className="time-window" aria-label="Graph time window">
      <div className="time-window-head">
        <Clock3 size={13} />
        <b>{active ? "Event relationships in window" : "Structural relationships only"}</b>
        <span className="time-window-note">
          {active
            ? `${eventEdgeCount} event relationship${eventEdgeCount === 1 ? "" : "s"} fired in ${spanHours.toFixed(2)} h`
            : "Relationships that hold for the whole export, independent of time."}
        </span>
        <div className="time-window-modes">
          <button
            type="button" className={active ? "" : "on"} aria-pressed={!active}
            onClick={() => onChange(null)}
          ><InfinityIcon size={11} /> Structural</button>
          <button
            type="button" className={active ? "on" : ""} aria-pressed={!!active}
            onClick={() => emit(range[1] > range[0] ? range : [0, buckets])}
          ><Play size={11} fill="currentColor" /> Windowed</button>
        </div>
      </div>

      <div className={`time-window-track ${active ? "" : "idle"}`}>
        <div className="time-window-fill" style={{
          left: `${(range[0] / buckets) * 100}%`,
          width: `${((range[1] - range[0]) / buckets) * 100}%`,
        }} />
        <input
          type="range" min={0} max={buckets} value={range[0]} onChange={move(0)}
          aria-label="Window start" disabled={!active}
        />
        <input
          type="range" min={0} max={buckets} value={range[1]} onChange={move(1)}
          aria-label="Window end" disabled={!active}
        />
      </div>

      <div className="time-window-foot">
        <span>{label(floor + range[0] * BUCKET_MS)}</span>
        <div className="time-window-presets">
          <button type="button" onClick={() => emit([0, buckets])}>Whole export</button>
          <button
            type="button"
            onClick={() => {
              const from = Math.round((Date.parse("2026-08-13T02:30:00Z") - floor) / BUCKET_MS);
              const to = Math.round((Date.parse("2026-08-13T03:45:00Z") - floor) / BUCKET_MS);
              emit([Math.max(0, from), Math.min(buckets, to)]);
            }}
          ><Target size={10} /> Focal incident</button>
        </div>
        <span>{label(floor + range[1] * BUCKET_MS)}</span>
      </div>
      {active && <p className="time-window-caveat">
        {followedScenario && <span className="time-window-follow">Following the scanner scenario “{followedScenario}”. Move a handle to detach.</span>}
        Counts are attributed to 15-minute buckets, so a boundary mid-bucket includes the whole bucket.
      </p>}
    </section>
  );
}
