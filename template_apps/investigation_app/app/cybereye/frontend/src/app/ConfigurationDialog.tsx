import { RefObject, useState } from "react";
import { Activity, Database, LogOut, X } from "lucide-react";
import { signOut, type Caller } from "../shared/api";
import type { AgentIdentity } from "../shared/types";

interface Props {
  dialog: RefObject<HTMLDialogElement | null>;
  health: "checking" | "ok" | "degraded";
  caller: Caller | null;
  investigator: AgentIdentity | null;
}

export function ConfigurationDialog({ dialog, health, caller, investigator }: Props) {
  const [signOutError, setSignOutError] = useState("");
  // The workstation composition authenticates the loopback interface, so there is no session to
  // end and a "Sign out" button would be a control that does nothing.
  const localPreview = caller?.issuer === "local-preview";

  return (
    <dialog ref={dialog} id="configuration-window" className="configuration-dialog"
            aria-labelledby="configuration-title"
            onClick={(event) => {
              if (event.target !== event.currentTarget) return;
              const bounds = event.currentTarget.getBoundingClientRect();
              if (event.clientX < bounds.left || event.clientX > bounds.right
                  || event.clientY < bounds.top || event.clientY > bounds.bottom) {
                event.currentTarget.close();
              }
            }}>
      <div className="configuration-heading">
        <h2 id="configuration-title">Configuration</h2>
        <button type="button" className="configuration-close" aria-label="Close configuration"
                title="Close configuration" autoFocus onClick={() => dialog.current?.close()}>
          <X size={19} aria-hidden="true" />
        </button>
      </div>
      <dl className="configuration-details">
        <div>
          <dt><Database size={14} aria-hidden="true" /> ADX</dt>
          <dd className="configuration-health"><span className={`health-dot ${health}`} />{health}</dd>
        </div>
        <div>
          <dt><Activity size={14} aria-hidden="true" /> Model</dt>
          <dd>{investigator?.model ?? "Unavailable"}</dd>
        </div>
        <div>
          <dt><Database size={14} aria-hidden="true" /> Perth table</dt>
          <dd>15,520 events</dd>
        </div>
        <div data-testid="identity-chip">
          <dt>{localPreview ? "Local preview" : caller ? "Signed in" : "Identity"}</dt>
          <dd title={caller?.id}>{caller ? caller.display || caller.id : "Unavailable"}</dd>
        </div>
      </dl>
      {caller && !localPreview && (
        <div className="configuration-actions">
            <button type="button" className="sign-out" data-testid="sign-out"
                    onClick={() => {
                      setSignOutError("");
                      // A failed revocation must leave the person where they are. Navigating
                      // to the signed-out page with a live cookie would tell them they had
                      // signed out when they had not.
                      signOut().catch((error: unknown) => setSignOutError(
                        error instanceof Error ? error.message : "sign-out failed; try again",
                      ));
                    }}>
              <LogOut size={13} aria-hidden="true" /> Sign out
            </button>
          {signOutError && (
            <span className="sign-out-error error-box" role="alert" data-testid="sign-out-error">
              {signOutError}
            </span>
          )}
        </div>
      )}
    </dialog>
  );
}
