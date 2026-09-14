/**
 * The contents half of the request: eight content kinds, each rendered as the
 * thing it is rather than as a JSON blob with the payload quoted inside it.
 *
 * `sizeBytes` is the size of the underlying object, so a truncated read says
 * how much of it arrived instead of implying the object is small. Exactly one
 * of `text`, `dataBase64` and `rows` carries the payload, named by
 * `contentKind`; a kind whose carrier is missing says so rather than rendering
 * blank.
 */

import { useState, type JSX } from "react";

import { formatBytes, formatCount, rowSampleText, truncationText } from "../../api/format";
import { toDelimitedTable } from "../../api/delimited";
import { answered, CONTENT_KIND_LABEL, LOADING_LABEL } from "../../api/status";
import type { ContentResponse } from "../../api/wire";
import { StatusNote, TruncationNote } from "../StatusNote";
import { BinaryView } from "./BinaryView";
import { ImageView } from "./ImageView";
import { JsonView } from "./JsonView";
import { MarkdownView } from "./MarkdownView";
import { RowsTable } from "./RowsTable";
import { TextView } from "./TextView";

export interface ContentViewProps {
  content: ContentResponse | null;
  loading: boolean;
  failure: string | null;
  hasContent: boolean;
  onRetry: () => void;
}

export function ContentView({
  content,
  loading,
  failure,
  hasContent,
  onRetry,
}: ContentViewProps): JSX.Element {
  if (!hasContent) {
    return (
      <p data-testid="content-none" className="text-sm text-secondary">
        This node has no contents of its own. Open it in the tree to see what is
        underneath it.
      </p>
    );
  }
  if (failure !== null) {
    return (
      <div className="rounded border border-critical bg-critical-tint px-3 py-2">
        <p data-testid="content-failure" className="text-sm text-critical">
          {failure}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 min-h-[44px] rounded border border-border px-3 text-sm text-primary"
        >
          Try again
        </button>
      </div>
    );
  }
  if (content === null) {
    return (
      <p data-testid="content-loading" className="text-sm text-secondary">
        {loading ? `${LOADING_LABEL} reading these contents.` : "Contents not read yet."}
      </p>
    );
  }
  if (!answered(content.status)) {
    return (
      <StatusNote
        status={content.status}
        error={content.error}
        action="read these contents"
        testId="content-note"
      />
    );
  }

  const isRows = content.contentKind === "rows";
  const truncation = isRows
    ? rowSampleText(content.sizeBytes, content.truncated)
    : truncationText(content.sizeBytes, content.truncated);

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p
        data-testid="content-facts"
        data-content-kind={content.contentKind}
        className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted"
      >
        <span className="font-semibold uppercase tracking-wide text-secondary">
          {CONTENT_KIND_LABEL[content.contentKind]}
        </span>
        <span className="font-mono">{content.mediaType}</span>
        <span>
          {isRows
            ? formatCount(content.sizeBytes, "row")
            : `${formatBytes(content.sizeBytes)} underlying`}
        </span>
      </p>
      {truncation === null ? null : <TruncationNote>{truncation}</TruncationNote>}
      <ContentBody content={content} />
    </div>
  );
}

function MissingCarrier({ kind }: { kind: string }): JSX.Element {
  return (
    <p
      data-testid="content-missing"
      className="rounded border border-warning bg-warning-tint px-3 py-2 text-sm text-warning"
    >
      The server typed these contents as {kind} but sent no payload for that kind.
    </p>
  );
}

function ContentBody({ content }: { content: ContentResponse }): JSX.Element {
  switch (content.contentKind) {
    case "none":
      return (
        <p data-testid="content-empty" className="text-sm text-secondary">
          The call succeeded and there are no contents to show.
        </p>
      );
    case "text":
      return content.text === null ? (
        <MissingCarrier kind="text" />
      ) : (
        <TextView text={content.text} />
      );
    case "json":
      return content.text === null ? (
        <MissingCarrier kind="JSON" />
      ) : (
        <JsonView text={content.text} />
      );
    case "markdown":
      return content.text === null ? (
        <MissingCarrier kind="markdown" />
      ) : (
        <MarkdownBody text={content.text} />
      );
    case "csv":
      return content.text === null ? (
        <MissingCarrier kind="delimited text" />
      ) : (
        <DelimitedBody text={content.text} mediaType={content.mediaType} />
      );
    case "image":
      return (
        <ImageView
          mediaType={content.mediaType}
          dataBase64={content.dataBase64}
          label={content.label}
        />
      );
    case "binary":
      return <BinaryView text={content.text} />;
    case "rows":
      return content.rows === null ? (
        <MissingCarrier kind="rows" />
      ) : (
        <RowsTable
          rows={content.rows}
          columns={content.columns}
          caption={`Sampled rows from ${content.label}`}
        />
      );
  }
}

function Toggle({
  options,
  value,
  onChange,
  label,
}: {
  options: readonly string[];
  value: string;
  onChange: (next: string) => void;
  label: string;
}): JSX.Element {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex overflow-hidden rounded border border-border"
    >
      {options.map((option) => (
        <button
          key={option}
          type="button"
          data-testid="view-toggle"
          data-option={option}
          aria-pressed={option === value}
          onClick={() => onChange(option)}
          className={`min-h-[44px] px-3 text-[13px] ${
            option === value ? "bg-surface2 text-primary" : "text-secondary"
          }`}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

const MARKDOWN_VIEWS = ["Rendered", "Source"] as const;

function MarkdownBody({ text }: { text: string }): JSX.Element {
  const [view, setView] = useState<string>(MARKDOWN_VIEWS[0]);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Toggle
        options={MARKDOWN_VIEWS}
        value={view}
        onChange={setView}
        label="Markdown view"
      />
      {view === "Source" ? <TextView text={text} /> : <MarkdownView text={text} />}
    </div>
  );
}

const DELIMITED_VIEWS = ["Table", "Raw text"] as const;

function DelimitedBody({
  text,
  mediaType,
}: {
  text: string;
  mediaType: string;
}): JSX.Element {
  const [view, setView] = useState<string>(DELIMITED_VIEWS[0]);
  const table = toDelimitedTable(text, mediaType);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Toggle
        options={DELIMITED_VIEWS}
        value={view}
        onChange={setView}
        label="Delimited text view"
      />
      {view === "Raw text" || table.columns.length === 0 ? (
        <TextView text={text} />
      ) : (
        <RowsTable
          rows={table.rows}
          columns={table.columns}
          caption="Delimited file contents"
        />
      )}
    </div>
  );
}
