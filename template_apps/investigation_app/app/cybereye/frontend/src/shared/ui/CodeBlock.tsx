import type { ReactNode } from "react";

type Rule = { className: string; pattern: RegExp };

/** Four languages appear in the corpus logic field, so each gets a small hand-written rule set. */
const COMMON: Rule[] = [
  { className: "tok-str", pattern: /"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g },
  { className: "tok-num", pattern: /\b\d+(?:\.\d+)?\b/g },
];

const KEYWORDS: Record<string, RegExp> = {
  kql: /\b(let|where|summarize|project|extend|join|union|order|by|asc|desc|count|make_list|min|max|between|has|has_any|contains|startswith|endswith|isnotempty|isempty|tolower|tostring|coalesce|extract|distinct|top|limit|render|datatable|ago|now|bin|and|or|not|in)\b/g,
  sigma: /\b(title|id|status|description|references|author|date|tags|logsource|detection|condition|falsepositives|level|category|product|service|selection|filter|keywords|timeframe|fields|selection_\w+|all of them|1 of them)\b/g,
  shell: /\b(if|then|else|fi|for|do|done|while|case|esac|function|return|echo|set|export|reg|add|New-Item|Get-\w+|Set-\w+|Invoke-\w+|Start-\w+|Remove-\w+|cmd|powershell|sudo|curl|wget)\b/gi,
  stix_pseudo: /\b(AND|OR|NOT|FOLLOWEDBY|LIKE|MATCHES|IN|START|STOP|WITHIN|REPEATS|TIMES)\b/g,
};

const COMMENT: Record<string, RegExp> = {
  kql: /\/\/[^\n]*/g,
  sigma: /#[^\n]*/g,
  shell: /(?:^|\s)#[^\n]*/g,
  stix_pseudo: /\/\/[^\n]*/g,
};

const LABEL: Record<string, string> = {
  kql: "KQL", sigma: "Sigma rule", shell: "Shell", stix_pseudo: "STIX pattern",
};

interface Mark { start: number; end: number; className: string }

function highlight(source: string, language: string): ReactNode[] {
  const marks: Mark[] = [];
  const claim = (start: number, end: number, className: string) => {
    if (marks.some((m) => start < m.end && end > m.start)) return;
    marks.push({ start, end, className });
  };
  const comment = COMMENT[language];
  if (comment) for (const m of source.matchAll(comment)) claim(m.index, m.index + m[0].length, "tok-comment");
  for (const rule of COMMON) for (const m of source.matchAll(rule.pattern)) claim(m.index, m.index + m[0].length, rule.className);
  const keywords = KEYWORDS[language];
  if (keywords) for (const m of source.matchAll(keywords)) claim(m.index, m.index + m[0].length, "tok-key");
  marks.sort((a, b) => a.start - b.start);

  const out: ReactNode[] = [];
  let cursor = 0;
  marks.forEach((mark, index) => {
    if (mark.start > cursor) out.push(source.slice(cursor, mark.start));
    out.push(<span key={index} className={mark.className}>{source.slice(mark.start, mark.end)}</span>);
    cursor = mark.end;
  });
  if (cursor < source.length) out.push(source.slice(cursor));
  return out;
}

interface Props {
  children: string;
  language?: string;
  caption?: string;
}

export function CodeBlock({ children, language = "", caption }: Props) {
  const lang = language.toLowerCase();
  return (
    <div className="codeblock">
      <div className="codeblock-head">
        <span className="codeblock-lang">{LABEL[lang] ?? (lang || "code")}</span>
        {caption && <span className="codeblock-caption">{caption}</span>}
      </div>
      <pre className="codeblock-body"><code>{highlight(children, lang)}</code></pre>
    </div>
  );
}
