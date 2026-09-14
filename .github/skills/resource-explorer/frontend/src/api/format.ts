/**
 * Numbers and timestamps, written the way an operator reads them.
 *
 * `sizeBytes` is the size of the underlying object, so a truncated read has to
 * say "64 KiB of 4 GiB" rather than implying the file was small.
 */

const UNITS = ["bytes", "KiB", "MiB", "GiB", "TiB"] as const;

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "unknown size";
  if (bytes < 1024) return `${String(Math.round(bytes))} bytes`;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rendered = value >= 100 ? value.toFixed(0) : value.toFixed(1);
  return `${rendered} ${UNITS[unit] ?? "bytes"}`;
}

export function formatCount(count: number, noun: string): string {
  const plural = count === 1 ? noun : `${noun}s`;
  return `${count.toLocaleString("en-US")} ${plural}`;
}

/** A truncated listing still succeeded; the count has to say both things. */
export function childCountText(count: number, truncated: boolean): string {
  const base = formatCount(count, "item");
  return truncated ? `${base} shown — more exist` : base;
}

/**
 * `observedAt` is UTC ISO-8601 at second resolution. It is shown in the
 * reader's zone with the zone named, because "13:47" with no zone is a lie
 * half the world reads wrong.
 */
export function formatObservedAt(observedAt: string): string {
  const parsed = new Date(observedAt);
  if (Number.isNaN(parsed.getTime())) return observedAt;
  const local = parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  });
  return `${local} (${observedAt})`;
}

/** How much of the underlying object actually arrived. */
export function truncationText(sizeBytes: number, truncated: boolean): string | null {
  if (!truncated) return null;
  return `Truncated. The whole object is ${formatBytes(sizeBytes)}; only the beginning was read.`;
}

/** Row samples report a row count in `sizeBytes`, not a byte count. */
export function rowSampleText(sizeBytes: number, truncated: boolean): string | null {
  if (!truncated) return null;
  return `Sampled. ${formatCount(sizeBytes, "row")} returned; the table holds more.`;
}
