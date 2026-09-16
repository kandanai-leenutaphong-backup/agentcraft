/**
 * Workspace — single-canvas content host for the centre column.
 *
 * C1 (see specs/couturier_20260517_overhaul_proposal.md §"Tier C delivery —
 * staged C1 → C4") retired the 7-tab `CenterTabs` strip + Workshop overflow
 * dropdown + portal-position-recompute hack, replacing them with a compact
 * mode chip-row plus palette/keyboard switching.
 *
 * Why this shape:
 *   - The old tab strip (4 primary + Workshop dropdown) clipped at common
 *     viewport widths and required a portalled, scroll-tracked menu to
 *     escape its parent `overflow-x-auto` clip. Operators routinely missed
 *     the overflow. The hack is now gone.
 *   - All 7 modes are independently meaningful but only one is in-focus at
 *     a time. "Tabs" implies parallel availability; "workspace mode" is
 *     the honest framing.
 *   - Three switching mechanisms remain: digit keys 1–6 (useGlobalShortcuts),
 *     palette commands (CommandPalette), and this header chip-row. All
 *     three converge on the same `panelStore.centerTab` state.
 *   - The `panelStore.centerTab` / `setCenterTab` / `CenterTab` contract is
 *     preserved unchanged so consumers (SituationControlBar,
 *     PinnedSituationPanel, SituationAlertsPanel, useGlobalShortcuts,
 *     usePersistence, CommandPalette) need no edits.
 *   - Test-id surface preserved (`center-tab-bar`, `center-tab-{id}`,
 *     `center-tab-body-{id}`) so existing Playwright specs that click
 *     mode chips and assert body visibility continue to work without
 *     selector churn. The dropped surface area is the `center-tab-workshop`
 *     trigger + `center-tab-workshop-menu` (no longer exist).
 *
 * Mounting model: all 7 mode bodies stay mounted (hidden via CSS) so their
 * internal state — topology graph, dock query, tuning form, audit pagination
 * — survives a mode swap. Unchanged from CenterTabs.
 */

import { useCallback, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Activity,
  ClipboardCheck,
  Command as CommandIcon,
  ListChecks,
  Network,
  Pin,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { usePanelStore } from "@/stores/panelStore";
import { usePaletteStore } from "@/stores/paletteStore";
import type { CenterTab } from "@/stores/panelStore";
import { PriorityActionsPanel } from "./PriorityActionsPanel";
import { GridStatusPanel } from "./GridStatusPanel";
import { PinnedSituationPanel } from "./PinnedSituationPanel";
import { SituationDetectorTuningPanel } from "./SituationDetectorTuningPanel";
import { SessionAuditPanel } from "./SessionAuditPanel";
import { TopologyPanel } from "@/components/topology";
import { DockContent } from "@/components/lookup/LookupDock";
import { useVocab } from "@/stores/vocabularyStore";

/* Mode definition shape — id matches `CenterTab` so the chip click and the
   store action share one symbol. `digit` is the keyboard shortcut already
   wired in useGlobalShortcuts, surfaced here as a discoverability hint. */
type ModeDef = {
  id: CenterTab;
  label: string;
  icon: typeof Network;
  digit: string;
};

/* Primary modes — the surfaces an operator reaches for in the course of
   normal incident response. Order matches the digit-key wiring in
   useGlobalShortcuts. */
const PRIMARY_MODES: ModeDef[] = [
  { id: "priorities", label: "Priorities",  icon: ListChecks, digit: "1" },
  { id: "situation",  label: "Situation",   icon: Pin,        digit: "2" },
  { id: "status",     label: "Grid Status", icon: Activity,   digit: "3" },
  { id: "topology",   label: "Topology",    icon: Network,    digit: "4" },
];

/* Workshop modes — developer / config surfaces. Visually subdued in the
   chip-row but still one click away (no dropdown, no portal). The
   "evaluations" mode has no digit shortcut by design — palette only. */
const WORKSHOP_MODES: ModeDef[] = [
  { id: "data",        label: "Data Search",      icon: Search,             digit: "5" },
  { id: "tuning",      label: "Detector Tuning",  icon: SlidersHorizontal,  digit: "6" },
  { id: "evaluations", label: "System Evaluations", icon: ClipboardCheck,   digit: "" },
];

/**
 * ModeChip — one button in the workspace mode chip-row.
 *
 * 2026-05-17 follow-up: chips bumped to h-9 + h-4 icons, each chip
 * shows an on-surface popover (not the native `title` tooltip) with
 * the full label + keyboard hint. Operator brief: "popup when you
 * mouse over them to enable very quick navigation … buttons should be
 * larger and easier to see … reducing visual strain".
 *
 * 2026-05-18 fix: popovers are now portalled to `document.body` and
 * positioned via `getBoundingClientRect` on the chip wrapper, so they
 * escape the centre panel's `overflow-hidden` clip (which used to
 * truncate the leftmost chip's popover against the left-column edge).
 * Hover/focus state is now React-managed (was pure CSS group-hover);
 * the trade-off is +1 useState per chip vs reliable rendering outside
 * any clipping ancestor.
 *
 * `workshop` styles the chip slightly subdued so the operator's eye
 * still parses primary vs workshop hierarchy without a dropdown.
 */
function ModeChip({
  mode,
  active,
  workshop,
  onSelect,
  onKeyDown,
}: {
  mode: ModeDef;
  active: boolean;
  workshop: boolean;
  onSelect: (id: CenterTab) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLButtonElement>, id: CenterTab) => void;
}) {
  const { id, label, icon: Icon, digit } = mode;
  const wrapperRef = useRef<HTMLSpanElement>(null);
  /* `popoverPos` carries the viewport coords for the portalled popover.
     When null, no popover is rendered. We update it on the same event
     that flips `hovered` so the popover doesn't render briefly at the
     wrong location during the first frame. */
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);

  /* Active = elevated chip with label + accent underline.
     Inactive = icon-only button.
     Workshop = inactive baseline is more subdued. */
  const base = "flex items-center gap-1.5 h-9 px-2.5 rounded-md transition-colors whitespace-nowrap";
  const tone = active
    ? "bg-neutral-bg2 text-text-primary"
    : workshop
      ? "text-text-muted hover:text-text-primary hover:bg-neutral-bg2"
      : "text-text-secondary hover:text-text-primary hover:bg-neutral-bg2";

  /* Compute viewport coords for the popover from the wrapper's rect.
     Placed centred below the chip with a 6px gap. */
  const showPopover = useCallback(() => {
    const r = wrapperRef.current?.getBoundingClientRect();
    if (!r) return;
    setPopoverPos({ top: r.bottom + 6, left: r.left + r.width / 2 });
  }, []);
  const hidePopover = useCallback(() => setPopoverPos(null), []);

  return (
    <span
      ref={wrapperRef}
      className="relative"
      onMouseEnter={showPopover}
      onMouseLeave={hidePopover}
      onFocus={showPopover}
      onBlur={hidePopover}
    >
      <button
        data-testid={`center-tab-${id}`}
        role="tab"
        aria-selected={active}
        aria-controls={`center-tab-body-${id}`}
        aria-label={label}
        id={`center-tab-${id}`}
        tabIndex={active ? 0 : -1}
        onClick={() => onSelect(id)}
        onKeyDown={(e) => onKeyDown(e, id)}
        className={[
          base,
          tone,
          active ? "border-b-2 border-accent -mb-px" : "",
        ].join(" ")}
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        {/* Active chip carries the label inline; inactive chips rely
            on the hover popover for the label. */}
        {active ? (
          <span className="text-sm font-medium">{label}</span>
        ) : (
          <span className="sr-only">{label}</span>
        )}
      </button>
      {/* Portalled popover — escapes the centre panel's overflow-hidden
          clip. `position: fixed` with viewport coords computed from
          the chip's bounding rect. `pointer-events-none` so the
          popover never steals the mouse. `transform: translateX(-50%)`
          centres it horizontally over the chip. */}
      {popoverPos && createPortal(
        <span
          role="tooltip"
          data-testid={`center-tab-${id}-popover`}
          style={{
            position: "fixed",
            top: popoverPos.top,
            left: popoverPos.left,
            transform: "translateX(-50%)",
            zIndex: 50,
          }}
          className="pointer-events-none rounded-md border border-border bg-neutral-bg3 px-2 py-1 shadow-lg flex items-center gap-2 whitespace-nowrap"
        >
          <span className="text-xs font-semibold text-text-primary">{label}</span>
          {digit && (
            <kbd className="text-micro font-mono uppercase tracking-wider text-text-muted border border-border rounded px-1 py-px">
              {digit}
            </kbd>
          )}
        </span>,
        document.body,
      )}
    </span>
  );
}

export function Workspace() {
  const centerTab = usePanelStore((s) => s.centerTab);
  const setCenterTab = usePanelStore((s) => s.setCenterTab);
  const openPalette = usePaletteStore((s) => s.openPalette);
  const tablistRef = useRef<HTMLDivElement>(null);
  const statusLabel = useVocab("systemStatusLabel");
  /* Hide the grid "Detector Tuning" surface in domains (e.g. SOC) whose
     alerts arrive pre-formed — the detector dials have no meaning there. */
  const showDetectorTuning = useVocab("showDetectorTuning");
  const primaryModes = PRIMARY_MODES.map((mode) => mode.id === "status" ? { ...mode, label: statusLabel } : mode);
  const workshopModes = showDetectorTuning ? WORKSHOP_MODES : WORKSHOP_MODES.filter((m) => m.id !== "tuning");
  const allModes = [...primaryModes, ...workshopModes];

  /* Keyboard roving across the chip-row. ArrowLeft / ArrowRight cycle
     focus across all 7 mode chips (primary + workshop, single linear
     order). Home / End jump to the ends. The selection itself is not
     changed by arrow keys — Tab/Enter or click commits, matching the
     WAI-ARIA tabs pattern used by the old CenterTabs strip. */
  const onModeKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>) => {
      if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const buttons = tablistRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="tab"]',
      );
      if (!buttons || buttons.length === 0) return;
      const current = document.activeElement as HTMLElement | null;
      const idx = current ? Array.from(buttons).indexOf(current as HTMLButtonElement) : -1;
      const total = buttons.length;
      let next = idx;
      if (e.key === "ArrowRight") next = (idx + 1 + total) % total;
      else if (e.key === "ArrowLeft") next = (idx - 1 + total) % total;
      else if (e.key === "Home") next = 0;
      else if (e.key === "End") next = total - 1;
      buttons[next]?.focus();
    },
    [],
  );

  return (
    <div data-spotlight-id="panel-center" className="h-full flex flex-col min-h-0">
      {/* Mode chip-row — compact replacement for the old CenterTabs strip.
          Single horizontal row, no overflow, no portal. Primary modes
          left; workshop modes right of a thin divider. Far right: a
          permanent palette-open affordance (addresses audit S-009 —
          command palette previously had no on-surface entry point).
          2026-05-17 follow-up: row grew from h-9 → h-11 so the new
          taller chips + hover popovers fit without clipping. */}
      <div
        ref={tablistRef}
        data-testid="center-tab-bar"
        role="tablist"
        aria-label="Workspace modes"
        className="flex items-center gap-1 px-2 h-11 shrink-0 border-b border-border bg-neutral-bg1"
      >
        {primaryModes.map((mode) => (
          <ModeChip
            key={mode.id}
            mode={mode}
            active={centerTab === mode.id}
            workshop={false}
            onSelect={setCenterTab}
            onKeyDown={onModeKeyDown}
          />
        ))}
        {/* Divider between primary and workshop — a thin vertical rule so
            the eye still parses the two groups even though the dropdown
            is gone. */}
        <div className="mx-1 h-4 w-px bg-divider" aria-hidden="true" />
        {workshopModes.map((mode) => (
          <ModeChip
            key={mode.id}
            mode={mode}
            active={centerTab === mode.id}
            workshop={true}
            onSelect={setCenterTab}
            onKeyDown={onModeKeyDown}
          />
        ))}
        <div className="flex-1" />
        {/* Switch-view affordance — opens the existing command palette.
            Previously discoverable only via Cmd-K keyboard shortcut
            (audit S-009). Surface it permanently in the workspace
            header so operators reach for it instead of memorising
            keyboard shortcuts. */}
        <button
          data-testid="workspace-switch-view"
          type="button"
          onClick={() => openPalette()}
          title="Open command palette (⌘K)"
          aria-label="Open command palette"
          className="flex items-center gap-1.5 h-9 px-2.5 rounded-md text-text-muted hover:text-text-primary hover:bg-neutral-bg2 transition-colors"
        >
          <CommandIcon className="h-4 w-4" aria-hidden="true" />
          <span className="text-xs font-mono uppercase tracking-wider">⌘K</span>
        </button>
      </div>

      {/* Mode bodies — every body stays mounted; only one is visible at a
          time. This preserves topology graph state, dock query state,
          tuning form state, audit pagination across mode swaps. The
          `center-tab-body-{id}` test-ids are unchanged from CenterTabs
          so existing Playwright specs that assert body visibility
          continue to work without selector churn. */}
      <div className="flex-1 min-h-0 overflow-hidden relative">
        {allModes.map((mode) => {
          const visible = centerTab === mode.id;
          /* Per-mode wrapper class — most modes scroll vertically, the
             "situation" pinned panel manages its own overflow, and
             "topology" needs padding around the canvas. Preserved
             one-for-one from the old CenterTabs body wrappers so the
             visual rhythm of each mode is unchanged. */
          let cls: string;
          if (mode.id === "priorities") cls = visible ? "h-full overflow-y-auto" : "hidden";
          else if (mode.id === "situation") cls = visible ? "h-full" : "hidden";
          else if (mode.id === "status") cls = visible ? "h-full overflow-y-auto" : "hidden";
          else if (mode.id === "topology") cls = visible ? "h-full p-3" : "hidden";
          else cls = visible ? "h-full" : "hidden";
          return (
            <div
              key={mode.id}
              className={cls}
              role="tabpanel"
              id={`center-tab-body-${mode.id}`}
              aria-labelledby={`center-tab-${mode.id}`}
              data-testid={`center-tab-body-${mode.id}`}
            >
              {/* Mode body content — same components, same wrappers as the
                  old CenterTabs. The "priorities" + "status" bodies
                  retain their `p-3` outer padding for visual rhythm. */}
              {mode.id === "priorities" && <div className="p-3"><PriorityActionsPanel /></div>}
              {mode.id === "situation" && <PinnedSituationPanel />}
              {mode.id === "status" && <GridStatusPanel />}
              {mode.id === "topology" && <TopologyPanel />}
              {mode.id === "data" && <DockContent />}
              {mode.id === "tuning" && <SituationDetectorTuningPanel />}
              {mode.id === "evaluations" && <SessionAuditPanel />}
            </div>
          );
        })}
      </div>
    </div>
  );
}
