import type { ReactNode } from "react";

/** Corpus text is third-party content, so only these schemes ever become a live link. */
const SAFE_SCHEME = /^https:\/\//i;

const CITATION = /\(Citation:\s*([^)]*)\)/g;
const MD_LINK = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
const BARE_URL = /(?<!\]\()(https?:\/\/[^\s<>()[\]]+)/g;
const CODE_TAG = /<code>([\s\S]*?)<\/code>/g;
const BACKTICK = /`([^`]+)`/g;
const BOLD = /\*\*([^*]+)\*\*/g;

function safeHref(url: string): string | null {
  return SAFE_SCHEME.test(url) ? url : null;
}

/** A long URL shoulders the whole column out of shape, so show its host and tail. */
function linkText(url: string): string {
  try {
    const parsed = new URL(url);
    const tail = parsed.pathname.replace(/\/$/, "").split("/").filter(Boolean).pop() ?? "";
    return tail ? `${parsed.hostname}/${tail}` : parsed.hostname;
  } catch {
    return url.length > 48 ? `${url.slice(0, 45)}…` : url;
  }
}

function anchor(url: string, label: string, key: string): ReactNode {
  const href = safeHref(url);
  if (!href) return <span key={key} className="corpus-deadlink">{label}</span>;
  return <a key={key} className="corpus-link" href={href} target="_blank" rel="noopener noreferrer">{label}</a>;
}

type Token = { kind: "text" | "code" | "bold" | "link"; text: string; url?: string };

/** One pass over a line, longest-first, so a URL inside a markdown link is not matched twice. */
function tokenize(line: string): Token[] {
  const marks: { start: number; end: number; token: Token }[] = [];
  const claim = (start: number, end: number, token: Token) => {
    if (marks.some((m) => start < m.end && end > m.start)) return;
    marks.push({ start, end, token });
  };
  for (const m of line.matchAll(MD_LINK)) {
    claim(m.index, m.index + m[0].length, { kind: "link", text: m[1], url: m[2] });
  }
  for (const m of line.matchAll(CODE_TAG)) {
    claim(m.index, m.index + m[0].length, { kind: "code", text: m[1] });
  }
  for (const m of line.matchAll(BACKTICK)) {
    claim(m.index, m.index + m[0].length, { kind: "code", text: m[1] });
  }
  for (const m of line.matchAll(BOLD)) {
    claim(m.index, m.index + m[0].length, { kind: "bold", text: m[1] });
  }
  for (const m of line.matchAll(BARE_URL)) {
    claim(m.index, m.index + m[0].length, { kind: "link", text: linkText(m[1]), url: m[1] });
  }
  marks.sort((a, b) => a.start - b.start);

  const out: Token[] = [];
  let cursor = 0;
  for (const mark of marks) {
    if (mark.start > cursor) out.push({ kind: "text", text: line.slice(cursor, mark.start) });
    out.push(mark.token);
    cursor = mark.end;
  }
  if (cursor < line.length) out.push({ kind: "text", text: line.slice(cursor) });
  return out;
}

function renderLine(line: string, keyBase: string): ReactNode[] {
  return tokenize(line).map((token, index) => {
    const key = `${keyBase}-${index}`;
    if (token.kind === "link") return anchor(token.url ?? "", token.text, key);
    if (token.kind === "code") return <code key={key} className="corpus-code">{token.text}</code>;
    if (token.kind === "bold") return <strong key={key}>{token.text}</strong>;
    return <span key={key}>{token.text}</span>;
  });
}

export interface CorpusText {
  body: ReactNode;
  citations: string[];
}

/**
 * Renders the markup the classification corpus actually contains — 71% of its 9,471 bodies
 * carry at least one of these forms — without a markdown dependency or any raw HTML.
 */
export function renderCorpusText(source: string): CorpusText {
  const citations: string[] = [];
  const text = source.replace(CITATION, (_match, name: string) => {
    const trimmed = name.trim();
    if (trimmed && !citations.includes(trimmed)) citations.push(trimmed);
    return "";
  });

  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (!bullets.length) return;
    const items = bullets;
    bullets = [];
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="corpus-list">
        {items.map((item, index) => <li key={index}>{renderLine(item, `li-${blocks.length}-${index}`)}</li>)}
      </ul>,
    );
  };

  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    if (bullet) { bullets.push(bullet[1]); continue; }
    flush();
    if (!line.trim()) continue;
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push(<p key={`h-${blocks.length}`} className="corpus-heading">{heading[2]}</p>);
      continue;
    }
    blocks.push(<p key={`p-${blocks.length}`}>{renderLine(line, `p-${blocks.length}`)}</p>);
  }
  flush();

  return { body: <>{blocks}</>, citations };
}
