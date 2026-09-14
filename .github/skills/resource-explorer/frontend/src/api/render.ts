/**
 * JSON, tokenised for colour, and image bytes, gated before they reach a URL.
 *
 * Both are boundary work: the first bounds how much text is turned into DOM
 * nodes, the second refuses to build a `data:` URL for anything the server did
 * not type as a bitmap image.
 */

export type JsonTokenKind =
  | "key"
  | "string"
  | "number"
  | "keyword"
  | "punct";

export interface JsonToken {
  text: string;
  kind: JsonTokenKind;
}

/** Above this, the text renders unhighlighted rather than as 50 000 spans. */
export const MAX_HIGHLIGHT_CHARS = 100_000;

const SCANNER =
  /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

export function tokenizeJson(text: string): JsonToken[] {
  const tokens: JsonToken[] = [];
  let last = 0;
  SCANNER.lastIndex = 0;
  let match = SCANNER.exec(text);
  while (match !== null) {
    if (match.index > last) {
      tokens.push({ text: text.slice(last, match.index), kind: "punct" });
    }
    if (match[1] !== undefined) {
      const isKey = match[2] !== undefined;
      tokens.push({ text: match[1], kind: isKey ? "key" : "string" });
      if (isKey) tokens.push({ text: match[2] as string, kind: "punct" });
    } else if (match[3] !== undefined) {
      tokens.push({ text: match[3], kind: "keyword" });
    } else if (match[4] !== undefined) {
      tokens.push({ text: match[4], kind: "number" });
    }
    last = match.index + match[0].length;
    match = SCANNER.exec(text);
  }
  if (last < text.length) tokens.push({ text: text.slice(last), kind: "punct" });
  return tokens;
}

/**
 * Bitmap types only. `image/svg+xml` is a script-bearing document and the
 * server never types one as an image; this refuses it a second time, because a
 * rendered SVG from a storage account would run inside this origin.
 */
const RENDERABLE_IMAGE = /^image\/(png|jpeg|gif|webp|bmp|avif|x-icon)$/i;
const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;

export function imageDataUrl(mediaType: string, dataBase64: string | null): string | null {
  if (dataBase64 === null || dataBase64 === "") return null;
  const type = mediaType.split(";", 1)[0]?.trim() ?? "";
  if (!RENDERABLE_IMAGE.test(type)) return null;
  if (!BASE64.test(dataBase64)) return null;
  return `data:${type.toLowerCase()};base64,${dataBase64}`;
}
