/**
 * App shell — GridIQ control room layout.
 *
 * The workspace (3-column control room) is the only first-paint surface;
 * the short-lived chat-first toggle from Couturier v2 R1 was retired in
 * favour of always-on visibility of situation alerts + centre tabs +
 * chat. PanelLayout owns the 3-column shell.
 */

import { PanelLayout } from "./components/panels";
import { RateLimitOverlay } from "./components/layout/RateLimitOverlay";
import { SavedSessionPicker } from "./components/layout/SavedSessionPicker";
import { HistoricalScenarioPicker } from "./components/layout/HistoricalScenarioPicker";
import { Toaster } from "./components/shared/Toaster";
import { CommandPalette } from "./components/shared/CommandPalette";
import { HelpOverlay } from "./components/shared/HelpOverlay";
import { useEffect } from "react";
import { LayoutTemplate, LogOut, UserRoundCog } from "lucide-react";
import { useAgentStore } from "./stores/agentStore";
import { usePlaceholderStore } from "./stores/placeholderStore";
import { useChatStore } from "./stores/chatStore";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { usePersistence } from "./hooks/usePersistence";
import { startEscalationWatcher } from "./features/situation/escalationWatcher";
import { useAuth } from "./auth/useAuth";
import { IS_KIOSK } from "./foundation/constants";
import { seedKioskStores } from "./demo/kioskBootstrap";
import { PlaybackControls } from "./components/demo/PlaybackControls";
import { NarrationOverlay } from "./components/demo/NarrationOverlay";
import { ChapterProgressBar } from "./components/demo/ChapterProgressBar";
import { SpotlightOverlay } from "./components/demo/SpotlightOverlay";
import { PasswordGate } from "./components/kiosk/PasswordGate";
import { useVocab } from "./stores/vocabularyStore";

/* Placeholder-mode toggle is a developer fixture — never render it in a
   production build. import.meta.env.DEV is replaced at build time by Vite,
   so the entire button + its handlers tree-shake out of the prod bundle. */
const SHOW_PLACEHOLDER_TOGGLE = import.meta.env.DEV;

/** Inner app — only rendered after site auth succeeds. */
function AuthenticatedApp() {
  const fetchAgents = useAgentStore((s) => s.fetchAgents);
  const togglePlaceholder = usePlaceholderStore((s) => s.toggle);
  const placeholderEnabled = usePlaceholderStore((s) => s.enabled);
  const seedPlaceholderMessages = useChatStore((s) => s.seedPlaceholderMessages);
  const clearAllChat = useChatStore((s) => s.clearAll);
  /* Auth chip in the header — hoisted from PanelLayout's bottom-left
     panel on 2026-05-18. Keeping the read here (one call site) keeps
     the header self-contained without an extra wrapper component. */
  const { isAuthenticated, user, logout, switchAccount } = useAuth();
  useEffect(() => {
    if (IS_KIOSK) seedKioskStores();
    else fetchAgents();
  }, [fetchAgents]);

  /* Seed or clear placeholder chat messages when the toggle flips. */
  useEffect(() => {
    if (placeholderEnabled) {
      seedPlaceholderMessages(["grid_manager", "data_assistant"]);
    } else {
      clearAllChat();
    }
  }, [placeholderEnabled, seedPlaceholderMessages, clearAllChat]);

  /* Tier 3 infrastructure — keyboard shortcuts, localStorage persistence,
     and the situation escalation toast watcher. Each hook/helper is a
     thin side-effect layer with no props; wiring here keeps App.tsx as
     the single mount point for cross-cutting behaviour. */
  useGlobalShortcuts();
  if (!IS_KIOSK) usePersistence();
  useEffect(() => {
    if (IS_KIOSK) return undefined;
    /* Return the unsubscribe so tests / HMR unmount cleanly. */
    return startEscalationWatcher();
  }, []);

  const productName = useVocab("productName");

  return (
    <div className="flex flex-col h-screen bg-app-bg text-text-primary">
      {/* Kiosk builds have no header: the site around the demo supplies the
          wordmark and navigation, and the single scenario autostarts. */}
      {!IS_KIOSK && (
      <header className="flex items-center px-4 py-2 bg-header-bg border-b border-header-border">
        <span
          data-testid="app-wordmark"
          className="text-xs font-bold uppercase tracking-widest text-text-primary"
        >
          {productName}
        </span>
        {/* Scenario picker + saved-session picker — always available in the
            header chrome now that the workspace is the only first-paint
            surface. */}
        {!IS_KIOSK && (
          <div className="ml-4">
            <HistoricalScenarioPicker />
          </div>
        )}
        {!IS_KIOSK && (
          <div className="ml-2">
            <SavedSessionPicker />
          </div>
        )}
        <div className="flex-1" />
        {!IS_KIOSK && SHOW_PLACEHOLDER_TOGGLE && (
          <button
            data-testid="placeholder-toggle"
            onClick={togglePlaceholder}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              placeholderEnabled
                ? "bg-placeholder/20 text-placeholder border border-placeholder/30"
                : "text-text-secondary hover:text-text-primary hover:bg-neutral-bg2"
            }`}
            title={placeholderEnabled ? "Placeholder data ON — click to disable" : "Show placeholder data for UI development"}
          >
            <LayoutTemplate className="h-3.5 w-3.5" />
            {placeholderEnabled ? "Placeholders ON" : "Placeholders"}
          </button>
        )}
        {/* Auth chip — hoisted from PanelLayout's bottom-left strip on
            2026-05-18. Compact single-row layout fits the 32px header:
            two-line name/email collapses to a single name + small
            switch-account + logout icons. Tooltips carry the email and
            action labels. */}
        {!IS_KIOSK && isAuthenticated && user && (
          <div
            data-testid="user-chip"
            className="ml-3 flex items-center gap-1 pl-3 border-l border-header-border"
          >
            <span
              className="text-xs font-medium text-text-primary max-w-[140px] truncate"
              title={user.email}
            >
              {user.name}
            </span>
            <button
              onClick={switchAccount}
              className="p-1.5 rounded hover:bg-neutral-bg3 text-text-muted hover:text-text-primary transition-colors"
              title={`Switch account (${user.email})`}
              aria-label="Switch account"
            >
              <UserRoundCog className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={logout}
              className="p-1.5 rounded hover:bg-neutral-bg3 text-text-muted hover:text-status-error transition-colors"
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </header>
      )}
      <PanelLayout />
      <RateLimitOverlay />
      {/* Tier 3 surfaces — fixed-position overlays mounted once. */}
      <CommandPalette />
      <HelpOverlay />
      <Toaster />
      {IS_KIOSK && (
        <>
          <ChapterProgressBar />
          <NarrationOverlay />
          <SpotlightOverlay />
          <PlaybackControls />
        </>
      )}
    </div>
  );
}

export default function App() {
  if (IS_KIOSK) {
    return (
      <PasswordGate>
        <AuthenticatedApp />
      </PasswordGate>
    );
  }
  return <AuthenticatedApp />;
}
