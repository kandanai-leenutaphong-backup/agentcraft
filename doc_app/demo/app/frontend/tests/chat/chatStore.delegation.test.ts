import { beforeEach, describe, expect, test, vi } from "vitest";

vi.mock("@/api/client", () => ({
  streamChat: vi.fn(),
  abortGeneration: vi.fn(),
  getSession: vi.fn(),
}));

import * as api from "@/api/client";
import { useChatStore } from "@/stores/chatStore";
import { usePanelStore } from "@/stores/panelStore";
import { useSessionStore } from "@/stores/sessionStore";

describe("chatStore delegation panel routing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.getState().clearAll();
    usePanelStore.setState({
      disturbanceSummary: null,
      operatingState: null,
      priorityActions: null,
    });
    useSessionStore.setState({
      activeSessionId: null,
      activeSession: null,
      sessions: [],
      loading: false,
      error: null,
    });
  });

  test("delegated push_action updates the priority actions panel", async () => {
    vi.mocked(api.streamChat).mockImplementation(async (_sessionId, _req, callbacks) => {
      callbacks.onDelegationToolEnd?.("dispatcher", "tool-1", "push_action", {
        action: "Open the station service feeder breaker",
        reasoning: "## Why now\n\n- Alarm sequence shows repeated DC undervoltage on the board.\n- Investigator flagged escalating auxiliary supply instability.",
        guide: "1. Confirm the affected auxiliary board on SCADA.\n2. Open the station service feeder breaker.\n3. Verify the board is isolated and stable.",
      });
    });

    await useChatStore.getState().sendMessage("session-1", "Investigate the DC fault", "placeholder");
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(usePanelStore.getState().priorityActions).toEqual({
      actions: [
        {
          step: 1,
          action: "Open the station service feeder breaker",
          reasoning: "## Why now\n\n- Alarm sequence shows repeated DC undervoltage on the board.\n- Investigator flagged escalating auxiliary supply instability.",
          guide: "1. Confirm the affected auxiliary board on SCADA.\n2. Open the station service feeder breaker.\n3. Verify the board is isolated and stable.",
        },
      ],
    });
  });

  test("session rehydration does not overwrite a locally streaming slice", () => {
    useChatStore.setState({
      slices: {
        dispatcher: {
          ...useChatStore.getState().getSlice("dispatcher"),
          status: "streaming",
          messages: [
            {
              id: "local-1",
              role: "assistant",
              content: "Local streaming content",
              parts: [{ type: "text", text: "Local streaming content" }],
              status: "streaming",
              tool_calls: [],
              agent_name: "dispatcher",
              created_at: new Date().toISOString(),
            },
          ],
        },
      },
    });

    useChatStore.getState().loadSessionMessages(
      {
        dispatcher: {
          agent_session_id: "thread-1",
          agent_id: "dispatcher",
          agent_name: "Operator",
          created_at: new Date().toISOString(),
          messages: [
            {
              id: "server-1",
              role: "assistant",
              content: "Server copy",
              parts: null,
              status: "complete",
              tool_calls: [],
              agent_name: "dispatcher",
              created_at: new Date().toISOString(),
            },
          ],
        },
      },
      "placeholder",
    );

    expect(useChatStore.getState().getSlice("dispatcher").messages[0]?.content).toBe(
      "Local streaming content",
    );
  });

  test("background tool events live-update the priority actions panel", async () => {
    useChatStore.getState().handleBackgroundEvent("dispatcher", "start", {
      task: "Publish immediate operator actions",
    });

    useChatStore.getState().handleBackgroundEvent("dispatcher", "tool_call_start", {
      id: "call-1",
      name: "push_action",
    });

    useChatStore.getState().handleBackgroundEvent("dispatcher", "tool_call_end", {
      id: "call-1",
      name: "push_action",
      arguments: {
        action: "Open the standby cooling feeder",
        reasoning: "Cooling bank A is unavailable and winding temperature is climbing.",
        guide: "1. Confirm the standby feeder is available.\n2. Open the standby cooling feeder.",
      },
    });

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(usePanelStore.getState().priorityActions).toEqual({
      actions: [
        {
          step: 1,
          action: "Open the standby cooling feeder",
          reasoning: "Cooling bank A is unavailable and winding temperature is climbing.",
          guide: "1. Confirm the standby feeder is available.\n2. Open the standby cooling feeder.",
        },
      ],
    });
    expect(useChatStore.getState().getSlice("dispatcher").status).toBe("streaming");
  });
});