/**
 * What this surface is, for a reader who has opened it without being told.
 *
 * A native `<dialog>` opened with `showModal`, so focus containment, Escape,
 * and the inert backdrop come from the platform rather than from a hand-rolled
 * trap that will be wrong in one browser.
 */

import { useEffect, useRef, type JSX } from "react";

import { KIND_ICON, KIND_LABEL, KIND_MEANING } from "../api/kinds";
import { statusLabel, statusMeaning, statusRemedy, statusTone } from "../api/status";
import { NODE_KINDS, NODE_STATUSES } from "../api/wire";
import { Icon } from "./Icon";
import { Badge } from "./StatusNote";

const KEYS: [string, string][] = [
  ["↑ ↓", "move between the rows that are visible"],
  ["→", "open a branch, then step into it"],
  ["←", "close a branch, then step out to its parent"],
  ["Home / End", "jump to the first or last visible row"],
  ["Enter / Space", "show this node in the pane, and open or close it"],
  ["/", "jump to the estate search box"],
  ["Escape", "close this dialog"],
];

export function HelpDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}): JSX.Element {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      data-testid="help-dialog"
      aria-labelledby="help-title"
      onClose={onClose}
      className="w-[min(48rem,92vw)] rounded border border-border bg-canvas p-0 text-primary backdrop:bg-[rgba(20,17,13,0.45)]"
    >
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <h2 id="help-title" className="mr-auto text-base font-semibold">
          Reading this explorer
        </h2>
        <button
          type="button"
          onClick={onClose}
          data-testid="help-close"
          className="min-h-[44px] rounded border border-border px-3 text-sm"
        >
          Close
        </button>
      </div>

      <div className="max-h-[70vh] overflow-y-auto px-4 py-3">
        <p className="text-sm text-secondary">
          The tree is one Azure subscription, discovered live. Every level below the
          subscription is read from Azure when you open it — nothing here is configured
          by hand. Selecting a node shows what it is on the right; a node that holds
          bytes, documents or rows shows them under <strong>Contents</strong>.
        </p>
        <p className="mt-2 text-sm text-secondary">
          This surface only reads. It never creates, changes or deletes anything, and it
          never reads the value of a Key Vault secret.
        </p>

        <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-secondary">
          Keyboard
        </h3>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          {KEYS.map(([key, meaning]) => (
            <div key={key} className="contents">
              <dt className="whitespace-nowrap font-mono text-[12px] text-primary">{key}</dt>
              <dd className="text-[13px] text-secondary">{meaning}</dd>
            </div>
          ))}
        </dl>

        <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-secondary">
          What a branch&rsquo;s state means
        </h3>
        <ul className="mt-2 flex flex-col gap-2">
          {NODE_STATUSES.map((status) => (
            <li key={status} className="flex flex-wrap items-baseline gap-2">
              <Badge tone={statusTone(status)}>{statusLabel(status)}</Badge>
              <span className="min-w-0 flex-1 text-[13px] text-secondary">
                {statusMeaning(status)}{" "}
                <span className="text-muted">{statusRemedy(status)}</span>
              </span>
            </li>
          ))}
        </ul>

        <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-secondary">
          The kinds of node in the tree
        </h3>
        <ul data-testid="kind-legend" className="mt-2 flex flex-col gap-1.5 pb-2">
          {NODE_KINDS.map((kind) => (
            <li key={kind} className="flex items-start gap-2">
              <span className="mt-0.5 text-muted">
                <Icon name={KIND_ICON[kind]} />
              </span>
              <span className="min-w-0 flex-1 text-[13px]">
                <span className="font-semibold text-primary">{KIND_LABEL[kind]}</span>{" "}
                <span className="text-secondary">{KIND_MEANING[kind]}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </dialog>
  );
}
