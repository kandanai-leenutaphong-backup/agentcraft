/**
 * JSON, coloured by token class.
 *
 * The server already pretty-printed it at two-space indent, so this only adds
 * colour — and stops adding it above a bound, because a 200 000-character
 * document is 50 000 spans and a frozen tab.
 */

import type { JSX } from "react";

import { MAX_HIGHLIGHT_CHARS, tokenizeJson, type JsonTokenKind } from "../../api/render";

const TOKEN_CLASS: Record<JsonTokenKind, string> = {
  key: "text-flow",
  string: "text-success",
  number: "text-warning",
  keyword: "text-group",
  punct: "text-secondary",
};

export function JsonView({ text }: { text: string }): JSX.Element {
  if (text.length > MAX_HIGHLIGHT_CHARS) {
    return (
      <div className="min-w-0">
        <p className="mb-2 text-xs text-muted">
          Syntax colouring is off above {MAX_HIGHLIGHT_CHARS.toLocaleString("en-US")}{" "}
          characters. The text below is the document as it arrived.
        </p>
        <pre
          data-testid="content-json"
          className="overflow-x-auto whitespace-pre-wrap break-words rounded border border-border bg-surface p-3 font-mono text-[12.5px] leading-5 text-primary"
        >
          {text}
        </pre>
      </div>
    );
  }

  const tokens = tokenizeJson(text);
  return (
    <pre
      data-testid="content-json"
      className="overflow-x-auto whitespace-pre-wrap break-words rounded border border-border bg-surface p-3 font-mono text-[12.5px] leading-5 text-primary"
    >
      {tokens.map((token, index) => (
        <span key={index} className={TOKEN_CLASS[token.kind]}>
          {token.text}
        </span>
      ))}
    </pre>
  );
}
