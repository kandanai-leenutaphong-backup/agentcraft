/**
 * Default suggested queries per agent — shown as clickable pills
 * when the chat is empty and a session is active.
 *
 * Keyed by agent ID. Disappear after the first message is sent.
 *
 * Hard rule (per data-boundary mandate, 2026-05-01): no real station
 * codes, equipment IDs, dates, or operational signal counts in this
 * file. Use synthetic, deliberately generic copy only. Operators
 * replace these with scenario-specific quick-links via the saved-
 * session picker.
 *
 * Couturier v2 R9 (downgraded to R9a): the previous strings shipped
 * literal `<STATION_CODE>` / `<start-time>` template syntax that
 * rendered verbatim in production. First-turn users saw what looked
 * like leaked dev fixtures. The strings below are curated, realistic-
 * sounding examples with zero `<...>` placeholders. They do not name
 * any real station, equipment id, or event. R9b (a click-to-fill
 * picker overlay) was downgraded in this run because no
 * `/api/stations` endpoint exists — see audit Sidebars for the
 * backend-contract request.
 */

export const DEFAULT_SUGGESTIONS: Record<string, string[]> = {
  grid_manager: [
    "Investigate the most recent critical situation",
    "Summarise alarms from the last hour",
    "What changed across the grid in the last 15 minutes?",
    "Walk me through the current operating state",
  ],
  data_assistant: [
    "What equipment categories does the asset registry track?",
    "Explain how the topology graph models bus connectivity",
    "Procedure for restoring a 220 kV bus after a protection trip",
    "What information is available about substation ownership?",
  ],
};
