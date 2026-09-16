import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { Check, Copy, FileCode2, WrapText } from "lucide-react";
import {
  bundledLanguages, bundledLanguagesInfo, bundledThemes,
  createHighlighterCore, createJavaScriptRegexEngine,
} from "shiki";
import type { BundledLanguage, ThemedToken } from "shiki";

export interface SourceCodeViewerProps {
  code: string;
  filename?: string;
  language?: string;
  startLine?: number;
  maxHeight?: CSSProperties["maxHeight"];
  truncated?: boolean;
  defaultWrap?: boolean;
}

type SourceToken = Pick<ThemedToken, "content" | "color" | "fontStyle">;
type Highlight = { code: string; language: string; lines: SourceToken[][] | null };
let highlighter: ReturnType<typeof createHighlighterCore> | undefined;

function languageFor(filename: string, language?: string): { id: BundledLanguage | "text"; label: string } {
  const name = filename.split(/[\\/]/).pop()?.toLowerCase() ?? "";
  const candidate = language?.trim().toLowerCase() || name.split(".").pop();
  const known = bundledLanguagesInfo.find((entry) => entry.id === candidate || entry.aliases?.includes(candidate ?? ""));
  const id = known && Object.hasOwn(bundledLanguages, known.id) ? known.id as BundledLanguage : "text";
  return { id, label: known?.name ?? "Plain text" };
}

function tokenStyle(token: SourceToken): CSSProperties {
  const flags = Math.max(0, token.fontStyle ?? 0);
  return {
    color: token.color,
    fontStyle: flags & 1 ? "italic" : undefined,
    fontWeight: flags & 2 ? "bold" : undefined,
    textDecoration: flags & 4 ? "underline" : undefined,
  };
}

export function SourceCodeViewer({ code, filename = "", language, startLine = 1,
  maxHeight = 480, truncated = false, defaultWrap = false }: SourceCodeViewerProps) {
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [wrap, setWrap] = useState(defaultWrap);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [copyError, setCopyError] = useState(false);
  const { id: languageId, label } = languageFor(filename, language);
  const current = highlight?.code === code && highlight.language === languageId ? highlight : null;
  const lines = current?.lines ?? code.split(/\r\n|\r|\n/).map((content) => [{ content }]);
  const firstLine = Number.isFinite(startLine) ? Math.max(1, Math.floor(startLine)) : 1;
  const copied = copiedCode === code;

  useEffect(() => {
    if (languageId === "text") return;
    let cancelled = false;
    highlighter ??= createHighlighterCore({
      themes: [bundledThemes["dark-plus"]], langs: [], engine: createJavaScriptRegexEngine(),
    });
    highlighter.then(async (engine) => {
      await engine.loadLanguage(bundledLanguages[languageId]);
      return engine.codeToTokens(code, { lang: languageId, theme: "dark-plus" }).tokens;
    }).then((tokens) => {
      if (!cancelled) setHighlight({ code, language: languageId, lines: tokens });
    }).catch(() => {
      if (!cancelled) setHighlight({ code, language: languageId, lines: null });
    });
    return () => { cancelled = true; };
  }, [code, languageId]);

  async function copySource() {
    setCopyError(false);
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
    } catch {
      setCopyError(true);
    }
  }

  return <div className="scv" data-language={languageId} data-highlighted={Boolean(current?.lines)}>
    <div className="scv-toolbar">
      <FileCode2 size={15} aria-hidden="true" />
      <code className="scv-filename" title={filename}>{filename || "Source"}</code>
      <span className="scv-language">{current?.lines === null ? "Plain text" : label}</span>
      <div className="scv-actions">
        <button type="button" aria-label="Wrap lines" title="Wrap lines" aria-pressed={wrap}
                onClick={() => setWrap((value) => !value)}><WrapText size={16} /></button>
        <button type="button" aria-label={copied ? "Copied source code" : "Copy source code"}
                title={copied ? "Copied" : "Copy source code"} onClick={() => void copySource()}>
          {copied ? <Check size={15} /> : <Copy size={15} />}
        </button>
      </div>
    </div>
    {copyError && <div className="scv-error" role="alert">Could not copy source code.</div>}
    <pre className={`scv-code${wrap ? " scv-wrap" : ""}`} style={{ maxHeight }} tabIndex={0}
         aria-label={`${filename || "Source"} code`} aria-busy={languageId !== "text" && !current}>
      <code>{lines.map((tokens, lineIndex) => <span className="scv-line" key={lineIndex}>
        <span className="scv-line-number" aria-hidden="true">{firstLine + lineIndex}</span>
        <span className="scv-line-content">{tokens.map((token, tokenIndex) =>
          <span className="scv-token" key={tokenIndex} style={tokenStyle(token)}>{token.content}</span>)}</span>
      </span>)}</code>
    </pre>
    <div className="scv-status"><span>{lines.length} {lines.length === 1 ? "line" : "lines"}</span>
      <span>{truncated ? "Truncated preview" : "Read-only"}</span>
    </div>
  </div>;
}