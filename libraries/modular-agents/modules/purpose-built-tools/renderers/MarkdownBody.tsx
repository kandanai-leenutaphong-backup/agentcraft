/**
 * MarkdownBody — a small, safe markdown renderer for retrieved documents.
 *
 * WHY NOT A MARKDOWN LIBRARY
 * --------------------------
 * The box has no dependencies and this is not where that changes. A knowledge
 * base returns headings, emphasis, code, lists, links and quotes; that subset
 * is a hundred lines of parsing and covers what retrieved prose actually
 * contains.
 *
 * WHY IT BUILDS ELEMENTS RATHER THAN HTML
 * ---------------------------------------
 * There is no `dangerouslySetInnerHTML` here and there must never be one. The
 * text being rendered came out of a search index — that is, out of data, which
 * is to say out of somewhere an attacker may have been able to write. Every
 * output is a React element built from parsed text, so a document containing
 * `<script>` renders those characters and does not execute them.
 *
 * Link targets are checked for scheme: `javascript:` and `data:` URLs are
 * rendered as plain text, because a link is the one construct in markdown that
 * can carry executable intent.
 */

import type { ReactNode } from "react";

/** Schemes a link may use. Anything else renders as text, not as an anchor. */
const SAFE_LINK = /^(https?:|mailto:|#|\/)/i;

const BULLET = /^\s*[-*+]\s+(.*)$/;
const ORDERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^(#{1,6})\s+(.*)$/;
const QUOTE = /^>\s?(.*)$/;
const FENCE = /^```/;
const RULE = /^(-{3,}|\*{3,}|_{3,})\s*$/;
// A pipe table. Models emit these constantly whether or not you asked for one,
// and without support the whole table collapses into a line of pipes.
const TABLE_ROW = /^\s*\|(.+)\|\s*$/;
const TABLE_RULE = /^\s*\|[\s:|-]+\|\s*$/;

/** Inline spans, longest-delimiter first so `**` wins over `*`. */
const INLINE = /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_|\[[^\]]+\]\([^)]+\))/;

/** Split a pipe-table row into its cells. */
function tableCells(line: string): string[] {
  const inner = TABLE_ROW.exec(line)?.[1] ?? "";
  return inner.split("|").map((cell) => cell.trim());
}

/** Render one line's inline markup into elements. */
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(INLINE).filter((part) => part !== "" && part !== undefined);
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;

    if (part.startsWith("`") && part.endsWith("`") && part.length > 1) {
      return (
        <code key={key} className="rounded bg-neutral-bg3 px-1 font-mono text-micro">
          {part.slice(1, -1)}
        </code>
      );
    }
    if ((part.startsWith("**") && part.endsWith("**")) || (part.startsWith("__") && part.endsWith("__"))) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"))) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }

    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      const [, label, href] = link;
      if (!SAFE_LINK.test(href.trim())) {
        // A javascript: or data: target. Show the text; do not make it clickable.
        return <span key={key}>{label}</span>;
      }
      return (
        <a
          key={key}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent underline underline-offset-2"
        >
          {label}
        </a>
      );
    }

    return <span key={key}>{part}</span>;
  });
}

const HEADING_CLASS: Record<number, string> = {
  1: "mt-3 text-sm font-semibold text-text-primary",
  2: "mt-3 text-xs font-semibold text-text-primary",
  3: "mt-2 text-xs font-semibold text-text-secondary",
  4: "mt-2 text-micro font-semibold text-text-secondary",
  5: "mt-2 text-micro font-semibold text-text-muted",
  6: "mt-2 text-micro font-semibold text-text-muted",
};

export interface MarkdownBodyProps {
  children: string;
  /** Test hook and styling escape hatch. */
  className?: string;
}

/** Render a markdown string as elements. Never returns raw HTML. */
export function MarkdownBody({ children, className }: MarkdownBodyProps) {
  const lines = (children ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];

  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let quote: string[] = [];
  let fence: { language: string; lines: string[] } | null = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p-${blocks.length}`} className="mt-2 leading-relaxed">
        {renderInline(paragraph.join(" "), `p${blocks.length}`)}
      </p>,
    );
    paragraph = [];
  };
  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag
        key={`l-${blocks.length}`}
        className={`mt-2 space-y-0.5 pl-4 ${list.ordered ? "list-decimal" : "list-disc"}`}
      >
        {list.items.map((item, index) => (
          <li key={index}>{renderInline(item, `l${blocks.length}-${index}`)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };
  const flushQuote = () => {
    if (!quote.length) return;
    blocks.push(
      <blockquote
        key={`q-${blocks.length}`}
        className="mt-2 border-l-2 border-neutral-border pl-2 italic text-text-muted"
      >
        {renderInline(quote.join(" "), `q${blocks.length}`)}
      </blockquote>,
    );
    quote = [];
  };
  const flushAll = () => {
    flushParagraph();
    flushList();
    flushQuote();
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];

    // A table is a header row, a separator, then rows. Detected by looking one
    // line ahead: a lone pipe line is not a table and must stay a paragraph.
    if (!fence && TABLE_ROW.test(line) && TABLE_RULE.test(lines[index + 1] ?? "")) {
      flushAll();
      const headers = tableCells(line);
      const rows: string[][] = [];
      let cursor = index + 2;
      while (cursor < lines.length && TABLE_ROW.test(lines[cursor])) {
        rows.push(tableCells(lines[cursor]));
        cursor += 1;
      }
      index = cursor - 1;
      blocks.push(
        <div key={`t-${blocks.length}`} className="mt-2 overflow-x-auto">
          <table className="w-full border-collapse text-micro">
            <thead>
              <tr>
                {headers.map((header, column) => (
                  <th key={column} className="border-b border-border px-2 py-1 text-left font-semibold text-text-muted">
                    {renderInline(header, `th${blocks.length}-${column}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="even:bg-neutral-bg2/30">
                  {headers.map((_, column) => (
                    <td key={column} className="px-2 py-1 align-top">
                      {renderInline(row[column] ?? "", `td${blocks.length}-${rowIndex}-${column}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    // A fenced block swallows everything until its closing fence, so markup
    // inside a code sample is shown, not interpreted.
    if (fence) {
      if (FENCE.test(line)) {
        blocks.push(
          <pre
            key={`c-${blocks.length}`}
            data-language={fence.language || undefined}
            className="mt-2 overflow-x-auto rounded bg-neutral-bg3 p-2 font-mono text-micro"
          >
            {fence.lines.join("\n")}
          </pre>,
        );
        fence = null;
      } else {
        fence.lines.push(line);
      }
      continue;
    }
    if (FENCE.test(line)) {
      flushAll();
      fence = { language: line.replace(/^```/, "").trim(), lines: [] };
      continue;
    }

    if (!line.trim()) {
      flushAll();
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      flushAll();
      const level = heading[1].length;
      const Tag = `h${Math.min(level, 6)}` as "h1";
      blocks.push(
        <Tag key={`h-${blocks.length}`} className={HEADING_CLASS[level] ?? HEADING_CLASS[6]}>
          {renderInline(heading[2], `h${blocks.length}`)}
        </Tag>,
      );
      continue;
    }

    if (RULE.test(line)) {
      flushAll();
      blocks.push(<hr key={`r-${blocks.length}`} className="mt-3 border-neutral-border" />);
      continue;
    }

    const quoted = QUOTE.exec(line);
    if (quoted) {
      flushParagraph();
      flushList();
      quote.push(quoted[1]);
      continue;
    }

    const bullet = BULLET.exec(line);
    const ordered = ORDERED.exec(line);
    if (bullet || ordered) {
      flushParagraph();
      flushQuote();
      const isOrdered = Boolean(ordered);
      if (!list || list.ordered !== isOrdered) {
        flushList();
        list = { ordered: isOrdered, items: [] };
      }
      list.items.push((bullet ?? ordered)![1]);
      continue;
    }

    // Lazy continuation: a wrapped list item keeps going on the next line.
    // Without this, a soft-wrapped bullet ends the list and the remainder
    // becomes a stray paragraph — the list visibly splits in two.
    if (list && list.items.length && /^\s+\S/.test(line)) {
      list.items[list.items.length - 1] += ` ${line.trim()}`;
      continue;
    }

    flushList();
    flushQuote();
    paragraph.push(line.trim());
  }

  // An unterminated fence still has to render: dropping it would hide content.
  if (fence) {
    blocks.push(
      <pre key={`c-${blocks.length}`} className="mt-2 overflow-x-auto rounded bg-neutral-bg3 p-2 font-mono text-micro">
        {fence.lines.join("\n")}
      </pre>,
    );
  }
  flushAll();

  return (
    <div data-testid="markdown-body" className={className ?? "text-xs text-text-secondary"}>
      {blocks}
    </div>
  );
}
