/**
 * Demo player store — playback controls for kiosk-mode scenarios.
 *
 * Module role:
 *   Tracks the demo player's runtime state: which scenario is loaded,
 *   pause / resume gate, current frame + chapter index, speed multiplier,
 *   step-mode toggle, narration visibility. Separate from the existing
 *   replayStore (which manages session-replay aborts) so the kiosk player
 *   stays self-contained and either store can evolve independently.
 *
 * Pause gate:
 *   The framePlayer awaits `waitWhilePaused()` before each frame's
 *   `transition_ms` countdown. Calling pause() flips `paused=true` and
 *   the next await blocks until resume() resolves the internal Promise.
 *
 * Lifecycle:
 *   loadScenario(s)   →  scenario set, frame=0, paused=true, mode='ready'
 *   start()           →  mode='playing', paused=false
 *   pause()/resume()  →  toggles the gate
 *   skipToChapter(n)  →  signals the player loop to jump
 *   skipToEnd()       →  replays all remaining patches and marks done
 *   restart()         →  back to frame 0 of current scenario
 *   stop()            →  abort, mode='off'
 */

import { create } from "zustand";
import { IS_KIOSK } from "@/foundation/constants";
import type { Scenario } from "./scenarioSchema";
import { applyKioskBootstrap } from "./kioskBootstrap";

export type DemoMode = "off" | "ready" | "playing" | "paused" | "done";

interface DemoPlayerStore {
  /** Currently loaded scenario (null when nothing selected). */
  scenario: Scenario | null;
  /** Player lifecycle state. */
  mode: DemoMode;
  /** Speed multiplier — divides each frame's transition_ms. */
  speed: number;
  /** When true, the player auto-pauses at each chapter boundary. */
  stepMode: boolean;
  /** Whether the narration overlay is visible. */
  narrationVisible: boolean;
  /** Whether per-frame annotation spotlights fire automatically.
   *  Defaults to ON. When OFF, scenario-authored ``annotation`` fields
   *  on frames are ignored by the player; imperative
   *  ``ui.spotlight.set`` patch ops still fire (they are reserved for
   *  mandatory beats like the precursor reveal). */
  annotationsEnabled: boolean;
  /** When true, the player loops the scenario after the last frame
   *  instead of marking done. Useful for unattended kiosk mode where
   *  the demo should keep cycling on a stand-alone screen. */
  autoReplay: boolean;
  /** Index of the current frame in scenario.frames (–1 before start). */
  currentFrameIndex: number;
  /** Index of the current chapter (–1 before any chapter starts). */
  currentChapterIndex: number;
  /** AbortController for the running player loop. */
  _abortController: AbortController | null;
  /** Promise that the player awaits while paused. Resolved by resume(). */
  _pauseResolver: (() => void) | null;
  /** Frame index the player should jump to on the next loop tick (or -1). */
  _seekTo: number;
  /** Resolver used by framePlayer to interrupt the current dwell when seeking. */
  _seekWakeResolver: (() => void) | null;

  /** Pre-computed list of chapter frame indexes for skip controls. */
  chapterIndexes: number[];

  // ── Actions ─────────────────────────────────────────────────────────

  /** Load a scenario (does not start playback). */
  loadScenario: (s: Scenario) => void;
  /** Start playback from the current frame index. */
  start: () => void;
  /** Pause — next frame waits on the resume promise. */
  pause: () => void;
  /** Resume — resolves the pause promise so the loop continues. */
  resume: () => void;
  /** Skip forward to the next chapter (or end). */
  skipToNextChapter: () => void;
  /** Jump to a specific chapter by index. */
  skipToChapter: (chapterIdx: number) => void;
  /** Jump to the final scenario state and show the Done control. */
  skipToEnd: () => void;
  /** Restart from frame 0. Player loop sees seekTo and resets. */
  restart: () => void;
  /** Stop playback entirely; aborts the loop and clears scenario. */
  stop: () => void;
  /** Adjust playback speed (clamped 0.25x–5x). */
  setSpeed: (n: number) => void;
  /** Toggle step mode. */
  toggleStepMode: () => void;
  /** Set step mode to a specific value. Used by Next/Previous controls
   *  to disable Autostep (i.e. enable stepMode) on every manual nav so
   *  the presenter never accidentally races past their own click. */
  setStepMode: (value: boolean) => void;
  /** Toggle narration overlay visibility. */
  toggleNarration: () => void;
  /** Toggle automatic per-frame annotation spotlights. */
  toggleAnnotations: () => void;
  /** Toggle auto-replay (loop the scenario at end). */
  toggleAutoReplay: () => void;

  // ── Internal hooks called by framePlayer ────────────────────────────

  /** Player tells the store which frame is now active. */
  _setCurrentFrame: (idx: number) => void;
  /** Player tells the store which chapter is now active. */
  _setCurrentChapter: (idx: number) => void;
  /** Player awaits this; resolves when paused becomes false. */
  _waitWhilePaused: () => Promise<void>;
  /** Player consumes seekTo and clears it. Returns the requested index or -1. */
  _consumeSeek: () => number;
  /** Player registers a resolver that seek actions call to interrupt waits. */
  _setSeekWakeResolver: (resolver: (() => void) | null) => void;
  /** Player tells the store playback finished naturally. */
  _markDone: () => void;
}

/** Compute the indexes of every frame whose `chapter` field is set. */
function computeChapters(scenario: Scenario): number[] {
  const out: number[] = [];
  scenario.frames.forEach((f, i) => {
    if (f.chapter) out.push(i);
  });
  return out;
}

export const useDemoPlayerStore = create<DemoPlayerStore>((set, get) => ({
  scenario: null,
  mode: "off",
  speed: 1,
  /* Autostep defaults OFF — i.e. stepMode is ON by default. The demo is
     shown live on stage by a non-technical presenter, so the safe default
     is to require an explicit Next click at every chapter boundary so the
     presenter controls pacing and the audience can read each beat.

     Kiosk builds are the exception: they have no header and so no
     AutostepControl, so stepping would strand the demo at the first
     chapter boundary. They play straight through; the Chapter button in
     PlaybackControls still allows manual stepping. */
  stepMode: !IS_KIOSK,
  narrationVisible: true,
    /* Annotations default OFF. They are presenter-supplied callouts that
      overlay the UI; the on-stage operator opts in via the header toggle
      when they want guided commentary. Keeping them off by default means
      a fresh scenario run shows the raw UI without distracting bubbles. */
  annotationsEnabled: false,
  /* Auto-replay defaults OFF — a stage demo ends on the Done button.
     Operators flip it on for unattended kiosk loops (e.g. trade-show
     stand) where the demo should restart from frame 0 after the last
     frame, indefinitely, until manually stopped. */
  autoReplay: false,
  currentFrameIndex: -1,
  currentChapterIndex: -1,
  _abortController: null,
  _pauseResolver: null,
  _seekTo: -1,
  _seekWakeResolver: null,
  chapterIndexes: [],

  loadScenario: (scenario) => {
    /* If a scenario was already running, abort it cleanly. */
    const prev = get()._abortController;
    if (prev) prev.abort();
    /* Apply the selected scenario's bootstrap before the first frame
       renders so the visible agent tabs, dock replies, classifications,
       and vocabulary all match the selected domain. */
    applyKioskBootstrap(scenario.kiosk_bootstrap ?? {});
    set({
      scenario,
      mode: "ready",
      currentFrameIndex: -1,
      currentChapterIndex: -1,
      chapterIndexes: computeChapters(scenario),
      _abortController: null,
      _pauseResolver: null,
      _seekTo: -1,
      _seekWakeResolver: null,
    });
  },

  start: () => {
    const ctrl = new AbortController();
    set({
      mode: "playing",
      _abortController: ctrl,
      _pauseResolver: null,
    });
  },

  pause: () => {
    if (get().mode !== "playing") return;
    set({ mode: "paused" });
  },

  resume: () => {
    const resolver = get()._pauseResolver;
    set({ mode: "playing", _pauseResolver: null });
    if (resolver) resolver();
  },

  skipToNextChapter: () => {
    const { chapterIndexes, currentChapterIndex } = get();
    const next = currentChapterIndex + 1;
    if (next >= chapterIndexes.length) return;
    set({ _seekTo: chapterIndexes[next] });
    const wake = get()._seekWakeResolver;
    if (wake) {
      set({ _seekWakeResolver: null });
      wake();
    }
    /* If we're paused, fire the resume so the loop can act on the seek. */
    const resolver = get()._pauseResolver;
    if (resolver) {
      set({ mode: "playing", _pauseResolver: null });
      resolver();
    }
  },

  skipToChapter: (chapterIdx) => {
    const { chapterIndexes } = get();
    if (chapterIdx < 0 || chapterIdx >= chapterIndexes.length) return;
    set({ _seekTo: chapterIndexes[chapterIdx] });
    const wake = get()._seekWakeResolver;
    if (wake) {
      set({ _seekWakeResolver: null });
      wake();
    }
    const resolver = get()._pauseResolver;
    if (resolver) {
      set({ mode: "playing", _pauseResolver: null });
      resolver();
    }
  },

  skipToEnd: () => {
    const { scenario } = get();
    if (!scenario) return;
    /* Seek one frame past the scenario so framePlayer replays every
       patch without waits, exits the loop, and renders the existing
       Done affordance. Auto-replay is disabled because this command is
       an explicit presenter request to land on the terminal state. */
    set({ _seekTo: scenario.frames.length, autoReplay: false });
    const wake = get()._seekWakeResolver;
    if (wake) {
      set({ _seekWakeResolver: null });
      wake();
    }
    const resolver = get()._pauseResolver;
    if (resolver) {
      set({ mode: "playing", _pauseResolver: null });
      resolver();
    }
  },

  restart: () => {
    set({ _seekTo: 0 });
    const wake = get()._seekWakeResolver;
    if (wake) {
      set({ _seekWakeResolver: null });
      wake();
    }
    /* Also wake the loop if paused. */
    const resolver = get()._pauseResolver;
    if (resolver) {
      set({ mode: "playing", _pauseResolver: null });
      resolver();
    }
  },

  stop: () => {
    const { _abortController, _pauseResolver } = get();
    /* Resolve any pending pause Promise so the loop's await unblocks
       and it can see the abort signal on its next iteration. */
    if (_pauseResolver) _pauseResolver();
    if (_abortController) _abortController.abort();
    set({
      mode: "off",
      scenario: null,
      currentFrameIndex: -1,
      currentChapterIndex: -1,
      chapterIndexes: [],
      _abortController: null,
      _pauseResolver: null,
      _seekTo: -1,
      _seekWakeResolver: null,
    });
  },

  setSpeed: (n) => {
    /* Clamp to the documented range. The lower end (0.1x) gives the
       on-stage presenter time to talk over a fast cascade of tokens;
       the upper end (6x) is for skipping through warmups in rehearsal.
       Anything outside this band makes the demo unwatchable. */
    const clamped = Math.max(0.1, Math.min(n, 6));
    set({ speed: clamped });
  },

  /* Toggle stepMode. When the operator flips Autostep ON mid-demo
     (i.e. stepMode going from true → false) and the player is currently
     paused at a chapter boundary, immediately resume so the toggle
     visibly takes effect — otherwise the player would sit there until
     a manual Next click, making Autostep appear broken. */
  toggleStepMode: () => {
    const next = !get().stepMode;
    set({ stepMode: next });
    if (next === false && get().mode === "paused") {
      const resolver = get()._pauseResolver;
      set({ mode: "playing", _pauseResolver: null });
      if (resolver) resolver();
    }
  },
  setStepMode: (value) => set({ stepMode: value }),
  toggleNarration: () => set({ narrationVisible: !get().narrationVisible }),
  toggleAnnotations: () => set({ annotationsEnabled: !get().annotationsEnabled }),
  toggleAutoReplay: () => set({ autoReplay: !get().autoReplay }),

  _setCurrentFrame: (idx) => set({ currentFrameIndex: idx }),
  _setCurrentChapter: (idx) => set({ currentChapterIndex: idx }),

  _waitWhilePaused: () => {
    if (get().mode !== "paused") return Promise.resolve();
    return new Promise<void>((resolve) => {
      set({ _pauseResolver: resolve });
    });
  },

  _consumeSeek: () => {
    const seek = get()._seekTo;
    if (seek !== -1) set({ _seekTo: -1 });
    return seek;
  },

  _setSeekWakeResolver: (resolver) => set({ _seekWakeResolver: resolver }),

  _markDone: () => {
    set({ mode: "done", _abortController: null, _pauseResolver: null, _seekWakeResolver: null });
  },
}));
