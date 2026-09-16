import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("react-resizable-panels", () => ({
  Group: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Panel: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  Separator: () => <div data-testid="panel-separator" />,
}));

vi.mock("@/auth/useAuth", () => ({
  useAuth: () => ({
    isAuthenticated: false,
    user: null,
    logout: vi.fn(),
    switchAccount: vi.fn(),
  }),
}));

vi.mock("@/components/chat", () => ({
  ChatPanel: () => <div>Chat Panel</div>,
}));

vi.mock("@/components/panels/OperatingStatePanel", () => ({
  OperatingStatePanel: () => <div>Operating State</div>,
}));

vi.mock("@/components/panels/PriorityActionsPanel", () => ({
  PriorityActionsPanel: () => <div>Priority Actions</div>,
}));

vi.mock("@/components/panels/SituationAlertsPanel", () => ({
  SituationAlertsPanel: () => <div>Situation Alerts</div>,
}));

import { PanelLayout } from "@/components/panels/PanelLayout";

describe("PanelLayout", () => {
  test("does not render the disturbance summary panel", () => {
    render(<PanelLayout />);

    expect(screen.getByText("Situation Alerts")).toBeTruthy();
    expect(screen.getByText("Operating State")).toBeTruthy();
    expect(screen.queryByText("Disturbance Summary")).toBeNull();
  });
});