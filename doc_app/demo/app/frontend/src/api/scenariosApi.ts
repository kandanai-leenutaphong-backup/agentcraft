/**
 * Scenarios API — fetch historical test-scenario triggers.
 *
 * Wire contract: ``GET /api/evaluations/scenarios/triggers`` returns a
 * list of scenarios with their detector-scan trigger window. The
 * payload originates from ``data_processors/evaluations/scenarios/``;
 * this client never hardcodes station codes or event timestamps —
 * those values live exclusively in the in-repo yaml files (the only
 * place permitted to hold real public-AEMO derivatives, per §3 of the
 * project README).
 */

import { BASE, authHeaders, handleResponse } from "./client";

/** One historical test scenario as served by the backend. */
export interface ScenarioTrigger {
  scenario_id: string;
  name: string;
  description: string | null;
  trigger: {
    station: string;
    /** "YYYY-MM-DD HH:MM" — matches SituationParams wire format. */
    start: string;
    /** "YYYY-MM-DD HH:MM" — matches SituationParams wire format. */
    end: string;
  };
}

/** Fetch every in-repo scenario's trigger window. */
export async function listScenarioTriggers(): Promise<ScenarioTrigger[]> {
  const res = await fetch(`${BASE}/evaluations/scenarios/triggers`, {
    headers: await authHeaders(),
  });
  return handleResponse<ScenarioTrigger[]>(res);
}
