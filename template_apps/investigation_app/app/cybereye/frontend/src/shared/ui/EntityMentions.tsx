import { type ReactNode, useEffect, useState } from "react";
import { api } from "../api";
import type { GraphEntity } from "../types";

/** Classes whose names are distinctive enough to match inside prose without false hits. */
const LINKABLE = new Set(["Host", "Identity", "KerberosService", "VaultSafe",
  "SoftwareReference", "Domain", "IpAddress"]);

/** A short label an analyst recognises, used in the mention's tooltip. */
const CLASS_NOUN: Record<string, string> = {
  Host: "host", Identity: "account", KerberosService: "service principal",
  VaultSafe: "vault safe", SoftwareReference: "tool reference", Domain: "domain",
  IpAddress: "address", SecurityAlert: "alert", Session: "session", Application: "application",
};

export interface EntityIndex {
  pattern: RegExp | null;
  byName: Map<string, GraphEntity>;
}

const EMPTY: EntityIndex = { pattern: null, byName: new Map() };

function escape(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function buildEntityIndex(entities: GraphEntity[]): EntityIndex {
  const byName = new Map<string, GraphEntity>();
  for (const entity of entities) {
    if (!LINKABLE.has(entity.label) || entity.name.length < 3) continue;
    const key = entity.name.toLowerCase();
    const existing = byName.get(key);
    // Two classes can share a label (a sensor and a host both called SVPDS004); prefer the
    // one the telemetry saw more of rather than whichever the traversal returned first.
    if (!existing || entity.event_count > existing.event_count) byName.set(key, entity);
  }
  if (byName.size === 0) return EMPTY;
  // Longest first so SVPMN082$ wins over SVPMN082 at the same position.
  const names = [...byName.values()].map((entity) => entity.name)
    .sort((a, b) => b.length - a.length).map(escape);
  return {
    byName,
    pattern: new RegExp(`(?<![\\w.$-])(${names.join("|")})(?![\\w$-])`, "gi"),
  };
}

export function useEntityIndex(): EntityIndex {
  const [index, setIndex] = useState<EntityIndex>(EMPTY);
  useEffect(() => {
    let cancelled = false;
    api.graphEntities()
      .then((entities) => !cancelled && setIndex(buildEntityIndex(entities)))
      .catch(() => { /* mentions stay plain text when the graph is unavailable */ });
    return () => { cancelled = true; };
  }, []);
  return index;
}

/** Wrap every entity name in `text` with a control that opens it in the graph. */
export function linkEntities(
  text: string,
  index: EntityIndex,
  onOpen: (entity: GraphEntity) => void,
): ReactNode {
  if (!index.pattern || !text) return text;
  const parts: ReactNode[] = [];
  let cursor = 0;
  index.pattern.lastIndex = 0;
  for (let match = index.pattern.exec(text); match; match = index.pattern.exec(text)) {
    const entity = index.byName.get(match[0].toLowerCase());
    if (!entity) continue;
    if (match.index > cursor) parts.push(text.slice(cursor, match.index));
    parts.push(
      <button
        key={`${entity.id}-${match.index}`}
        type="button"
        className={`entity-mention ${entity.label.toLowerCase()}`}
        title={`${entity.name} — ${CLASS_NOUN[entity.label] ?? entity.label} · open in the graph`}
        onClick={() => onOpen(entity)}
      >
        {match[0]}
      </button>,
    );
    cursor = match.index + match[0].length;
  }
  if (parts.length === 0) return text;
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
}
