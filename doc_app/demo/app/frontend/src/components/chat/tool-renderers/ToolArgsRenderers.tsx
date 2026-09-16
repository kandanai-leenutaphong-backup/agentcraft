/**
 * Tool-specific argument renderers.
 *
 * These components group tool parameters into layouts that match how an
 * operator reasons about the tool invocation: query target, time window,
 * search prompt, delegated task, or panel payload.
 */

import type { ReactNode } from "react";

interface ToolArgsProps {
  args: Record<string, unknown>;
}

function valueToText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function previewText(value: unknown, maxLen: number = 220): string {
  const text = valueToText(value);
  return text.length > maxLen ? `${text.slice(0, maxLen)}...` : text;
}

function shouldRenderMeta(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

function MetaRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[0.85em]">
      <span className="text-text-muted font-medium">{label}</span>
      <span className="text-text-secondary break-words">{value}</span>
    </div>
  );
}

function TimeWindow({ start, end }: { start?: unknown; end?: unknown }) {
  if (!start && !end) return null;
  return (
    <div className="rounded border border-border/50 bg-neutral-bg1 px-2 py-1 text-[0.8em] text-text-secondary">
      {valueToText(start)} to {valueToText(end)}
    </div>
  );
}

function FilterBlock({ value }: { value: unknown }) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return <span className="text-text-secondary">{valueToText(value)}</span>;
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
        <span key={key} className="rounded bg-neutral-bg1 px-2 py-1 text-[0.8em] font-mono text-text-secondary">
          {key}={valueToText(item)}
        </span>
      ))}
    </div>
  );
}

export function NoArgumentsRenderer() {
  return <div className="text-[0.85em] italic text-text-muted">No arguments</div>;
}

export function SearchQueryArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      <div className="rounded-lg border border-border/50 bg-neutral-bg1 px-3 py-2 text-text-primary">
        {previewText(args.query, 400)}
      </div>
    </div>
  );
}

export function DelegationArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      <MetaRow label="Agent" value={valueToText(args.agent_id)} />
      <div>
        <div className="mb-1 text-text-muted font-medium">Task</div>
        <div className="rounded-lg border border-border/50 bg-neutral-bg1 px-3 py-2 text-text-primary">
          {previewText(args.task, 600)}
        </div>
      </div>
    </div>
  );
}

export function PanelActionArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      <div>
        <div className="mb-1 text-text-muted font-medium">Action</div>
        <div className="rounded-lg border border-border/50 bg-neutral-bg1 px-3 py-2 text-text-primary">
          {previewText(args.action ?? args.requested_action, 300)}
        </div>
      </div>
      {shouldRenderMeta(args.reasoning) && <MetaRow label="Reasoning" value={previewText(args.reasoning)} />}
      {shouldRenderMeta(args.guide) && <MetaRow label="Guide" value={previewText(args.guide)} />}
    </div>
  );
}

/* ClassifierVerdictArgsRenderer + VERDICT_CHIP removed 2026-05-18 with
   the classifier retirement. Grid_manager's new `classify` tool renders
   via JsonFallback for the initial deploy; a typed renderer is a
   follow-up UI polish task. */

export function PriorityActionsArgsRenderer({ args }: ToolArgsProps) {
  const actions = Array.isArray(args.actions) ? args.actions : [];
  return (
    <div className="space-y-2 text-[0.85em]">
      <MetaRow label="Action count" value={String(actions.length)} />
      <div className="space-y-1">
        {actions.map((action, index) => (
          <div key={index} className="rounded border border-border/50 bg-neutral-bg1 px-2 py-1 text-text-secondary">
            {previewText((action as Record<string, unknown>).action, 160)}
          </div>
        ))}
      </div>
    </div>
  );
}

export function OperatingStateArgsRenderer({ args }: ToolArgsProps) {
  const checks = Array.isArray(args.checks) ? args.checks : [];
  const failing = checks.filter((check) => (check as Record<string, unknown>).status === "fail");
  return (
    <div className="space-y-2 text-[0.85em]">
      <MetaRow label="Checks" value={String(checks.length)} />
      <MetaRow label="Failing" value={String(failing.length)} />
      <div className="space-y-1">
        {checks.slice(0, 6).map((check, index) => {
          const item = check as Record<string, unknown>;
          return (
            <div key={index} className="rounded border border-border/50 bg-neutral-bg1 px-2 py-1 text-text-secondary">
              {valueToText(item.name)}: {valueToText(item.status)}
            </div>
          );
        })}
        {checks.length > 6 && (
          <div className="text-text-muted">+{checks.length - 6} more checks</div>
        )}
      </div>
    </div>
  );
}

export function DisturbanceSummaryArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      <MetaRow label="Event" value={valueToText(args.event_type)} />
      <MetaRow label="Location" value={valueToText(args.location)} />
      <MetaRow label="Time" value={valueToText(args.timestamp)} />
      <MetaRow label="Generation lost" value={`${valueToText(args.generation_lost_mw)} MW`} />
      <MetaRow label="Load shed" value={`${valueToText(args.load_shed_mw)} MW`} />
    </div>
  );
}

export function GraphLookupArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      {shouldRenderMeta(args.node_type) && <MetaRow label="Node type" value={valueToText(args.node_type)} />}
      {shouldRenderMeta(args.node_name) && <MetaRow label="Node id" value={<span className="font-mono">{valueToText(args.node_name)}</span>} />}
      {shouldRenderMeta(args.alias_name) && <MetaRow label="Entity id" value={<span className="font-mono">{valueToText(args.alias_name)}</span>} />}
      {shouldRenderMeta(args.filters) && <MetaRow label="Filters" value={<FilterBlock value={args.filters} />} />}
      {shouldRenderMeta(args.node_filter) && <MetaRow label="Start node" value={<FilterBlock value={args.node_filter} />} />}
      {shouldRenderMeta(args.direction) && <MetaRow label="Direction" value={valueToText(args.direction)} />}
      {args.limit !== undefined && <MetaRow label="Limit" value={valueToText(args.limit)} />}
    </div>
  );
}

export function GraphPathArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      <MetaRow label="Source type" value={valueToText(args.source_type)} />
      <MetaRow label="Target type" value={valueToText(args.target_type)} />
      {shouldRenderMeta(args.source_filter) && <MetaRow label="Source filter" value={<FilterBlock value={args.source_filter} />} />}
      {shouldRenderMeta(args.target_filter) && <MetaRow label="Target filter" value={<FilterBlock value={args.target_filter} />} />}
      {args.max_hops !== undefined && <MetaRow label="Max hops" value={valueToText(args.max_hops)} />}
      {args.limit !== undefined && <MetaRow label="Limit" value={valueToText(args.limit)} />}
    </div>
  );
}

export function EdgeArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      <MetaRow label="Source type" value={valueToText(args.source_type)} />
      <MetaRow label="Target type" value={valueToText(args.target_type)} />
      {shouldRenderMeta(args.edge_type) && <MetaRow label="Edge type" value={valueToText(args.edge_type)} />}
      {shouldRenderMeta(args.source_filter) && <MetaRow label="Source filter" value={<FilterBlock value={args.source_filter} />} />}
      {shouldRenderMeta(args.target_filter) && <MetaRow label="Target filter" value={<FilterBlock value={args.target_filter} />} />}
      {args.limit !== undefined && <MetaRow label="Limit" value={valueToText(args.limit)} />}
    </div>
  );
}

export function EntityTimeRangeArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      {(shouldRenderMeta(args.entity_id) || shouldRenderMeta(args.location)) && (
        <MetaRow
          label="Target"
          value={
            <span className="font-mono">
              {valueToText(args.entity_id ?? args.location)}
            </span>
          }
        />
      )}
      <TimeWindow start={args.time_start} end={args.time_end} />
      {shouldRenderMeta(args.order) && <MetaRow label="Order" value={valueToText(args.order)} />}
      {args.limit !== undefined && <MetaRow label="Limit" value={valueToText(args.limit)} />}
    </div>
  );
}

export function SummaryArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      {shouldRenderMeta(args.group_by) && <MetaRow label="Group by" value={valueToText(args.group_by)} />}
      {shouldRenderMeta(args.aggregation) && <MetaRow label="Aggregation" value={valueToText(args.aggregation)} />}
      {shouldRenderMeta(args.reading_type) && <MetaRow label="Reading type" value={valueToText(args.reading_type)} />}
      {shouldRenderMeta(args.entity_id) && <MetaRow label="Entity id" value={<span className="font-mono">{valueToText(args.entity_id)}</span>} />}
      {shouldRenderMeta(args.location) && <MetaRow label="Location" value={valueToText(args.location)} />}
      <TimeWindow start={args.time_start} end={args.time_end} />
      {args.limit !== undefined && <MetaRow label="Limit" value={valueToText(args.limit)} />}
    </div>
  );
}

export function AlertArgsRenderer({ args }: ToolArgsProps) {
  return (
    <div className="space-y-2 text-[0.85em]">
      <MetaRow label="Classification" value={valueToText(args.classification)} />
      <div>
        <div className="mb-1 text-text-muted font-medium">Situation</div>
        <div className="rounded-lg border border-border/50 bg-neutral-bg1 px-3 py-2 text-text-primary">
          {previewText(args.situation, 260)}
        </div>
      </div>
      {shouldRenderMeta(args.details) && <MetaRow label="Details" value={previewText(args.details)} />}
      {shouldRenderMeta(args.evidence) && <MetaRow label="Evidence" value={previewText(args.evidence)} />}
    </div>
  );
}