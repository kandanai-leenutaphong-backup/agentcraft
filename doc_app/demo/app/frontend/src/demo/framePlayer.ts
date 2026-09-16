/**
 * Frame player — async loop that walks a Scenario's frames.
 *
 * Module role:
 *   The single async function that drives a demo run. It reads frames in
 *   order, applies each patch via applyPatch(), and waits transition_ms
 *   (divided by the current speed multiplier) before advancing. Honours
 *   pause, step mode, seek requests, and abort.
 *
 * Concurrency invariants:
 *   - Only one playRun() call should be in flight at a time. The caller
 *     (PlayDemoButton) ensures this by checking demoPlayerStore.mode before
 *     starting a new run and calling stop() before any new start.
 *   - All blocking awaits respect the AbortSignal: throws AbortError
 *     immediately if abort() was called.
 */

import { applyPatch, freshScenarioState, resetDemoStores } from "./applyPatch";
import type { ScenarioState } from "./applyPatch";
import { useDemoPlayerStore } from "./demoPlayerStore";
import { useSpotlightStore } from "@/stores/spotlightStore";
import type { Scenario, Frame } from "./scenarioSchema";

/** Sleep that bails out cleanly on abort. Throws AbortError on cancel. */
function abortableSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/** Sleep for the frame dwell unless a seek command arrives first. Returns
 *  true when the player should restart the loop immediately so the seek
 *  can be consumed before advancing the current frame index. */
function sleepUntilTimeoutAbortOrSeek(ms: number, signal: AbortSignal): Promise<boolean> {
  let wakeFromSeek: (() => void) | null = null;
  const seekPromise = new Promise<boolean>((resolve) => {
    wakeFromSeek = () => resolve(true);
    useDemoPlayerStore.getState()._setSeekWakeResolver(wakeFromSeek);
  });
  return Promise.race([
    abortableSleep(ms, signal).then(() => false),
    seekPromise,
  ]).finally(() => {
    if (useDemoPlayerStore.getState()._seekWakeResolver === wakeFromSeek) {
      useDemoPlayerStore.getState()._setSeekWakeResolver(null);
    }
  });
}

/**
 * Run the loaded scenario from frame 0 (or wherever a seek points).
 *
 * Lifecycle:
 *   - Caller has already invoked demoPlayerStore.loadScenario(s) +
 *     demoPlayerStore.start() — so scenario, mode='playing', and
 *     _abortController are all set up.
 *   - We reset all stores, build a fresh ScenarioState, and walk the frames.
 *   - On natural end, call _markDone(). On abort, exit silently.
 */
export async function playScenario(): Promise<void> {
  const store = useDemoPlayerStore.getState();
  const scenario: Scenario | null = store.scenario;
  const ctrl = store._abortController;
  if (!scenario || !ctrl) {
    console.warn("[demo] playScenario called without scenario or controller", { hasScenario: !!scenario, hasCtrl: !!ctrl });
    return;
  }
  console.info("[demo] playScenario: starting loop, frames=", scenario.frames.length);
  const signal = ctrl.signal;

  /* Hard-reset all stores the player touches, then build a fresh
     working state. This guarantees a clean slate even if a previous
     run partially populated the stores. */
  resetDemoStores();
  let state: ScenarioState = freshScenarioState();

  let frameIdx = 0;
  /* Tracks the most-recently-entered chapter for the store. -1 means
     "no chapter started yet". */
  let chapterIdx = -1;

  try {
    while (frameIdx < scenario.frames.length) {
      if (signal.aborted) return;

      /* Honour any seek issued via skipToChapter / restart. A seek to 0
         requires re-resetting state, so we treat it as a full restart. */
      const seek = useDemoPlayerStore.getState()._consumeSeek();
      if (seek !== -1) {
        if (seek === 0) {
          resetDemoStores();
          state = freshScenarioState();
          chapterIdx = -1;
        } else {
          /* Forward seek: replay all frames from 0 up to and including
             the target's prior frames so the UI is in the right state.
             We skip the wait but DO apply the patches. This keeps the
             implementation simple — no incremental snapshots needed. */
          resetDemoStores();
          state = freshScenarioState();
          chapterIdx = -1;
          for (let i = 0; i < seek; i++) {
            const f = scenario.frames[i];
            state = applyPatch(state, f.patch);
            if (f.chapter) {
              /* Track which chapter we just entered while replaying. */
              chapterIdx++;
              useDemoPlayerStore.getState()._setCurrentChapter(chapterIdx);
            }
          }
        }
        frameIdx = seek;
        continue;
      }

      const frame: Frame = scenario.frames[frameIdx];

      /* Apply the patch instantly. */
      state = applyPatch(state, frame.patch);
      useDemoPlayerStore.getState()._setCurrentFrame(frameIdx);

      /* Advance chapter pointer if this frame opens a new chapter. */
      if (frame.chapter) {
        chapterIdx++;
        useDemoPlayerStore.getState()._setCurrentChapter(chapterIdx);
        /* Clear any annotation spotlight from the previous chapter so
           it does not bleed across the boundary. The current chapter's
           own annotation (if any) fires immediately below. */
        useSpotlightStore.getState().clearSpotlight();
        /* In step mode, auto-pause AT the chapter boundary so the demo
           lead can talk before clicking play. We skip the auto-pause on
           the very first chapter so the demo starts immediately. */
        if (useDemoPlayerStore.getState().stepMode && chapterIdx > 0) {
          useDemoPlayerStore.getState().pause();
        }
      }

      /* Auto-fire per-frame annotation spotlight if the user has
         Annotations enabled. Runs AFTER the patch + chapter handling so
         that the annotation lands on whatever DOM the patch just made
         visible. Imperative ``ui.spotlight.set`` ops in the patch take
         precedence (they ran inside applyPatch above) — this only
         fires when the frame opted in via the typed ``annotation``
         field AND no explicit set op was issued in this same frame. */
      if (frame.annotation
        && useDemoPlayerStore.getState().annotationsEnabled
        && !frame.patch["ui.spotlight.set"]
        && !frame.patch["ui.spotlight.clear"]
      ) {
        useSpotlightStore.getState().setSpotlight({
          targetId: frame.annotation.target,
          caption: frame.annotation.caption,
          placement: frame.annotation.placement,
          padding: frame.annotation.padding,
        });
      }

      /* Block here while paused. resume() resolves the inner promise. */
      await useDemoPlayerStore.getState()._waitWhilePaused();
      if (signal.aborted) return;
      if (useDemoPlayerStore.getState()._seekTo !== -1) continue;

      /* Wait the frame's transition, scaled by speed. When the frame
         carries narration text, scale the floor to the narration's
         reading time so the audience can finish each beat before the
         player moves on. We use 220 ms per word (~270 wpm — brisk but
         readable on-screen with one or two seconds of buffer baked
         into transition_ms). The scenario-authored transition_ms is
         still respected as a minimum so frames that need a longer
         hold (e.g. the 10-second scan animation) are not shortened. */
      const speed = useDemoPlayerStore.getState().speed;
      const baseMs = frame.transition_ms;
      const narrationMs = frame.narration
        ? frame.narration.trim().split(/\s+/).filter(Boolean).length * 220
        : 0;
      const dwellMs = Math.max(baseMs, narrationMs);
      const waitMs = Math.max(0, Math.round(dwellMs / speed));
      if (waitMs > 0) {
        try {
          const interruptedBySeek = await sleepUntilTimeoutAbortOrSeek(waitMs, signal);
          if (interruptedBySeek) continue;
        } catch (err) {
          if ((err as DOMException).name === "AbortError") return;
          throw err;
        }
      }

      frameIdx++;
    }

    /* Reached the end without abort. If auto-replay is on, loop back
       to frame 0 instead of marking done; otherwise hand control to
       the Done button. The loop reuses the current AbortController so
       a Stop click still cancels mid-replay. */
    if (useDemoPlayerStore.getState().autoReplay) {
      console.info("[demo] playScenario: auto-replay enabled, looping");
      resetDemoStores();
      state = freshScenarioState();
      useSpotlightStore.getState().clearSpotlight();
      frameIdx = 0;
      chapterIdx = -1;
      useDemoPlayerStore.getState()._setCurrentChapter(-1);
      useDemoPlayerStore.getState()._setCurrentFrame(-1);
      /* Tail-recurse via the outer while loop. We can just continue
         since we are inside the try block — but the loop has already
         exited because frameIdx === scenario.frames.length. Re-enter
         by recursive call; abort propagates through the same signal. */
      return playScenario();
    }
    useDemoPlayerStore.getState()._markDone();
  } catch (err) {
    if ((err as DOMException).name === "AbortError") return;
    console.error("[demo] playScenario unexpected error:", err);
    useDemoPlayerStore.getState()._markDone();
  }
}
