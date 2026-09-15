import { KeyboardEvent, RefObject } from "react";
import { Settings } from "lucide-react";

/** Which workspace the shell is showing. The tab strip is the only control that changes it. */
export type Workspace = "investigation" | "explorer" | "agent-editor";

const TABS: { id: Workspace; label: string }[] = [
  { id: "investigation", label: "Investigation" },
  { id: "explorer", label: "Data & Tools Catalogue" },
  { id: "agent-editor", label: "Agent Editor" },
];

interface Props {
  workspace: Workspace;
  onWorkspaceChange: (workspace: Workspace) => void;
  configuration: RefObject<HTMLDialogElement | null>;
}

export function Header({ workspace, onWorkspaceChange, configuration }: Props) {
  function onTabKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = TABS.findIndex((tab) => tab.id === workspace);
    const next = event.key === "Home" ? TABS[0].id
      : event.key === "End" ? TABS[TABS.length - 1].id
      : event.key === "ArrowLeft" ? TABS[(index + TABS.length - 1) % TABS.length].id
      : event.key === "ArrowRight" ? TABS[(index + 1) % TABS.length].id : null;
    if (!next) return;
    event.preventDefault();
    onWorkspaceChange(next);
    document.getElementById(`tab-${next}`)?.focus();
  }

  return (
    <header className="topbar">
      <div className="wordmark"><span className="mark">C</span><div><b>CyberEye</b><small>Security operations workspace</small></div></div>
      <span className="replay-label">Historical replay</span>
      <div className="header-tabs" role="tablist" aria-label="Workspace" onKeyDown={onTabKeyDown}>
        {TABS.map(({ id, label }) => (
          <button key={id} type="button" role="tab" id={`tab-${id}`}
                  aria-selected={workspace === id} aria-controls={`workspace-${id}`}
                  tabIndex={workspace === id ? 0 : -1}
                  className={workspace === id ? "active" : ""}
                  onClick={() => onWorkspaceChange(id)}>{label}</button>
        ))}
      </div>
      <button type="button" className="configuration-toggle" aria-label="Configuration"
              title="Configuration" aria-haspopup="dialog" aria-controls="configuration-window"
              onClick={() => configuration.current?.showModal()}>
        <Settings size={19} aria-hidden="true" />
      </button>
    </header>
  );
}
