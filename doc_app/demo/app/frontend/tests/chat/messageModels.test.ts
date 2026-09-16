import { describe, expect, test } from "vitest";

import type { ApiMessage } from "@/api/types";
import {
  buildFallbackAssistantMessage,
  normalizeMessage,
} from "@/features/chat/messageModels";

describe("messageModels", () => {
  test("normalizeMessage reconstructs parts for legacy transport messages", () => {
    const message: ApiMessage = {
      id: "m-1",
      role: "assistant",
      content: "Restored text",
      status: "complete",
      tool_calls: [],
      agent_name: "investigator",
      created_at: new Date().toISOString(),
    };

    const normalized = normalizeMessage(message);

    expect(normalized.parts).toEqual([{ type: "text", text: "Restored text" }]);
  });

  test("buildFallbackAssistantMessage creates a renderable error message", () => {
    const fallback = buildFallbackAssistantMessage("investigator", "error");

    expect(fallback.role).toBe("assistant");
    expect(fallback.status).toBe("error");
    expect(fallback.parts[0]).toEqual({ type: "text", text: "[Error building message]" });
  });
});