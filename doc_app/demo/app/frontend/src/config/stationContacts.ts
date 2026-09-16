/**
 * Station contacts registry — synthetic placeholders for the demo UI.
 *
 * The SituationCard component shows a small list of standing contacts
 * for the focused station so operators can see at-a-glance where to
 * route a phone call. Real contact data is sourced from an integrated
 * directory in production deployments. This file exists only to keep
 * the demo UI populated; every value here is fabricated and does not
 * map to any real person, phone number, or email.
 *
 * Hard rules (per AUTODEV "Ops Data Protection"):
 *   - No real names.
 *   - No real phone numbers — use the +61-9-0000-XXXX reserved-test
 *     range or other clearly fake formats.
 *   - No real corporate email domains. Use `contacts.example` only.
 *   - No station-specific role descriptions that imply privileged
 *     knowledge of a real station (use generic role names).
 *
 * If you need real contacts, wire a contacts API in the backend and
 * fetch on demand under access control. Do not embed them in this
 * checked-in module.
 */

/** A generic station-level contact card. */
export interface GenericContact {
  name: string;
  role: string;
  phone: string;
  teams: string;
}

// Three synthetic generic contacts shown for any station the UI
// surfaces. The same three are returned regardless of station code,
// because they are placeholder content only — production replaces
// this with an authenticated directory lookup.
const GENERIC_PLACEHOLDER_CONTACTS: GenericContact[] = [
  { name: "Control Room (placeholder)", role: "Network Control Room", phone: "+61 9 0000 0001", teams: "control-room@contacts.example" },
  { name: "Field Crew Supervisor (placeholder)", role: "Field Crew Supervisor", phone: "+61 9 0000 0002", teams: "field-crew@contacts.example" },
  { name: "Station Operations (placeholder)", role: "Station Operations", phone: "+61 9 0000 0003", teams: "station-ops@contacts.example" },
];

/**
 * Station code → standing contacts.
 *
 * Implemented as a Proxy so any station code returns the same
 * synthetic placeholder list. This avoids per-station hardcoding
 * (which would invite re-introduction of real contact data) while
 * keeping the existing call site (`STATION_CONTACTS[sit.station]`)
 * working unchanged.
 */
export const STATION_CONTACTS: Record<string, GenericContact[]> = new Proxy(
  {},
  {
    get: () => GENERIC_PLACEHOLDER_CONTACTS,
  },
) as Record<string, GenericContact[]>;
