/**
 * SituationCard — single-situation row.
 *
 * Head row (always visible): chevron · severity pill · station code ·
 * MW lost + impact%. Classification verdict and Investigate were lifted
 * out of the head row on 2026-05-17 into their own always-visible
 * subpanels directly beneath it so each starts expanded and neither is
 * crammed into the dense head strip.
 *
 * Credibility subpanel (always visible, expanded by default): NER 4.2.3
 * verdict pill + rationale text laid out as a small captioned card.
 * While the background classifier is in flight, a muted "Classifying…"
 * placeholder holds the slot so the layout does not jump when the
 * verdict lands.
 *
 * Investigate subpanel (always visible when an `onInvestigate` handler
 * is provided): the Investigate action gets its own captioned card so
 * the operator never has to fish it out of the head-row chip strip.
 *
 * Collapsed body shows a single pattern-chip row beneath the subpanels.
 * Expanded body leads with patterns + a one-line capacity impact, then
 * affected equipment, signal chips, and a "Why this score" disclosure.
 * Footer (expanded): one primary Focus button plus icon-only topology /
 * pin secondaries.
 *
 * Couturier audit 2026-05-16 (R1, R3, R4, R6) shaped the head row; the
 * 2026-05-17 follow-up split credibility + investigate into their own
 * subpanels per operator request — "don't stuff them into one panel".
 */

import { useState } from "react";
import { ChevronDown, ChevronRight, Search, Phone, Network, Focus } from "lucide-react";
import type { SituationRecord } from "@/api/situationApi";
import { STATION_CONTACTS } from "@/config/stationContacts";
import type { GenericContact } from "@/config/stationContacts";
import { TeamsCallModal } from "@/components/shared/TeamsCallModal";
import { useSituationStore, type ClassificationState } from "@/stores/situationStore";
import { useVocab } from "@/stores/vocabularyStore";
/* Severity vocabulary + Tailwind class maps live in lib/severity so the
   card cannot drift from the alerts panel + operating-state panel. The
   surface wash is the soft `/10` tint that lifts the card off the panel
   by tone alone; the head-row pill is the strong solid fill. */
import {
  SEVERITY_PILL,
  SEVERITY_SURFACE,
  type RawSeverity,
} from "@/lib/severity";
/* Wire-decoder helpers — single source of truth for the JSON-encoded
   SituationRecord fields (`affected_equipment`, `alarm_signals`,
   `scada_signals`, `affected_tags`). The card used to inline four
   `JSON.parse(...) catch {}` IIFEs with subtle drift; the helpers
   centralise the defensive parse with explicit shape guards. */
import {
  parseAffectedEquipment,
  parseAffectedTags,
  parseSignalCounts,
  parseSignalEvidence,
} from "@/lib/situationRecord";
import {
  AlarmSignalDisclosure,
  ScadaSignalDisclosure,
  PatternDisclosure,
} from "@/components/panels/SignalEvidenceDisclosure";

interface SituationCardProps {
  situation: SituationRecord;
  onInvestigate?: (situation: SituationRecord) => void;
  onViewTopology?: (situation: SituationRecord) => void;
  /** "Focus" composite action — pin this situation to the centre tab
   *  AND open topology with the alarm overlay in one click. Delegates to
   *  the caller so keyboard/route interactions (tab switch, topology
   *  store mutations) stay in the parent component. */
  onFocusAll?: (situation: SituationRecord) => void;
  /** Render the card with the expanded body visible on first mount.
   *  Used by PinnedSituationPanel so the pinned situation reads as a
   *  full-detail view without the operator having to click into it. */
  defaultExpanded?: boolean;
  /** Render in "embedded" mode — hides the head row (severity pill /
   *  station / time / MW / Investigate), the credibility subpanel,
   *  the pattern chip row, and the top of the expanded body (time
   *  window, patterns, capacity). Used when the card is dropped
   *  inside a station-table row whose parent already carries the
   *  severity badge, station code, and window range — the card
   *  should drop straight into the by-equipment / by-alarm breakdown
   *  and everything below it (operator brief 2026-05-24). Implies
   *  defaultExpanded=true (a collapsed embedded card has nothing
   *  visible to click). */
  embedded?: boolean;
}

export function SituationCard({ situation: sit, onInvestigate, onViewTopology, onFocusAll, defaultExpanded = false, embedded = false }: SituationCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded || embedded);
  /* Track which equipment boxes are expanded by equipment_id. */
  const [expandedEquip, setExpandedEquip] = useState<Set<string>>(new Set());
  /* Track whether the equipment section itself is collapsed. */
  const [equipSectionOpen, setEquipSectionOpen] = useState(true);
  /* Track whether the contacts section is open. */
  const [contactsOpen, setContactsOpen] = useState(false);
  /* Toggle between "by-equipment", "all-alarms", and "all-scada" view. */
  const [alarmView, setAlarmView] = useState<"equipment" | "alarms" | "scada">("equipment");
  /* Track active Teams call modal contact. */
  const [callingContact, setCallingContact] = useState<GenericContact | null>(null);
  /* Click-to-expand evidence panels per chip. One open chip per group
     (alarm signal / SCADA signal / pattern). Operator brief 2026-05-25
     — click a chip to see the rows + rule that produced its count. */
  const [openAlarmSignal, setOpenAlarmSignal] = useState<string | null>(null);
  const [openScadaSignal, setOpenScadaSignal] = useState<string | null>(null);
  const [openPattern, setOpenPattern] = useState<string | null>(null);

  /* Classification verdict — the background NER 4.2.3 fetch path was
     retired 2026-05-18 when the classifier moved into grid_manager's
     `classify` chat tool (writes to panelStore.classifyVerdict). The
     CredibilitySubpanel below still consumes situationStore's per-card
     classification slot in case a future flow re-populates it; until
     then the subpanel renders its idle/indeterminate default. The dead
     POST /api/situations/classify call was removed 2026-05-20 (AUTODEV
     §0.3) — it was returning HTTP 404 on every card mount. */
  const classification = useSituationStore((s) => s.classifications[sit.situation_id]);

  /* Domain vocabulary — every energy-specific label on the card reads
     through these so a scenario fully relabels the card for its industry
     (impact unit, system label, telemetry/alert wording, capacity). */
  const impactUnit = useVocab("impactUnit");
  const impactLabel = useVocab("impactLabel");
  const capacityLabel = useVocab("capacityLabel");
  const systemLabel = useVocab("systemLabel");
  const facilityTermSingular = useVocab("facilityTermSingular");
  const alertsLabel = useVocab("alertsLabel");
  const telemetryLabel = useVocab("telemetryLabel");

  const stationContacts = STATION_CONTACTS[sit.station] ?? [];

  const alarmSignals = parseSignalCounts(sit.alarm_signals);
  const scadaSignals = parseSignalCounts(sit.scada_signals);
  const affectedTags = parseAffectedTags(sit.affected_tags);
  const affectedEquipment = parseAffectedEquipment(sit.affected_equipment);
  /* Per-signal evidence map — the rule + rows that triggered each
     signal chip. Empty `{}` on partial frames (evidence layer has not
     run yet) and on records that fired no signals; the disclosures
     guard their renders against that. */
  const signalEvidence = parseSignalEvidence(sit.signal_evidence);

  /* Toggle a single equipment box open/closed. */
  const toggleEquip = (eid: string) => {
    setExpandedEquip((prev) => {
      const next = new Set(prev);
      if (next.has(eid)) next.delete(eid); else next.add(eid);
      return next;
    });
  };

  /* Pattern list for collapsed chip row + expanded patterns section. */
  const patternList = (sit.patterns ?? "").split(",").map((p) => p.trim()).filter(Boolean);

  /* Hoisted scope/percentage selection for the head row. Computed once
     so the wide row-1 chip and the narrow row-2 chip (R9 reflow) share
     a single source of truth and stay byte-identical. */
  const pct = sit.total_mw_lost > 0
    ? (sit.impact_station_pct > 0 ? { val: sit.impact_station_pct, label: facilityTermSingular.toLowerCase() }
      : sit.impact_region_pct > 0 ? { val: sit.impact_region_pct, label: sit.station_region }
      : sit.impact_nem_pct > 0 ? { val: sit.impact_nem_pct, label: systemLabel }
      : null)
    : null;
  const pctColor = pct ? (pct.val > 10 ? "text-status-error" : pct.val > 1 ? "text-status-warning" : "text-text-muted") : "";

  return (
    <div
      data-testid={`situation-card-${sit.situation_id}`}
      data-spotlight-id={`situation-card-${sit.situation_id}`}
      data-severity={sit.severity}
      /* Card chrome (borderless):
           Severity is conveyed by the tinted surface below + the colour
           pill at the head. No outline, no left strip. The `animate-
           fresh-hairline` token is preserved for backwards compatibility
           but renders nothing under the global borderless reset.
         Couturier R9 (2026-05-17): `@container/card` establishes the
         containment context for the head-row container queries below.
         The card reflows as the surrounding resizable panel narrows;
         viewport queries are useless here because the viewport does
         not change when the operator drags the splitter. */
      className={`@container/card rounded-lg ${SEVERITY_SURFACE[sit.severity as RawSeverity] ?? "bg-neutral-bg2"} overflow-hidden animate-fresh-hairline`}
    >
      {/* Head row — severity-first glance hierarchy.
          Reading order (wide): chevron · severity · station · MW · % ·
          classification chip · Investigate.
          Pin moved out of the head row to reduce clutter; it lives in
          the expanded footer alongside topology.
          Couturier R9 (2026-05-17): the head row reflows in three
          container-query stages:
            - wide  (>= @[24rem]/card): full labels everywhere.
            - medium ([18rem-24rem)):   MW%-suffix and chip-label hide;
                                        Investigate keeps its label.
            - narrow (<  @[18rem]):     two-row layout. Row 1 carries
                                        chevron · severity · station ·
                                        Investigate (icon-only). Row 2
                                        carries MW · MW% · chip.
          Station is the one element that absorbs slack (`flex-1 min-w-0
          truncate`); the spacer span the layout used to rely on is
          gone — station owns the gap. */}
      {/* Head row wrapper — expand-toggle button + Investigate icon
          button sit side-by-side so the Investigate action is reachable
          on the extreme right of every card without a dedicated
          subpanel. Nested buttons are not legal HTML, so the expand
          chevron region and the Investigate trigger are siblings inside
          a flex container.
          Suppressed in embedded mode (2026-05-24) — the host station-
          table row already carries severity / station / window so the
          card head would just duplicate it. */}
      {!embedded && (
      <div className="flex items-stretch">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex-1 min-w-0 flex flex-col text-left hover:bg-neutral-bg2/50 transition-colors"
        >
        {/* Row 1 — always rendered. */}
        <div className="flex items-center gap-2 min-w-0 px-3 pt-2 pb-2 @[18rem]/card:pb-2">
          {expanded ? (
            <ChevronDown className="h-3 w-3 text-text-muted shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 text-text-muted shrink-0" />
          )}

          {/* Severity pill — dominant. `text-sm font-black tracking-wide`
              is the largest categorical type on the head row, ahead of MW.
              Operators read severity first, always. */}
          <span
            data-testid={`severity-pill-${sit.situation_id}`}
            className={`shrink-0 px-2 py-0.5 text-sm font-black tracking-wide rounded ${SEVERITY_PILL[sit.severity as RawSeverity] ?? SEVERITY_PILL.minor}`}
          >
            {sit.severity}
          </span>

          {/* Station code — absorbs slack. Drops `shrink-0`, gains
              `flex-1 min-w-0 truncate` so it is the one element that
              gives ground as the card narrows. */}
          <span className="flex-1 min-w-0 text-sm font-bold text-text-primary truncate font-mono">
            {sit.station}
          </span>

          {/* MW lost — visible inline at @[18rem]+. At narrow it
              re-renders in row 2. */}
          {sit.total_mw_lost > 0 && (
            <span className="hidden @[18rem]/card:inline-block shrink-0 text-base font-bold text-status-error font-mono">
              {Math.round(sit.total_mw_lost).toLocaleString()} {impactUnit}
            </span>
          )}

          {/* Impact percentage — companion to MW. Label suffix
              (`stn`/region/`NEM`) only at wide. */}
          {pct && (
            <span className={`hidden @[18rem]/card:inline-block shrink-0 text-xs font-bold font-mono ${pctColor}`}>
              · {pct.val}%
              <span className="hidden @[24rem]/card:inline"> {pct.label}</span>
            </span>
          )}

          {/* Classification chip + Investigate were moved out of the
             head row on 2026-05-17 into their own always-visible
             subpanels (see <CredibilitySubpanel> and
             <InvestigateSubpanel> below). The head row keeps only
             severity + station + MW%; secondary concerns each get a
             dedicated captioned card. */}
        </div>

        {/* Row 2 — narrow only. Mirrors MW · MW% (the classification
            chip used to ride here too; it moved into its own subpanel
            on 2026-05-17). Left-aligned under station (`pl-6` matches
            chevron + gap), muted weight so it reads as supplementary
            to row 1. */}
        {sit.total_mw_lost > 0 && (
          <div
            data-testid={`head-narrow-row-${sit.situation_id}`}
            className="flex @[18rem]/card:hidden items-center gap-2 pl-6 pr-3 pb-2 -mt-1 text-xs"
          >
            <span className="shrink-0 font-bold text-status-error font-mono">
              {Math.round(sit.total_mw_lost).toLocaleString()} {impactUnit}
            </span>
            {pct && (
              <span className={`shrink-0 font-bold font-mono ${pctColor}`}>
                · {pct.val}%
              </span>
            )}
          </div>
        )}
        </button>

        {/* Investigate — small icon button anchored to the extreme right
            of the head row. Replaces the prior full-width subpanel
            (operator brief 2026-05-21: "investigate should be much
            smaller, button on extreme right of situation header"). The
            button is a sibling of the expand-toggle, not nested, so the
            click never bubbles into the chevron handler. */}
        {onInvestigate && (
          <button
            type="button"
            data-testid={`investigate-${sit.station}`}
            aria-label={`Investigate ${sit.station}`}
            title={`Investigate ${sit.station}`}
            onClick={(e) => { e.stopPropagation(); onInvestigate(sit); }}
            className="shrink-0 self-start mt-2 mr-2 h-7 w-7 flex items-center justify-center rounded bg-brand text-on-accent hover:bg-brand-hover transition-colors"
          >
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </div>
      )}

      {/* Credibility subpanel — single small captioned card under the
          head row, expanded by default. Investigate used to live here as
          a full-width sibling card; on 2026-05-21 it was shrunk to an
          icon-only button anchored to the extreme right of the head row
          (see Row 1 above) so the situation list reads denser.
          Suppressed in embedded mode — the host row supplies severity
          framing; the classifier chip would compete with it. */}
      {!embedded && (
      <div className="px-3 pb-2 pt-1 space-y-1.5">
        <CredibilitySubpanel state={classification} sid={sit.situation_id} />
      </div>
      )}

      {/* Pattern chip row — visible in the collapsed state only.
          Compound patterns are the most decision-shaping signal short
          of severity; promoting them to the head means the operator
          knows what kind of incident this is without expansion. */}
      {!expanded && patternList.length > 0 && (
        <div
          data-testid={`pattern-chip-row-${sit.situation_id}`}
          className="flex flex-wrap items-center gap-1 px-3 pb-2 -mt-1"
        >
          {patternList.slice(0, 3).map((p) => (
            <span
              key={p}
              className="px-1.5 py-0.5 text-micro bg-tag-pattern-bg text-tag-pattern-text rounded font-mono truncate max-w-[12rem]"
              title={p.replace(/_/g, " ")}
            >
              {p.replace(/_/g, " ")}
            </span>
          ))}
          {patternList.length > 3 && (
            <span className="text-micro text-text-muted font-mono">+{patternList.length - 3}</span>
          )}
        </div>
      )}

      {/* Expanded details — resizable vertically.
          Body order (R3): patterns → capacity (single line) → affected
          equipment → alarm/scada signal chips → classification rationale
          → "Why this score" disclosure. Detector internals stay tucked
          behind the disclosure so the body leads with user-meaningful
          context. */}
      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-border/30 resize-y overflow-auto min-h-[4rem]">
          {/* Time window — suppressed in embedded mode; the host row
              already shows the window range. */}
          {!embedded && (
            <div className="text-micro text-text-muted pt-1.5">
              {sit.window_start} → {sit.window_end}
            </div>
          )}

          {/* Patterns — promoted to lead the expanded body. Suppressed
              in embedded mode per operator brief 2026-05-24: drop into
              by-equipment / by-alarm breakdown straight away. */}
          {!embedded && patternList.length > 0 && (
            <div data-testid="patterns-section" className="space-y-0.5">
              <div className="text-micro text-text-muted font-medium uppercase tracking-wider">Patterns</div>
              <div className="flex flex-wrap gap-1">
                {patternList.map((p) => {
                  const hasEvidence = !!signalEvidence.patterns[p];
                  const isOpen = openPattern === p;
                  return (
                    <button
                      key={p}
                      type="button"
                      data-testid={`pattern-chip-${p}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!hasEvidence) return;
                        setOpenPattern(isOpen ? null : p);
                      }}
                      aria-expanded={isOpen}
                      disabled={!hasEvidence}
                      className={`px-1.5 py-0.5 text-micro bg-tag-pattern-bg text-tag-pattern-text rounded ${hasEvidence ? "hover:ring-1 hover:ring-tag-pattern-text/40 cursor-pointer" : "opacity-80 cursor-default"} ${isOpen ? "ring-1 ring-tag-pattern-text/60" : ""}`}
                    >
                      {p.replace(/_/g, " ")}
                    </button>
                  );
                })}
              </div>
              {openPattern && signalEvidence.patterns[openPattern] && (
                <PatternDisclosure
                  patternId={openPattern}
                  evidence={signalEvidence.patterns[openPattern]}
                />
              )}
            </div>
          )}

          {/* Capacity Impact — single-line variant. Worst-tier colour
              drives the MW lost number; per-scope percentages follow
              as compact mono chips. Collapses three near-identical
              rows into one legible line (audit F-009). Suppressed in
              embedded mode — the row already aggregates the MW story
              upstream; surfacing it again duplicates the parent. */}
          {!embedded && sit.total_mw_lost > 0 && (sit.station_rated_mw > 0 || sit.region_live_mw > 0 || sit.nem_live_mw > 0) && (() => {
            const worstPct = Math.max(sit.impact_station_pct, sit.impact_region_pct, sit.impact_nem_pct);
            const worstColour = worstPct > 10 ? "text-status-error" : worstPct > 1 ? "text-status-warning" : "text-text-muted";
            return (
              <div data-testid="capacity-impact-section" className="text-micro flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="text-text-muted font-medium uppercase tracking-wider">{capacityLabel}</span>
                <span className={`font-mono font-bold ${worstColour}`}>{Math.round(sit.total_mw_lost).toLocaleString()} {impactLabel}</span>
                {sit.station_rated_mw > 0 && (
                  <span className="text-text-secondary">· {facilityTermSingular.toLowerCase()} <span className="font-mono">{sit.impact_station_pct}%</span></span>
                )}
                {sit.region_live_mw > 0 && (
                  <span className="text-text-secondary">· {sit.station_region} <span className="font-mono">{sit.impact_region_pct}%</span></span>
                )}
                {sit.nem_live_mw > 0 && (
                  <span className="text-text-secondary">· {systemLabel} <span className="font-mono">{sit.impact_nem_pct}%</span></span>
                )}
              </div>
            );
          })()}

          {/* Affected Equipment — enriched collapsible boxes */}
          {affectedEquipment.length > 0 ? (
            <div className="space-y-0.5">
              {/* View toggle: segmented control with a single moving
                  highlight. Both options share track + type weight so
                  the only visual difference is which side is lit
                  (audit F-013). */}
              <div
                data-testid="alarm-view-toggle"
                role="tablist"
                aria-label="Equipment view"
                className="inline-flex items-center gap-0.5 mb-1 bg-neutral-bg2 rounded p-0.5"
              >
                <button
                  data-testid="alarm-view-equipment"
                  role="tab"
                  aria-selected={alarmView === "equipment"}
                  data-active={alarmView === "equipment" ? "true" : "false"}
                  onClick={(e) => { e.stopPropagation(); setAlarmView("equipment"); }}
                  className={`px-2 py-0.5 text-micro font-medium rounded transition-colors ${
                    alarmView === "equipment" ? "bg-neutral-bg1 text-text-primary" : "text-text-muted hover:text-text-secondary"
                  }`}
                >By Equipment</button>
                <button
                  data-testid="alarm-view-alarms"
                  role="tab"
                  aria-selected={alarmView === "alarms"}
                  data-active={alarmView === "alarms" ? "true" : "false"}
                  onClick={(e) => { e.stopPropagation(); setAlarmView("alarms"); }}
                  className={`px-2 py-0.5 text-micro font-medium rounded transition-colors ${
                    alarmView === "alarms" ? "bg-neutral-bg1 text-text-primary" : "text-text-muted hover:text-text-secondary"
                  }`}
                >All {alertsLabel}</button>
                <button
                  data-testid="alarm-view-scada"
                  role="tab"
                  aria-selected={alarmView === "scada"}
                  data-active={alarmView === "scada" ? "true" : "false"}
                  onClick={(e) => { e.stopPropagation(); setAlarmView("scada"); }}
                  className={`px-2 py-0.5 text-micro font-medium rounded transition-colors ${
                    alarmView === "scada" ? "bg-neutral-bg1 text-text-primary" : "text-text-muted hover:text-text-secondary"
                  }`}
                >All {telemetryLabel}</button>
              </div>

              {/* All Alarms — flat tabular view */}
              {alarmView === "alarms" && (() => {
                const allAlarms = affectedEquipment
                  .flatMap((eq) => (eq.alarms ?? []).map((a) => ({ ...a, equipment_id: eq.equipment_id })))
                  .sort((a, b) => (a.timestamp_aest ?? "").localeCompare(b.timestamp_aest ?? ""));
                if (allAlarms.length === 0) return (
                  <div className="text-micro text-text-muted italic py-1">No alarm rows</div>
                );
                return (
                  <div data-testid="alarm-table" className="overflow-x-auto rounded-lg border border-border max-h-64 overflow-y-auto resize-y">
                    <table className="w-full border-collapse text-micro">
                      <thead className="bg-neutral-bg3 text-text-muted text-micro uppercase tracking-wider sticky top-0">
                        <tr>
                          <th className="px-2 py-1 text-left font-semibold border-b border-border">Time</th>
                          <th className="px-2 py-1 text-left font-semibold border-b border-border">Equipment</th>
                          <th className="px-2 py-1 text-left font-semibold border-b border-border">Label</th>
                          <th className="px-2 py-1 text-left font-semibold border-b border-border">Priority</th>
                          <th className="px-2 py-1 text-left font-semibold border-b border-border">Text</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allAlarms.map((a, i) => (
                          <tr key={i} className="hover:bg-neutral-bg3/50 even:bg-neutral-bg2/30">
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 whitespace-nowrap font-mono">{a.timestamp_aest?.slice(11, 19) ?? ""}</td>
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 whitespace-nowrap font-mono">{a.equipment_id}</td>
                            <td className="px-2 py-1 text-tag-alarm-text border-b border-border/30 font-semibold">{a.alarm_label}</td>
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 font-mono">P{a.priority}</td>
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 truncate max-w-[200px]">{a.alarm_text}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                );
              })()}

              {/* All SCADA — flat tabular view, paginated to the 30 most
                  recent rows (timestamp DESC). 2026-05-24 operator brief:
                  SCADA volumes are heavier than alarms; the operator
                  wants the freshest activity, not the whole window. */}
              {alarmView === "scada" && (() => {
                const allScada = affectedEquipment
                  .flatMap((eq) => (eq.scada ?? []).map((s) => ({ ...s, equipment_id: eq.equipment_id })))
                  /* Most recent first; ISO-shaped timestamps sort by string. */
                  .sort((a, b) => (b.timestamp_aest ?? "").localeCompare(a.timestamp_aest ?? ""));
                const totalScada = allScada.length;
                const pageRows = allScada.slice(0, 30);
                if (totalScada === 0) return (
                  <div className="text-micro text-text-muted italic py-1">No {telemetryLabel} rows</div>
                );
                return (
                  <div data-testid="scada-table" className="overflow-x-auto rounded-lg border border-border max-h-64 overflow-y-auto resize-y">
                    <table className="w-full border-collapse text-micro">
                      <thead className="bg-neutral-bg3 text-text-muted text-micro uppercase tracking-wider sticky top-0">
                        <tr>
                          <th className="px-2 py-1 text-left font-semibold border-b border-border">Time</th>
                          <th className="px-2 py-1 text-left font-semibold border-b border-border">Equipment</th>
                          <th className="px-2 py-1 text-left font-semibold border-b border-border">Measurement</th>
                          <th className="px-2 py-1 text-right font-semibold border-b border-border">Prev</th>
                          <th className="px-2 py-1 text-right font-semibold border-b border-border">Value</th>
                          <th className="px-2 py-1 text-right font-semibold border-b border-border">Δ</th>
                          <th className="px-2 py-1 text-right font-semibold border-b border-border">%</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pageRows.map((s, i) => (
                          <tr key={i} className="hover:bg-neutral-bg3/50 even:bg-neutral-bg2/30">
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 whitespace-nowrap font-mono">{s.timestamp_aest?.slice(11, 19) ?? ""}</td>
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 whitespace-nowrap font-mono">{s.equipment_id}</td>
                            <td className="px-2 py-1 text-tag-scada-text border-b border-border/30 font-semibold">{s.measurement}</td>
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 font-mono text-right tabular-nums">{s.prev_val}</td>
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 font-mono text-right tabular-nums">{s.Value}</td>
                            <td className="px-2 py-1 border-b border-border/30 font-mono text-right tabular-nums text-status-error">
                              {(s.abs_drop ?? 0) > 0 ? "−" : "+"}{Math.abs(s.abs_drop ?? 0)}
                            </td>
                            <td className="px-2 py-1 text-text-secondary border-b border-border/30 font-mono text-right tabular-nums">{s.pct_change ?? 0}%</td>
                          </tr>
                        ))}
                      </tbody>
                      {totalScada > 30 && (
                        <tfoot>
                          <tr>
                            <td colSpan={7} className="px-2 py-1 text-micro text-text-muted italic border-t border-border bg-neutral-bg3/50">
                              Showing 30 most recent of {totalScada} {telemetryLabel} rows in this window.
                            </td>
                          </tr>
                        </tfoot>
                      )}
                    </table>
                  </div>
                );
              })()}

              {/* By Equipment — existing collapsible boxes */}
              {alarmView === "equipment" && (
                <>
              <button
                onClick={(e) => { e.stopPropagation(); setEquipSectionOpen(!equipSectionOpen); }}
                className="flex items-center gap-1 text-micro text-text-muted font-medium uppercase tracking-wider hover:text-text-secondary transition-colors"
              >
                {equipSectionOpen
                  ? <ChevronDown className="h-2.5 w-2.5" />
                  : <ChevronRight className="h-2.5 w-2.5" />}
                Affected Equipment ({affectedEquipment.length})
              </button>

              {equipSectionOpen && (
                <div
                  className="overflow-y-auto resize-y space-y-1 rounded border border-border/30 p-1"
                  style={{ minHeight: "2rem" }}
                >
                  {affectedEquipment.map((eq) => {
                    const isOpen = expandedEquip.has(eq.equipment_id);
                    const alarmCount = eq.alarms?.length ?? 0;
                    const scadaCount = eq.scada?.length ?? 0;
                    return (
                      <div
                        key={eq.equipment_id}
                        data-testid="equipment-box"
                        className="rounded border border-border/20 bg-neutral-bg2/50 overflow-hidden"
                      >
                        {/* Equipment header */}
                        <button
                          onClick={(e) => { e.stopPropagation(); toggleEquip(eq.equipment_id); }}
                          className="w-full flex items-center gap-1.5 px-2 py-1 text-left hover:bg-neutral-bg3/50 transition-colors"
                        >
                          {isOpen
                            ? <ChevronDown className="h-2.5 w-2.5 text-text-muted shrink-0" />
                            : <ChevronRight className="h-2.5 w-2.5 text-text-muted shrink-0" />}
                          <span className="flex-1 text-micro font-mono text-text-primary truncate">
                            {eq.equipment_id}
                          </span>
                          {alarmCount > 0 && (
                            <span className="text-micro text-tag-alarm-text font-mono">{alarmCount}A</span>
                          )}
                          {scadaCount > 0 && (
                            <span className="text-micro text-tag-scada-text font-mono">{scadaCount}S</span>
                          )}
                        </button>

                        {/* Expanded: alarm + SCADA rows */}
                        {isOpen && (
                          <div className="px-2 pb-1.5 space-y-1 border-t border-border/20">
                            {/* Alarm rows */}
                            {alarmCount > 0 && (
                              <div className="space-y-0.5 pt-1">
                                <div className="text-micro text-text-muted font-medium">{alertsLabel}</div>
                                {eq.alarms.map((a, i) => (
                                  <div
                                    key={i}
                                    data-testid="equipment-alarm-row"
                                    className="flex items-start gap-1.5 text-micro bg-tag-alarm-bg/50 rounded px-1.5 py-0.5"
                                  >
                                    <span className="shrink-0 font-bold text-tag-alarm-text">P{a.priority}</span>
                                    <span className="shrink-0 text-text-muted font-mono">
                                      {a.timestamp_aest?.slice(11, 19) ?? ""}
                                    </span>
                                    <span className="shrink-0 font-semibold text-tag-alarm-text">{a.alarm_label}</span>
                                    <span className="text-text-secondary truncate">{a.alarm_text}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                            {/* SCADA rows */}
                            {scadaCount > 0 && (
                              <div className="space-y-0.5 pt-0.5">
                                <div className="text-micro text-text-muted font-medium">{telemetryLabel}</div>
                                {eq.scada.map((s, i) => (
                                  <div
                                    key={i}
                                    data-testid="equipment-scada-row"
                                    className="flex items-center gap-1.5 text-micro bg-tag-scada-bg/50 rounded px-1.5 py-0.5"
                                  >
                                    <span className="shrink-0 text-text-muted font-mono">
                                      {s.timestamp_aest?.slice(11, 19) ?? ""}
                                    </span>
                                    <span className="shrink-0 font-semibold text-tag-scada-text">{s.measurement}</span>
                                    <span className="font-mono text-text-secondary">
                                      {s.prev_val} → {s.Value}
                                    </span>
                                    <span className="font-mono text-status-error">
                                      ({s.abs_drop > 0 ? "−" : "+"}{Math.abs(s.abs_drop)})
                                    </span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              </>
              )}
            </div>
          ) : (
            /* Fallback: old affected_tags flat display */
            Array.isArray(affectedTags) && affectedTags.length > 0 && (
              <div className="space-y-0.5">
                <div className="text-micro text-text-muted font-medium uppercase tracking-wider">Affected Equipment</div>
                <div className="text-micro text-text-secondary font-mono truncate">
                  {affectedTags.slice(0, 5).join(", ")}
                  {affectedTags.length > 5 && ` +${affectedTags.length - 5} more`}
                </div>
              </div>
            )
          )}

          {/* Alarm signal chips — raw signal evidence. Sits after the
              equipment block so the operator reads the equipment-grouped
              evidence first. Each chip is clickable when the backend
              attached a `signal_evidence.alarm[id]` bundle; clicking
              expands a small disclosure with the rule + matched rows
              (spec/signal_evidence_2026-05-24_proposal.md). */}
          {Object.keys(alarmSignals).length > 0 && (
            <div className="space-y-0.5">
              <div className="text-micro text-text-muted font-medium uppercase tracking-wider">{alertsLabel} Signals</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(alarmSignals).map(([key, val]) => {
                  const hasEvidence = !!signalEvidence.alarm[key];
                  const isOpen = openAlarmSignal === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      data-testid={`alarm-signal-chip-${key}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!hasEvidence) return;
                        setOpenAlarmSignal(isOpen ? null : key);
                      }}
                      aria-expanded={isOpen}
                      disabled={!hasEvidence}
                      className={`px-1.5 py-0.5 text-micro bg-tag-alarm-bg text-tag-alarm-text rounded font-mono ${hasEvidence ? "hover:ring-1 hover:ring-tag-alarm-text/40 cursor-pointer" : "opacity-80 cursor-default"} ${isOpen ? "ring-1 ring-tag-alarm-text/60" : ""}`}
                    >
                      {key}={String(val)}
                    </button>
                  );
                })}
              </div>
              {openAlarmSignal && signalEvidence.alarm[openAlarmSignal] && (
                <AlarmSignalDisclosure
                  signalId={openAlarmSignal}
                  evidence={signalEvidence.alarm[openAlarmSignal]}
                />
              )}
            </div>
          )}

          {/* SCADA signal chips. Click-to-expand mirrors the alarm side. */}
          {Object.keys(scadaSignals).length > 0 && (
            <div className="space-y-0.5">
              <div className="text-micro text-text-muted font-medium uppercase tracking-wider">{telemetryLabel} Signals</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(scadaSignals).map(([key, val]) => {
                  const hasEvidence = !!signalEvidence.scada[key];
                  const isOpen = openScadaSignal === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      data-testid={`scada-signal-chip-${key}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!hasEvidence) return;
                        setOpenScadaSignal(isOpen ? null : key);
                      }}
                      aria-expanded={isOpen}
                      disabled={!hasEvidence}
                      className={`px-1.5 py-0.5 text-micro bg-tag-scada-bg text-tag-scada-text rounded font-mono ${hasEvidence ? "hover:ring-1 hover:ring-tag-scada-text/40 cursor-pointer" : "opacity-80 cursor-default"} ${isOpen ? "ring-1 ring-tag-scada-text/60" : ""}`}
                    >
                      {key}={String(val)}
                    </button>
                  );
                })}
              </div>
              {openScadaSignal && signalEvidence.scada[openScadaSignal] && (
                <ScadaSignalDisclosure
                  signalId={openScadaSignal}
                  evidence={signalEvidence.scada[openScadaSignal]}
                />
              )}
            </div>
          )}

          {/* Classification rationale used to live here as a disclosure;
              on 2026-05-17 it moved into the always-visible Credibility
              subpanel directly under the head row so the operator does
              not have to expand the card to read why the classifier
              voted the way it did. */}

          {/* Why this score — detector internals tucked behind a
              disclosure so the expanded body leads with operator-
              meaningful context and not detector accounting. */}
          <details data-testid={`why-this-score-${sit.situation_id}`} className="group">
            <summary className="flex items-center gap-1 cursor-pointer text-micro text-text-muted font-medium uppercase tracking-wider hover:text-text-secondary transition-colors list-none">
              <ChevronRight className="h-2.5 w-2.5 transition-transform group-open:rotate-90" />
              Why this score
            </summary>
            <div className="flex gap-3 text-micro pt-1 pl-3">
              <span className="text-text-secondary">Alarms: <span className="font-mono">{sit.alarm_score}</span></span>
              <span className="text-text-secondary">SCADA: <span className="font-mono">{sit.scada_score}</span></span>
              <span className="text-text-secondary">MW+: <span className="font-mono">{sit.mw_boost}</span></span>
            </div>
          </details>

          {/* Contacts section — generic station contacts */}
          {stationContacts.length > 0 && (
            <div data-testid="situation-contact-section" className="space-y-0.5">
              <button
                onClick={(e) => { e.stopPropagation(); setContactsOpen(!contactsOpen); }}
                className="flex items-center gap-1 text-micro text-text-muted font-medium uppercase tracking-wider hover:text-text-secondary transition-colors"
              >
                {contactsOpen
                  ? <ChevronDown className="h-2.5 w-2.5" />
                  : <ChevronRight className="h-2.5 w-2.5" />}
                Contacts ({stationContacts.length})
              </button>
              {contactsOpen && (
                <div className="space-y-1 rounded border border-border/30 p-1">
                  {stationContacts.map((c, i) => (
                    <div key={i} className="flex items-center gap-2 px-2 py-1 rounded bg-neutral-bg2/50 text-micro">
                      <span className="font-semibold text-text-primary truncate">{c.name}</span>
                      <span className="text-text-muted truncate flex-1">{c.role}</span>
                      <span className="font-mono text-text-secondary shrink-0">{c.phone}</span>
                      <button
                        data-testid="contact-call-button"
                        onClick={(e) => { e.stopPropagation(); setCallingContact(c); }}
                        className="shrink-0 p-1 rounded bg-brand/15 text-brand hover:bg-brand/25 transition-colors"
                        title={`Call ${c.name} on Teams`}
                      >
                        <Phone className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Footer actions (R4): one primary Focus button, then an
              icon-only View topology secondary. Per-card Pin was
              retired 2026-05-25 — pin granularity moved to the
              station level (Pin button on the station-group header in
              SituationAlertsPanel); Investigate auto-pins silently. */}
          {(onFocusAll || onViewTopology) && (
            <div className="pt-1 space-y-1.5">
              {onFocusAll && (
                <button
                  data-testid={`focus-situation-${sit.situation_id}`}
                  onClick={(e) => { e.stopPropagation(); onFocusAll(sit); }}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded bg-brand text-on-accent hover:bg-brand-hover transition-colors"
                >
                  <Focus className="h-3 w-3" />
                  Focus
                </button>
              )}
              {onViewTopology && (
                <div className="flex items-center gap-1">
                  <button
                    data-testid={`view-topology-${sit.station}`}
                    aria-label="View topology"
                    title="View topology"
                    onClick={(e) => { e.stopPropagation(); onViewTopology(sit); }}
                    className="shrink-0 p-1.5 rounded bg-neutral-bg2 text-text-secondary hover:bg-neutral-bg3 hover:text-text-primary transition-colors"
                  >
                    <Network className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Teams call modal */}
      {callingContact && (
        <TeamsCallModal contact={callingContact} onClose={() => setCallingContact(null)} />
      )}
    </div>
  );
}


/* ── Classification + Investigate surfaces ─────────────────────────────
   After the 2026-05-17 operator-feedback round, credibility and
   investigate moved out of the head row and into their own always-
   visible captioned subpanels under the head row:

     - ClassificationChip       : the small verdict pill, now used as
                                  the right-aligned glyph inside
                                  <CredibilitySubpanel>'s header.
                                  Renders nothing while the verdict is
                                  in flight; the subpanel itself shows
                                  the "Classifying…" placeholder.
     - CredibilitySubpanel      : always-visible captioned card. Verdict
                                  pill in the header, rationale text in
                                  the body — both "expanded" by default
                                  so the operator never has to drill in
                                  to read the classifier's reasoning.
     - InvestigateSubpanel      : always-visible captioned card with a
                                  prominent Investigate button. Hosted
                                  separately so the action is not
                                  competing with the verdict pill on
                                  the head row.

   The pre-2026-05-17 inline head-row chip + Investigate button + body
   disclosure (<ClassificationRationale>) are retired. */

/* Operator label mapping (2026-05-17 follow-up #2 — softened).
 *
 *   non_credible → "Non-Credible" → green
 *   credible     → "Credible"     → orange
 *   non_event    → "Safe"         → red
 *
 * The bold full-fill verdict button was too thick; pastel /15 tints +
 * matched-tone text now read as a soft inline pill instead of a
 * shouting button. Long-form labels per operator request. */

const CLASS_PILL_SOFT: Record<string, string> = {
  non_credible: "bg-status-success/15 text-status-success",
  credible:     "bg-status-warning/15 text-status-warning",
  non_event:    "bg-status-error/15 text-status-error",
};

const CLASS_LABEL: Record<string, string> = {
  non_credible: "Non-Credible",
  credible:     "Credible",
  non_event:    "Safe",
};

/* Long form is now identical to the visible label, but the constant is
 * kept as the aria-label source so screen-reader output stays stable
 * if the visible label is ever shortened back. */
const CLASS_LABEL_LONG: Record<string, string> = {
  non_credible: "Non-Credible",
  credible:     "Credible",
  non_event:    "Safe",
};

interface CredibilitySubpanelProps {
  state: ClassificationState | undefined;
  sid: string;
}

/* CredibilitySubpanel — collapsible classifier verdict line.
 *
 * Default (collapsed) view shows only the verdict + score: `Non-Credible
 * | 53/100`. Clicking the panel reveals the model's rationale beneath.
 * Replaces the always-visible "Verdict | Score — Rationale" line so the
 * head-area density drops to a glance read of "which way did the
 * classifier vote and how strongly" — the rationale is one click away
 * when the operator wants the *why*, instead of always-on.
 *
 * Loading / unavailable / rationale-less states render the line as a
 * static, non-interactive pill: nothing to toggle, no chevron.
 *
 * `confidence` is a 0–100 integer; the server defaults to 50 when the
 * model omits a value so this is always a number once status === ready.
 *
 * 2026-05-18 update — replaces the line-clamp-to-two-lines version.
 */
function CredibilitySubpanel({ state, sid }: CredibilitySubpanelProps) {
  const status = state?.status ?? "idle";
  const cls = state?.classification ?? "non_event";
  const rationale = state?.rationale ?? "";
  const confidence = state?.confidence;

  // Cut "Classifier unavailable" subpanel entirely on error/idle states
  // (Phase 2 workstream D, 2026-05-18). The retired background classifier
  // sometimes leaves `status === "error"` on situation records; that label
  // was confusing to operators and added no actionable signal. When the
  // situation-detector classifier has no usable verdict (error/idle), the
  // subpanel collapses to zero height. Loading state still renders the
  // "Classifying…" placeholder so the operator knows a verdict is in flight.
  if (status === "error" || status === "idle") {
    return null;
  }

  const ready = status === "ready";
  const label = ready ? (CLASS_LABEL[cls] ?? "Unclassified") : "Classifying…";
  const longLabel = ready ? (CLASS_LABEL_LONG[cls] ?? cls) : label;
  const fill = ready
    ? (CLASS_PILL_SOFT[cls] ?? CLASS_PILL_SOFT.non_event)
    : "bg-neutral-bg2 text-text-muted";

  const scoreFragment = ready && typeof confidence === "number"
    ? `${confidence}/100`
    : null;

  /* Only render as an interactive disclosure when there is a rationale
     to reveal. Loading / errored / rationale-less states stay as a
     static pill so we don't lie about expandability. */
  const hasRationale = ready && rationale.length > 0;
  const [expanded, setExpanded] = useState(false);

  /* Title still carries the full rationale so a quick hover (without
     committing a click) still surfaces the why for power users. */
  const longTitle = [longLabel, scoreFragment, rationale].filter(Boolean).join(" — ");

  /* Compact header line — verdict label + score, always rendered. The
     score separator pipe is hidden when there is no score (loading /
     error states) so the header reads cleanly. */
  const header = (
    <span className="flex items-center gap-1.5 min-w-0">
      <span className="font-semibold">{label}</span>
      {scoreFragment && (
        <>
          <span className="opacity-50">|</span>
          <span
            data-testid={`credibility-confidence-${sid}`}
            className="font-mono tabular-nums font-semibold"
          >
            {scoreFragment}
          </span>
        </>
      )}
      {hasRationale && (
        <ChevronDown
          className={[
            "ml-auto h-3.5 w-3.5 shrink-0 opacity-60 transition-transform",
            expanded ? "rotate-180" : "",
          ].join(" ")}
          aria-hidden="true"
        />
      )}
    </span>
  );

  /* Static (non-interactive) shape for the no-rationale cases. */
  if (!hasRationale) {
    return (
      <section
        data-testid={`credibility-subpanel-${sid}`}
        data-classification={ready ? cls : status}
        className={[
          "rounded px-2 py-1 text-xs leading-snug",
          fill,
        ].join(" ")}
        title={longTitle}
      >
        <p data-testid={`credibility-line-${sid}`} className="line-clamp-2">
          {header}
        </p>
      </section>
    );
  }

  /* Interactive disclosure: header is a clickable button; rationale
     expands beneath it with a subtle border to separate the verdict
     row from the explanation. Click anywhere on the chip area toggles
     so the operator doesn't have to hit the tiny chevron. */
  return (
    <section
      data-testid={`credibility-subpanel-${sid}`}
      data-classification={ready ? cls : status}
      data-expanded={expanded}
      className={[
        "rounded text-xs leading-snug",
        fill,
      ].join(" ")}
    >
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
        aria-expanded={expanded}
        aria-controls={`credibility-rationale-${sid}`}
        className="w-full text-left px-2 py-1 flex items-center gap-1.5 rounded hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
        title={expanded ? "Hide rationale" : "Show rationale"}
      >
        {header}
      </button>
      {expanded && (
        <p
          id={`credibility-rationale-${sid}`}
          data-testid={`credibility-rationale-${sid}`}
          className="px-2 pb-1.5 pt-0.5 opacity-90 border-t border-black/10"
        >
          {rationale}
        </p>
      )}
    </section>
  );
}

interface InvestigateSubpanelProps {
  onInvestigate: () => void;
  station: string;
  sid: string;
}

/* InvestigateSubpanel — RETIRED 2026-05-21.
 *
 * Replaced by an icon-only button anchored to the extreme right of the
 * head row inside SituationCard. The subpanel-shaped Investigate card
 * read as a heavyweight per-card affordance in a panel that already
 * stacks a Credibility subpanel + footer actions; the operator brief
 * was "investigate should be much smaller \u2014 button on extreme right
 * of the situation header, not in its own panel". Function kept as a
 * stub for one release so any out-of-tree caller fails loudly.
 */
function InvestigateSubpanel(_props: InvestigateSubpanelProps): null {
  return null;
}
void InvestigateSubpanel;

