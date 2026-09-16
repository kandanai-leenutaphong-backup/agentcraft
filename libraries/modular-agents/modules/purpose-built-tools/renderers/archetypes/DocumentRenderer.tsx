/**
 * DocumentRenderer — one document's text, given room to be read.
 *
 * Accepts `{title?, document|text|content|body}` or a bare string. A payload
 * that parsed to an object but carries no recognised text field is
 * *unresolved*, not a document: dumping the object would be the raw-JSON
 * fallback wearing a different hat.
 *
 * The body renders through `MarkdownBody`, a small safe subset renderer that
 * builds elements rather than HTML — retrieved prose is data, and data is
 * somewhere an attacker may have written. Plain text renders unchanged through
 * the same path.
 *
 * A different renderer can still be supplied, for a consumer that already has
 * a full markdown stack:
 *
 *   <DocumentRenderer result={r} renderBody={(md) => <Markdown>{md}</Markdown>} />
 */

import type { ReactNode } from "react";
import { ToolResultCard } from "../ToolResultCard";
import { MarkdownBody } from "../MarkdownBody";
import { parseToolResult } from "../helpers";
import {
  ArchetypeEmpty,
  ArchetypeUnresolved,
  renderEnvelopeState,
  type ArchetypeRendererProps,
} from "./_common";

const TEXT_FIELDS = ["document", "text", "content", "body"] as const;

export interface DocumentRendererProps extends ArchetypeRendererProps {
  /** Render the body yourself — a markdown component, typically. */
  renderBody?: (body: string) => ReactNode;
}

export function DocumentRenderer({ resizeKey, result, renderBody }: DocumentRendererProps) {
  const parsed = parseToolResult<Record<string, unknown>>(result);

  if (parsed) {
    const envelopeState = renderEnvelopeState(parsed);
    if (envelopeState) return envelopeState;
  }

  let body: string | null = null;
  let title: string | null = null;

  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    for (const field of TEXT_FIELDS) {
      if (typeof parsed[field] === "string") {
        body = parsed[field] as string;
        break;
      }
    }
    if (typeof parsed.title === "string") title = parsed.title;
    if (body === null) return <ArchetypeUnresolved archetype="document" result={result} />;
  } else {
    // Did not parse as JSON: the legitimate plain-text document path.
    body = result;
  }

  if (!body.trim()) {
    return (
      <ArchetypeEmpty
        label="chars"
        message="Empty document"
        scope={title ? [{ label: "doc", value: title }] : undefined}
      />
    );
  }

  return (
    <ToolResultCard resizeKey={resizeKey} scope={title ? [{ label: "doc", value: title }] : undefined}>
      <div className="max-h-72 overflow-y-auto text-xs text-text-secondary">
        {renderBody ? renderBody(body) : <MarkdownBody>{body}</MarkdownBody>}
      </div>
    </ToolResultCard>
  );
}
