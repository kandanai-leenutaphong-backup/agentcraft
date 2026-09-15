import { Eye, Trash2, X } from "lucide-react";
import type { GraphEntity } from "../../shared/types";

const CLASS_NOUN: Record<string, string> = {
  Host: "host", Identity: "account", KerberosService: "service principal",
  VaultSafe: "vault safe", SoftwareReference: "tool", Domain: "domain", IpAddress: "address",
};

interface Props {
  picked: GraphEntity[];
  max: number;
  onRemove: (id: string) => void;
  onClear: () => void;
  onVisualize: () => void;
}

/** Collects entities clicked in the analysis so several can be compared in one graph. */
export function EntityTray({ picked, max, onRemove, onClear, onVisualize }: Props) {
  if (picked.length === 0) return null;
  const full = picked.length >= max;
  return (
    <aside className="entity-tray" aria-label="Selected entities">
      <header>
        <b>{picked.length} selected</b>
        <button type="button" onClick={onClear} aria-label="Clear the selection"><Trash2 size={12} /></button>
      </header>
      <ul>
        {picked.map((entity) => (
          <li key={entity.id} className={entity.label.toLowerCase()}>
            <span className="entity-tray-name">{entity.name}</span>
            <small>{CLASS_NOUN[entity.label] ?? entity.label}</small>
            <button type="button" onClick={() => onRemove(entity.id)} aria-label={`Remove ${entity.name}`}>
              <X size={11} />
            </button>
          </li>
        ))}
      </ul>
      <p className="entity-tray-hint">
        {picked.length === 1
          ? "Click another entity to see how the two connect, or visualize this one alone."
          : `The graph will show just these ${picked.length} and the relationships between them.`}
        {full && " Selection is full."}
      </p>
      <button type="button" className="entity-tray-go" onClick={onVisualize}>
        <Eye size={13} /> Visualize {picked.length === 1 ? "entity" : `${picked.length} entities`}
      </button>
    </aside>
  );
}
