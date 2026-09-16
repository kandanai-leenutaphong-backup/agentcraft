import { beforeEach, describe, expect, test } from "vitest";

import { usePanelStore } from "@/stores/panelStore";

describe("panelStore disturbance summary", () => {
  beforeEach(() => {
    usePanelStore.setState({
      disturbanceSummary: null,
      operatingState: usePanelStore.getState().operatingState,
      priorityActions: null,
    });
  });

  test("starts with no disturbance summary until live data arrives", () => {
    expect(usePanelStore.getState().disturbanceSummary).toBeNull();
  });

  test("populates disturbance summary from update_disturbance_summary", () => {
    usePanelStore.getState().updatePanel("update_disturbance_summary", {
      event_type: "Voltage Collapse",
      location: "substation 275 kV",
      timestamp: "14:06:30 AEST",
      generation_lost_mw: 3045,
      load_shed_mw: 2300,
      units_affected: ["example equipment", "domain B2"],
      network_trips: ["QNI"],
      ufls_status: "Stage 2 triggered",
    });

    expect(usePanelStore.getState().disturbanceSummary).toEqual({
      event_type: "Voltage Collapse",
      location: "substation 275 kV",
      timestamp: "14:06:30 AEST",
      generation_lost_mw: 3045,
      load_shed_mw: 2300,
      units_affected: ["example equipment", "domain B2"],
      network_trips: ["QNI"],
      ufls_status: "Stage 2 triggered",
    });
  });

  test("starts with the seeded degraded operating state", () => {
    const operatingState = usePanelStore.getState().operatingState;

    expect(operatingState).not.toBeNull();
    expect(operatingState?.checks.every((check) => check.status === "fail" || check.name === "Telemetry intact")).toBe(true);
    expect(operatingState?.checks.find((check) => check.name === "Telemetry intact")?.status).toBe("pass");
  });

  test("stores priority actions using action reasoning and guide", () => {
    usePanelStore.getState().updatePanel("push_action", {
      action: "Open the C4 feeder breaker",
      reasoning: "## Evidence\n\n- Active power reversed from +278 MW to -5 MW.\n- Protection remained unavailable.",
      guide: "1. Confirm breaker tagging with the field team.\n2. Open the C4 feeder breaker.\n3. Confirm power reversal clears.",
      priority: 4,
    });

    const result = usePanelStore.getState().priorityActions;
    expect(result?.actions[0]?.action).toBe("Open the C4 feeder breaker");
    expect(result?.actions[0]?.priority).toBe(4);
    expect(result?.actions[0]?.pinned).toBe(false);
  });

  test("rehydrates priority actions from persisted push_action tool calls", () => {
    usePanelStore.getState().syncPriorityActionsFromThreads({
      dispatcher: {
        agent_session_id: "thread-1",
        agent_id: "dispatcher",
        agent_name: "Operator",
        created_at: new Date().toISOString(),
        messages: [
          {
            id: "assistant-1",
            role: "assistant",
            content: "done",
            parts: null,
            status: "complete",
            agent_name: "dispatcher",
            created_at: new Date().toISOString(),
            context_snapshot: null,
            tool_calls: [
              {
                id: "call-1",
                name: "push_action",
                arguments: {
                  action: "Reduce transformer loading",
                  reasoning: "Live temperature trend is rising.",
                  guide: "1. Rebalance feeder demand.",
                },
                result: JSON.stringify({
                  panel: "priority_actions",
                  actions: [
                    {
                      step: 1,
                      action: "Reduce transformer loading",
                      reasoning: "Live temperature trend is rising.",
                      guide: "1. Rebalance feeder demand.",
                    },
                  ],
                }),
                status: "complete",
              },
            ],
          },
        ],
      },
    });

    expect(usePanelStore.getState().priorityActions?.actions[0]?.action).toBe(
      "Reduce transformer loading",
    );
  });

  test("preserves live priority actions when thread rehydration is still stale", () => {
    usePanelStore.getState().updatePanel("push_action", {
      action: "Open standby cooling feeder CB-2",
      reasoning: "Live dispatcher tool event already arrived.",
      guide: "1. Open the standby feeder.",
    });

    usePanelStore.getState().syncPriorityActionsFromThreads({
      dispatcher: {
        agent_session_id: "thread-1",
        agent_id: "dispatcher",
        agent_name: "Operator",
        created_at: new Date().toISOString(),
        messages: [],
      },
    });

    expect(usePanelStore.getState().priorityActions?.actions[0]?.action).toBe(
      "Open standby cooling feeder CB-2",
    );
  });

  test("auto-sorts actions by priority descending", () => {
    usePanelStore.getState().updatePanel("push_action", {
      action: "Low priority follow-up",
      reasoning: "r",
      guide: "g",
      priority: 2,
    });
    usePanelStore.getState().updatePanel("push_action", {
      action: "Critical safety action",
      reasoning: "r",
      guide: "g",
      priority: 5,
    });
    usePanelStore.getState().updatePanel("push_action", {
      action: "Standard action",
      reasoning: "r",
      guide: "g",
      priority: 3,
    });

    const actions = usePanelStore.getState().priorityActions!.actions;
    expect(actions.map((a) => a.action)).toEqual([
      "Critical safety action",
      "Standard action",
      "Low priority follow-up",
    ]);
    expect(actions.map((a) => a.step)).toEqual([1, 2, 3]);
  });

  test("pinned action stays in place when higher-priority action arrives", () => {
    usePanelStore.getState().updatePanel("push_action", {
      action: "First action",
      reasoning: "r",
      guide: "g",
      priority: 3,
    });

    usePanelStore.getState().togglePin(1);

    usePanelStore.getState().updatePanel("push_action", {
      action: "Higher priority action",
      reasoning: "r",
      guide: "g",
      priority: 5,
    });

    const actions = usePanelStore.getState().priorityActions!.actions;
    expect(actions[0].action).toBe("First action");
    expect(actions[0].pinned).toBe(true);
    expect(actions[1].action).toBe("Higher priority action");
  });
});