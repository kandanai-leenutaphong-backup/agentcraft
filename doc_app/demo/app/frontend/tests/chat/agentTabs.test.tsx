import { beforeEach, describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

vi.mock("@/api/client", () => ({
  sendMessage: vi.fn(),
  streamChat: vi.fn(),
  abortGeneration: vi.fn(),
  getSession: vi.fn(),
}));

import * as api from "@/api/client";
import { AgentTabBar } from "@/components/chat/AgentTabBar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { useAgentStore } from "@/stores/agentStore";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";

describe("core agent tabs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });
    useChatStore.getState().clearAll();
    useAgentStore.setState({
      agents: [
        {
          id: "placeholder",
          name: "Investigator",
          description: "Primary investigation agent.",
          tools: [],
          is_default: true,
          tool_count: 0,
        },
        {
          id: "dispatcher",
          name: "Operator",
          description: "Action synthesis agent.",
          tools: [],
          is_default: false,
          tool_count: 0,
        },
      ],
      activeAgentId: "placeholder",
      returnToAgentId: null,
      delegatedAgents: [],
    });
    useSessionStore.setState({
      sessions: [],
      activeSessionId: "session-1",
      activeSession: null,
      loading: false,
      error: null,
    });
  });

  test("renders all configured agents before any delegation happens", () => {
    render(<AgentTabBar />);

    expect(screen.getByTestId("agent-tab-placeholder")).toBeTruthy();
    expect(screen.getByTestId("agent-tab-dispatcher")).toBeTruthy();
  });

  test("routes chat input to the selected agent tab", async () => {
    vi.mocked(api.streamChat).mockResolvedValue(undefined);
    useAgentStore.getState().setActiveAgent("dispatcher");

    render(<ChatPanel />);

    const input = screen.getByLabelText("Chat message input");
    fireEvent.change(input, { target: { value: "Give me operator actions" } });
    fireEvent.input(input, { target: { value: "Give me operator actions" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    expect(api.streamChat).toHaveBeenCalledWith(
      "session-1",
      expect.objectContaining({
        content: "Give me operator actions",
        max_context_turns: 10,
      }),
      expect.any(Object),
      expect.any(AbortSignal),
      "dispatcher",
    );
  });

  test("shows dispatcher background status from the session", () => {
    useAgentStore.getState().setActiveAgent("dispatcher");
    useSessionStore.setState({
      activeSession: {
        id: "session-1",
        title: "Investigation",
        schema_version: 3,
        scenario_name: "",
        user_id: "",
        threads: {},
        background_runs: {
          dispatcher: {
            run_id: "run-1",
            agent_id: "dispatcher",
            source_agent_id: "placeholder",
            status: "running",
            requested_task: "Prepare actions",
            queued_at: new Date().toISOString(),
            started_at: new Date().toISOString(),
            completed_at: null,
            error: null,
          },
        },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });

    render(<ChatPanel />);

    expect(screen.getByText("Operator is working in the background.")).toBeTruthy();
  });
});