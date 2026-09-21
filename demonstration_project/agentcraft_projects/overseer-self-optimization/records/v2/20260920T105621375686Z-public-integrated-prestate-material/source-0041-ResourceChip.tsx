import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";

/** Stable resource ids are long and repetitive; show the discriminating tail by default. */
export const RESOURCE_ID = /^event:\/\/[\w.:-]+$/;

function shorthand(value: string): string {
  const parts = value.split(":");
  const tail = parts[parts.length - 1] ?? value;
  const family = parts[2]?.split(".").pop() ?? "event";
  return `${family}…${tail.slice(0, 8)}`;
}

export function ResourceChip({ value }: { value: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function activate() {
    setOpen((value) => !value);
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <span className={`resource-chip ${open ? "open" : ""}`}>
      <button type="button" onClick={activate} title={value}
              aria-label={`Resource id ${value}. Activate to expand and copy.`}>
        {copied ? <Check size={10} /> : <Copy size={10} />}
        <code>{open ? value : shorthand(value)}</code>
      </button>
      {copied && <span role="status" className="resource-copied">copied</span>}
    </span>
  );
}
