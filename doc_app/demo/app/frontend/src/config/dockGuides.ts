/**
 * Dock assistant guides — static help content for the center-tab assistant.
 *
 * Displayed as a collapsible section at the top of the dock message area.
 * Keyed by agent ID matching agent_config.yaml dock agent definitions.
 *
 * Hard rule (per data-boundary mandate, 2026-05-01): no real station codes,
 * dates, or equipment identifiers may appear in this file. Use placeholder
 * tokens (`<STATION_CODE>`, `<start-time>`, `<end-time>`).
 */

export const DOCK_GUIDES: Record<string, { title: string; content: string }> = {
  data_assistant: {
    title: "How to use Data Search Assistant",
    content: `**Data Search Assistant** searches operational data, topology, procedures, near-hit reports, investigation clues, and participant records.

**Available Tools:**
- Operational: \`find_asset\`, \`find_alarms\`, \`find_scada\`, \`find_alarm_by_mrid\`, \`query_kql\`
- Topology: graph station/equipment/bus/neighbour tools, plus \`query_gremlin\`
- Knowledge: \`search_paws\`, \`search_nearhit_reports\`, \`search_investigation_clues\`

**Example queries (replace placeholders with the station you are working on):**
- "What equipment is at <STATION_CODE>?"
- "Show alarms at <STATION_CODE> between <start-time> and <end-time>"
- "What stations are adjacent to <STATION_CODE>?"
- "What is connected to <STATION_CODE> <bus>?"
- "What procedure covers restoring a 220kV bus after a protection trip?"
- "Who owns and operates <STATION_CODE>?"

**Tips:**
- Get CIM MRIDs from an equipment lookup before asking for MRID-specific graph details.
- Natural-language KB queries work well; include alarm labels, SCADA patterns, station names, or equipment names when you have them.
- Ask for a cross-search when you want the assistant to use more than one source family.`,
  },
};
