import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { getToolArgsRenderer, getToolResultRenderer } from "@/components/chat/tool-renderers";
import { JsonFallback } from "@/components/chat/tool-renderers/JsonFallback";
import { PanelToolSummary } from "@/components/chat/tool-renderers/PanelToolSummary";

const ACTIVE_TOOLS_WITH_CUSTOM_ARGS = [
  "get_schema_context",
  "get_nodes",
  "get_neighbors",
  "get_node_properties",
  "find_path",
  "count_nodes",
  "get_edges",
  "lookup_entity",
  "get_scada_readings",
  "get_scada_timeline",
  "summarize_scada",
  "get_scada_extremes",
  "get_alarm_sequence",
  "summarize_alarms",
  "get_entity_events",
  "search_operator_manual",
  "delegate_to_agent",
  "push_action",
  "search_incident_reports",
  "search_nearhit_reports",
];

describe("tool renderer registry", () => {
  test("provides purpose-built argument renderers for the active tool surface", () => {
    for (const toolName of ACTIVE_TOOLS_WITH_CUSTOM_ARGS) {
      expect(getToolArgsRenderer(toolName), `${toolName} should have a custom args renderer`).not.toBeNull();
    }
  });

  test("maps push_action to the compact panel summary renderer", () => {
    expect(getToolResultRenderer("push_action")).toBe(PanelToolSummary);
  });

  test("does not leave schema context or entity events on the JSON fallback renderer", () => {
    expect(getToolResultRenderer("get_schema_context")).not.toBe(JsonFallback);
    expect(getToolResultRenderer("get_entity_events")).not.toBe(JsonFallback);
  });
});

describe("specialized result renderers", () => {
  test("renders schema context as a readable document", () => {
    const Renderer = getToolResultRenderer("get_schema_context");

    render(<Renderer result={"# Schema\n\nGeneratingUnit\nConnectivityNode"} />);

    expect(screen.getByText("Reference document")).toBeTruthy();
    expect(screen.getByText(/GeneratingUnit/)).toBeTruthy();
  });

  test("renders entity events as separate scada and alarm sections", () => {
    const Renderer = getToolResultRenderer("get_entity_events");

    render(
      <Renderer
        result={JSON.stringify({
          entity_id: "entity-123",
          time_range: { start: "2021-05-25T13:33:00Z", end: "2021-05-25T13:35:00Z" },
          scada: {
            columns: [{ name: "timestamp_aest" }, { name: "Value" }],
            rows: [{ timestamp_aest: "2021-05-25T13:33:04Z", Value: -5 }],
          },
          alarms: {
            columns: [{ name: "timestamp_aest" }, { name: "alarm_text" }],
            rows: [{ timestamp_aest: "2021-05-25T13:33:02Z", alarm_text: "DC SUPPLY FAIL" }],
          },
        })}
      />,
    );

    expect(screen.getByText("SCADA readings")).toBeTruthy();
    expect(screen.getByText("Alarm events")).toBeTruthy();
    expect(screen.getByText("entity-123")).toBeTruthy();
    expect(screen.getByText("DC SUPPLY FAIL")).toBeTruthy();
  });
});