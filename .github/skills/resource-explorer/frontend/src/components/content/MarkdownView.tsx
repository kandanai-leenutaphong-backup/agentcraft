/**
 * Markdown, rendered as React elements from a parsed tree.
 *
 * There is no `dangerouslySetInnerHTML` on this path and there must never be
 * one: these bytes came from a storage account an operator can write to, and
 * running them as HTML inside this origin would be stored XSS. Links are
 * limited to http, https and mailto; anything else stays as text.
 */

import type { JSX } from "react";

import { parseMarkdown, type Block, type Inline } from "../../api/markdown";

function renderInline(nodes: Inline[]): JSX.Element[] {
  return nodes.map((node, index) => {
    switch (node.type) {
      case "text":
        return <span key={index}>{node.value}</span>;
      case "code":
        return (
          <code
            key={index}
            className="rounded border border-border-soft bg-surface px-1 py-px font-mono text-[12.5px]"
          >
            {node.value}
          </code>
        );
      case "strong":
        return (
          <strong key={index} className="font-semibold">
            {renderInline(node.children)}
          </strong>
        );
      case "em":
        return (
          <em key={index} className="italic">
            {renderInline(node.children)}
          </em>
        );
      case "link":
        return (
          <a
            key={index}
            href={node.href}
            target="_blank"
            rel="noreferrer noopener"
            className="text-flow underline underline-offset-2"
          >
            {renderInline(node.children)}
          </a>
        );
    }
  });
}

const HEADING_CLASS = [
  "text-xl font-semibold",
  "text-lg font-semibold",
  "text-base font-semibold",
  "text-sm font-semibold",
  "text-sm font-semibold",
  "text-sm font-semibold",
];

function renderBlock(block: Block, key: number): JSX.Element {
  switch (block.type) {
    case "heading": {
      const level = Math.min(Math.max(block.level, 1), 6);
      const Tag = `h${String(level)}` as "h1";
      return (
        <Tag key={key} className={`mt-4 text-primary ${HEADING_CLASS[level - 1] ?? ""}`}>
          {renderInline(block.children)}
        </Tag>
      );
    }
    case "paragraph":
      return (
        <p key={key} className="mt-3 text-[14px] leading-6 text-secondary">
          {renderInline(block.children)}
        </p>
      );
    case "code":
      return (
        <pre
          key={key}
          className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded border border-border bg-surface p-3 font-mono text-[12.5px] leading-5 text-primary"
        >
          {block.value}
        </pre>
      );
    case "list":
      return block.ordered ? (
        <ol key={key} className="mt-3 list-decimal space-y-1 pl-6 text-[14px] leading-6 text-secondary">
          {block.items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ol>
      ) : (
        <ul key={key} className="mt-3 list-disc space-y-1 pl-6 text-[14px] leading-6 text-secondary">
          {block.items.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ul>
      );
    case "quote":
      return (
        <blockquote
          key={key}
          className="mt-3 border-l-2 border-group pl-3 text-[14px] leading-6 text-secondary"
        >
          {block.children.map((line, index) => (
            <p key={index}>{renderInline(line)}</p>
          ))}
        </blockquote>
      );
    case "rule":
      return <hr key={key} className="mt-4 border-border" />;
    case "table":
      return (
        <div key={key} className="mt-3 max-w-full overflow-x-auto rounded border border-border">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="bg-surface2">
                {block.header.map((cell, index) => (
                  <th
                    key={index}
                    scope="col"
                    className="border-b border-border px-3 py-2 font-semibold text-secondary"
                  >
                    {renderInline(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-b border-border-soft">
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex} className="px-3 py-2 text-primary">
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}

export function MarkdownView({ text }: { text: string }): JSX.Element {
  const blocks = parseMarkdown(text);
  return (
    <div
      data-testid="content-markdown"
      className="min-w-0 rounded border border-border bg-canvas2 px-4 py-2 pb-4"
    >
      {blocks.map(renderBlock)}
    </div>
  );
}
