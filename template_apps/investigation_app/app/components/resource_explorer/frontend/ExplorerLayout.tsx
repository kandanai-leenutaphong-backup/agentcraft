import type { ReactNode, RefObject } from "react";

export interface ExplorerLayoutProps {
  navigation?: ReactNode;
  agents: ReactNode;
  heading: ReactNode;
  subtitle?: string;
  children: ReactNode;
  viewerRef?: RefObject<HTMLElement | null>;
  testId?: string;
}

export function ExplorerLayout({ navigation, agents, heading, subtitle, children, viewerRef,
  testId = "resource-explorer" }: ExplorerLayoutProps) {
  const hasSources = navigation != null;
  return <section className={`rex-shell${hasSources ? "" : " rex-shell-agents"}`}
    aria-label={hasSources ? "Data sources, agents and tools" : "Agents and tools"} data-testid={testId}>
    {hasSources && <div className="rex-navigation rex-sources">{navigation}</div>}
    <aside className="rex-navigation rex-agents" aria-label="Agents">{agents}</aside>
    <section className="rex-viewer" aria-label="Selected item viewer" ref={viewerRef}>
      <header className="rex-header rex-viewer-head">
        <h2>{heading}</h2>
        {subtitle && <span>{subtitle}</span>}
      </header>
      {children}
    </section>
  </section>;
}