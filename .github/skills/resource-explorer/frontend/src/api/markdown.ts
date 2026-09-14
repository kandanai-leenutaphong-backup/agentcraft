/**
 * A markdown subset, parsed to a tree the renderer turns into React elements.
 *
 * Deliberately not an HTML pipeline. The bytes being rendered came out of a
 * storage account, and `dangerouslySetInnerHTML` on operator-supplied content
 * inside this app's own origin is a stored-XSS surface — the same reason the
 * server refuses to type `image/svg+xml` as an image. Raw HTML in the source
 * is shown as the text it is.
 */

export type Inline =
  | { type: "text"; value: string }
  | { type: "code"; value: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "link"; href: string; children: Inline[] };

export type Block =
  | { type: "heading"; level: number; children: Inline[] }
  | { type: "paragraph"; children: Inline[] }
  | { type: "code"; lang: string | null; value: string }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "quote"; children: Inline[][] }
  | { type: "rule" }
  | { type: "table"; header: Inline[][]; rows: Inline[][][] };

const SAFE_SCHEMES = ["http:", "https:", "mailto:"];

/** A link this surface will follow, or null — in which case it renders as text. */
export function safeHref(href: string): string | null {
  const trimmed = href.trim();
  if (trimmed === "") return null;
  try {
    const parsed = new URL(trimmed);
    return SAFE_SCHEMES.includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(__[^_]+__)|(\*[^*]+\*)|(_[^_]+_)|(\[[^\]]*\]\([^)\s]+\))|(<https?:\/\/[^>\s]+>)/;

export function parseInline(source: string): Inline[] {
  const out: Inline[] = [];
  let rest = source;
  while (rest.length > 0) {
    const match = INLINE.exec(rest);
    if (match === null || match.index === undefined) {
      out.push({ type: "text", value: rest });
      break;
    }
    if (match.index > 0) out.push({ type: "text", value: rest.slice(0, match.index) });
    const token = match[0];
    if (token.startsWith("`")) {
      out.push({ type: "code", value: token.slice(1, -1) });
    } else if (token.startsWith("**") || token.startsWith("__")) {
      out.push({ type: "strong", children: parseInline(token.slice(2, -2)) });
    } else if (token.startsWith("[")) {
      const split = token.indexOf("](");
      const text = token.slice(1, split);
      const href = safeHref(token.slice(split + 2, -1));
      if (href === null) out.push({ type: "text", value: token });
      else out.push({ type: "link", href, children: parseInline(text) });
    } else if (token.startsWith("<")) {
      const href = safeHref(token.slice(1, -1));
      if (href === null) out.push({ type: "text", value: token });
      else out.push({ type: "link", href, children: [{ type: "text", value: href }] });
    } else {
      out.push({ type: "em", children: parseInline(token.slice(1, -1)) });
    }
    rest = rest.slice(match.index + token.length);
  }
  return out.filter((node) => node.type !== "text" || node.value !== "");
}

function splitRow(line: string): string[] {
  return line
    .replace(/^\s*\|/, "")
    .replace(/\|\s*$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isDivider(line: string): boolean {
  return /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
}

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? "";

    if (line.trim() === "") {
      index += 1;
      continue;
    }

    const fence = /^\s*```\s*([\w+-]*)\s*$/.exec(line);
    if (fence !== null) {
      const lang = fence[1] === undefined || fence[1] === "" ? null : fence[1];
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^\s*```/.test(lines[index] ?? "")) {
        body.push(lines[index] ?? "");
        index += 1;
      }
      index += 1;
      blocks.push({ type: "code", lang, value: body.join("\n") });
      continue;
    }

    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push({ type: "rule" });
      index += 1;
      continue;
    }

    const heading = /^\s{0,3}(#{1,6})\s+(.*)$/.exec(line);
    if (heading !== null) {
      blocks.push({
        type: "heading",
        level: (heading[1] ?? "#").length,
        children: parseInline((heading[2] ?? "").trim()),
      });
      index += 1;
      continue;
    }

    if (line.includes("|") && isDivider(lines[index + 1] ?? "")) {
      const header = splitRow(line).map(parseInline);
      index += 2;
      const rows: Inline[][][] = [];
      while (index < lines.length && (lines[index] ?? "").includes("|")) {
        rows.push(splitRow(lines[index] ?? "").map(parseInline));
        index += 1;
      }
      blocks.push({ type: "table", header, rows });
      continue;
    }

    if (/^\s*>/.test(line)) {
      const quoted: Inline[][] = [];
      while (index < lines.length && /^\s*>/.test(lines[index] ?? "")) {
        quoted.push(parseInline((lines[index] ?? "").replace(/^\s*>\s?/, "")));
        index += 1;
      }
      blocks.push({ type: "quote", children: quoted });
      continue;
    }

    const bullet = /^\s*([-*+])\s+(.*)$/.exec(line);
    const numbered = /^\s*(\d+)[.)]\s+(.*)$/.exec(line);
    if (bullet !== null || numbered !== null) {
      const ordered = numbered !== null;
      const items: Inline[][] = [];
      while (index < lines.length) {
        const current = lines[index] ?? "";
        const next = ordered
          ? /^\s*\d+[.)]\s+(.*)$/.exec(current)
          : /^\s*[-*+]\s+(.*)$/.exec(current);
        if (next === null) break;
        items.push(parseInline((next[1] ?? "").trim()));
        index += 1;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length) {
      const current = lines[index] ?? "";
      if (
        current.trim() === "" ||
        /^\s*```/.test(current) ||
        /^\s{0,3}#{1,6}\s+/.test(current) ||
        /^\s*([-*+]|\d+[.)])\s+/.test(current) ||
        /^\s*>/.test(current)
      ) {
        break;
      }
      paragraph.push(current.trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", children: parseInline(paragraph.join(" ")) });
  }

  return blocks;
}
