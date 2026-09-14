/**
 * Plain text, as it arrived.
 *
 * Wrapped rather than scrolled sideways: a log line or a 200 000-character
 * blob that needs a horizontal scrollbar to be read is not being shown.
 */

import type { JSX } from "react";

export function TextView({ text }: { text: string }): JSX.Element {
  return (
    <pre
      data-testid="content-text"
      className="overflow-x-auto whitespace-pre-wrap break-words rounded border border-border bg-surface p-3 font-mono text-[12.5px] leading-5 text-primary"
    >
      {text}
    </pre>
  );
}
