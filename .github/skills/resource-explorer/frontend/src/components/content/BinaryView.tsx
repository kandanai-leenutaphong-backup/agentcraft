/**
 * Bytes that are not text, shown as the hex-and-ASCII preview the server
 * composed.
 *
 * A mojibake pane is worse than an honest hex dump, and the preview is bounded
 * at 512 bytes server-side, so the pane says how much of the object it is
 * looking at rather than implying it is the whole thing.
 */

import type { JSX } from "react";

export interface BinaryViewProps {
  text: string | null;
}

export function BinaryView({ text }: BinaryViewProps): JSX.Element {
  return (
    <div className="min-w-0">
      <p className="mb-2 text-xs text-muted">
        The preview below is the first bytes of the object, in hex and ASCII.
      </p>
      {text === null ? (
        <p className="text-sm text-secondary">
          The server returned no preview for these bytes.
        </p>
      ) : (
        <pre
          data-testid="content-binary"
          className="overflow-x-auto rounded border border-border bg-surface p-3 font-mono text-[12px] leading-5 text-primary"
        >
          {text}
        </pre>
      )}
    </div>
  );
}
