/**
 * PanelLayout — GridIQ workspace shell.
 *
 * Always-on 3-column control room (the short-lived chat-first toggle
 * from Couturier v2 R1 was retired; the workspace is the only first-paint
 * surface now).
 *   Left   (25 %): Situation alerts + scan controls
 *   Center (45 %): Workspace (priorities / situation / status / topology /
 *                  data / tuning / evaluations — single canvas, palette-
 *                  driven; replaced the CenterTabs strip + Workshop
 *                  overflow dropdown in C1 of the 2026-05-17 overhaul).
 *   Right  (30 %): Chat panel (Ask GridIQ)
 * Columns are resizable via react-resizable-panels; sizes persist to
 * localStorage via autoSaveId.
 */

import { Group, Panel, Separator } from "react-resizable-panels";
import { ChatPanel } from "@/components/chat";
import { Workspace } from "./Workspace";
import { SituationAlertsPanel } from "./SituationAlertsPanel";
import { SituationControlBar } from "./SituationControlBar";

export function PanelLayout() {
  return (
    <div className="flex-1 flex overflow-hidden">
      <Group orientation="horizontal">
        {/* Left column — alerts take the full height; Grid Status has
            moved into a center-column tab so the alerts pane can breathe.
            The user-identity / switch-account / logout chip used to live
            at the bottom of this column; it was hoisted into the header
            (App.tsx) on 2026-05-18 so the alerts pane gets the full
            vertical run and the chip sits next to the wordmark on the
            top-right — the conventional location operators expect. */}
        <Panel defaultSize={25} minSize={15} className="flex flex-col">
          {/* Situation control bar — time range + scan */}
          <SituationControlBar />

          {/* Situation Alerts — full remaining height, scrollable. */}
          <div data-spotlight-id="panel-situations" className="flex-1 overflow-y-auto p-3 min-h-0">
            <SituationAlertsPanel />
          </div>
        </Panel>

        <Separator className="w-1 bg-divider hover:bg-brand transition-colors cursor-col-resize" />

        {/* Center column — Workspace single-canvas host. C1 (see
            specs/couturier_20260517_overhaul_proposal.md) retired the
            CenterTabs 7-tab strip + Workshop overflow dropdown in favour
            of a compact mode chip-row + palette/keyboard switching. */}
        <Panel defaultSize={45} minSize={20} className="overflow-hidden bg-center-panel-bg">
          <Workspace />
        </Panel>

        <Separator className="w-1 bg-divider hover:bg-brand transition-colors cursor-col-resize" />

        {/* Right column — Chat (Ask GridIQ) */}
        <Panel defaultSize={30} minSize={20}>
          <div data-spotlight-id="panel-chat" className="h-full max-h-full flex flex-col overflow-hidden bg-neutral-bg1">
            <div className="flex items-center justify-between px-3 pt-3 pb-1">
              <h3 className="text-xs uppercase tracking-wider text-text-muted font-bold flex items-center gap-2">
                <span className="text-brand">✦</span> Ask GridIQ
              </h3>
            </div>
            <div className="flex-1 overflow-hidden min-h-0">
              <ChatPanel />
            </div>
          </div>
        </Panel>
      </Group>
    </div>
  );
}
