/**
 * AutostepControl — Module role:
 *
 *   Top-bar control that lets the on-stage demo presenter pace the
 *   playback. Three affordances:
 *
 *     1. Autostep slider (left=OFF, right=ON). Defaults OFF so the
 *        demo waits at every chapter boundary for an explicit click —
 *        the safe default for a non-technical CIO presenting live.
 *     2. Previous button — jumps to the start of the previous chapter
 *        (or restarts from frame 0 if at chapter 0). Always enabled
 *        while a scenario is loaded. Clicking it forces Autostep OFF
 *        so the player does not race past the new position.
 *     3. Next button — advances to the start of the next chapter.
 *        Always enabled while a scenario is loaded. Same Autostep-OFF
 *        behaviour as Previous. Pulses bright green when the player
 *        is paused at a chapter boundary waiting for the click;
 *        shows the upcoming chapter title inline.
 *
 *   Keyboard: ← / → drive Previous / Next from a wireless presenter
 *   clicker. Space also advances. All ignored while focus is in an
 *   input/textarea/contenteditable so normal typing is preserved.
 *
 *   Only renders when a scenario is loaded (mode !== "off").
 *
 * Key collaborators:
 *   - demo/demoPlayerStore.ts — reads stepMode, mode, currentChapterIndex,
 *     chapterIndexes, scenario; calls setStepMode, skipToChapter,
 *     skipToNextChapter, restart.
 */

import { useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useDemoPlayerStore } from "@/demo/demoPlayerStore";
import { playScenario } from "@/demo/framePlayer";

export function AutostepControl() {
  const mode = useDemoPlayerStore((s) => s.mode);
  const stepMode = useDemoPlayerStore((s) => s.stepMode);
  const annotationsEnabled = useDemoPlayerStore((s) => s.annotationsEnabled);
  const scenario = useDemoPlayerStore((s) => s.scenario);
  const currentChapterIndex = useDemoPlayerStore((s) => s.currentChapterIndex);
  const chapterIndexes = useDemoPlayerStore((s) => s.chapterIndexes);
  const toggleStepMode = useDemoPlayerStore((s) => s.toggleStepMode);
  const setStepMode = useDemoPlayerStore((s) => s.setStepMode);
  const toggleAnnotations = useDemoPlayerStore((s) => s.toggleAnnotations);
  const autoReplay = useDemoPlayerStore((s) => s.autoReplay);
  const toggleAutoReplay = useDemoPlayerStore((s) => s.toggleAutoReplay);
  const skipToChapter = useDemoPlayerStore((s) => s.skipToChapter);
  const skipToNextChapter = useDemoPlayerStore((s) => s.skipToNextChapter);
  const restart = useDemoPlayerStore((s) => s.restart);

  /* Autostep ON = stepMode OFF (player runs continuously).
     Autostep OFF = stepMode ON (player auto-pauses at chapter boundaries). */
  const autostep = !stepMode;

  /* True when the player is paused at a chapter boundary waiting for a
     manual advance — this is the moment we want the Next button to
     light up so the presenter knows it is their cue. */
  const awaitingNextClick = !autostep && mode === "paused";

  /* Title of the chapter the operator is about to advance INTO so the
     Next button can preview it. Null when at the last chapter. */
  const nextChapterTitle: string | null = (() => {
    if (!scenario) return null;
    const nextIdx = currentChapterIndex + 1;
    if (nextIdx >= chapterIndexes.length) return null;
    const frameIdx = chapterIndexes[nextIdx];
    return scenario.frames[frameIdx]?.chapter ?? null;
  })();

  /* Title of the previous chapter — used as the Previous button's
     hover hint so the presenter knows where they are about to jump. */
  const prevChapterTitle: string | null = (() => {
    if (!scenario) return null;
    const prevIdx = currentChapterIndex - 1;
    if (prevIdx < 0) return null;
    const frameIdx = chapterIndexes[prevIdx];
    return scenario.frames[frameIdx]?.chapter ?? null;
  })();

  /* Manual nav handlers. Both force Autostep OFF (stepMode ON) so the
     player does not race past the operator's click. The store's seek
     mechanism handles the actual jump regardless of pause state.

     Special case: when mode === "done" the player loop has exited and
     no longer consumes _seekTo. Prev / Next from the done state must
     re-arm the player by calling start() + playScenario() with the
     seek pre-set; framePlayer's seek branch then replays patches up
     to the target chapter and resumes there. */
  const reArmAt = (targetChapterIdx: number) => {
    const store = useDemoPlayerStore.getState();
    /* Seed the seek BEFORE start() so the loop's very first iteration
       sees it. Then start() creates a fresh AbortController and flips
       mode → "playing"; playScenario() walks frames 0..target, applying
       patches without sleeps, then sits paused at the target chapter. */
    useDemoPlayerStore.setState({ _seekTo: store.chapterIndexes[targetChapterIdx] ?? 0 });
    store.start();
    void playScenario();
  };
  const goNext = () => {
    setStepMode(true);
    if (mode === "done") {
      const target = Math.min(currentChapterIndex + 1, chapterIndexes.length - 1);
      reArmAt(target);
      return;
    }
    skipToNextChapter();
  };
  const goPrev = () => {
    setStepMode(true);
    const target = currentChapterIndex - 1;
    if (mode === "done") {
      /* From the done state, "Prev" rewinds to the previous chapter and
         resumes paused there. Clamp to 0 so a click never goes negative. */
      reArmAt(Math.max(0, target));
      return;
    }
    /* If we are partway through chapter N, "previous" jumps to the
       start of chapter N-1. If we are already at chapter 0, fall
       through to restart() which resets to frame 0 — the closest
       observable equivalent of a "back" beyond the start. */
    if (target < 0) restart();
    else skipToChapter(target);
  };

  /* Keyboard shortcuts — only attach when a scenario is loaded so the
     listener does not run during normal app use. Ignored while typing
     in a form element. */
  useEffect(() => {
    if (mode === "off") return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || t?.isContentEditable) return;
      if (e.key === "ArrowRight" || e.key === " ") {
        e.preventDefault();
        goNext();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        goPrev();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // goNext / goPrev close over store actions which are stable; rerunning
    // when currentChapterIndex changes keeps the closure's branch logic
    // honest without re-installing the listener every frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, currentChapterIndex]);

  /* Hide entirely when no scenario is loaded so the header stays clean. */
  if (mode === "off") return null;

  return (
    <div
      data-testid="autostep-control"
      className="flex items-center gap-2 rounded-lg bg-gray-900/80 px-3 py-1.5 ring-1 ring-white/10"
    >
      {/* Autostep label + slider toggle. Custom button with two states;
          the visual reads as a slider thumb sliding between OFF (left,
          grey) and ON (right, emerald). */}
      <button
        type="button"
        onClick={toggleStepMode}
        data-testid="autostep-toggle"
        aria-pressed={autostep}
        aria-label={autostep ? "Autostep is on" : "Autostep is off"}
        className="flex items-center gap-2 group"
        title={
          autostep
            ? "Autostep ON — the demo plays continuously. Click to require manual Next clicks at each chapter."
            : "Autostep OFF — the demo waits for a Next click at every chapter. Click to play continuously."
        }
      >
        <span className="text-xs font-bold uppercase tracking-widest text-white/80">
          Autostep
        </span>
        <span
          className={
            "relative inline-block h-5 w-10 rounded-full transition-colors " +
            (autostep ? "bg-emerald-500" : "bg-gray-600")
          }
        >
          <span
            className={
              "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all " +
              (autostep ? "left-[22px]" : "left-0.5")
            }
          />
        </span>
        <span
          className={
            "text-xs font-bold w-7 " +
            (autostep ? "text-emerald-400" : "text-gray-400")
          }
        >
          {autostep ? "ON" : "OFF"}
        </span>
      </button>

      {/* Annotation toggle — sibling slider next to Autostep. When ON,
          each chapter advance auto-fires its scenario-authored
          annotation spotlight (the "look here, this is what happened"
          callout). When OFF, only mandatory imperative spotlights fire. */}
      <button
        type="button"
        onClick={toggleAnnotations}
        data-testid="annotations-toggle"
        aria-pressed={annotationsEnabled}
        aria-label={annotationsEnabled ? "Annotations are on" : "Annotations are off"}
        className="flex items-center gap-2 group border-l border-white/10 pl-3"
        title={
          annotationsEnabled
            ? "Annotations ON — each chapter advance highlights what just happened. Click to disable."
            : "Annotations OFF — chapter advances run silently. Click to re-enable highlights."
        }
      >
        <span className="text-xs font-bold uppercase tracking-widest text-white/80">
          Annotation
        </span>
        <span
          className={
            "relative inline-block h-5 w-10 rounded-full transition-colors " +
            (annotationsEnabled ? "bg-amber-400" : "bg-gray-600")
          }
        >
          <span
            className={
              "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all " +
              (annotationsEnabled ? "left-[22px]" : "left-0.5")
            }
          />
        </span>
        <span
          className={
            "text-xs font-bold w-7 " +
            (annotationsEnabled ? "text-amber-300" : "text-gray-400")
          }
        >
          {annotationsEnabled ? "ON" : "OFF"}
        </span>
      </button>

      {/* Auto-replay toggle. When ON, the player loops back to frame 0
          immediately after the last frame instead of marking done. The
          Done button never appears while a loop is in progress. Used
          for unattended kiosk loops (trade-show stand) where the demo
          should cycle indefinitely until manually stopped. */}
      <button
        type="button"
        onClick={toggleAutoReplay}
        data-testid="autoreplay-toggle"
        aria-pressed={autoReplay}
        aria-label={autoReplay ? "Auto-replay is on" : "Auto-replay is off"}
        className="flex items-center gap-2 group border-l border-white/10 pl-3"
        title={
          autoReplay
            ? "Auto-replay ON \u2014 the demo loops back to the beginning when it ends. Click to disable."
            : "Auto-replay OFF \u2014 the demo stops at the last frame. Click to loop continuously."
        }
      >
        <span className="text-xs font-bold uppercase tracking-widest text-white/80">
          Loop
        </span>
        <span
          className={
            "relative inline-block h-5 w-10 rounded-full transition-colors " +
            (autoReplay ? "bg-cyan-400" : "bg-gray-600")
          }
        >
          <span
            className={
              "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all " +
              (autoReplay ? "left-[22px]" : "left-0.5")
            }
          />
        </span>
        <span
          className={
            "text-xs font-bold w-7 " +
            (autoReplay ? "text-cyan-300" : "text-gray-400")
          }
        >
          {autoReplay ? "ON" : "OFF"}
        </span>
      </button>

      {/* Previous chapter — always enabled while a scenario is loaded.
          Forces Autostep OFF on click so the player does not race past
          the new position. Fixed-width chrome (w-24) so the bar layout
          never shifts as chapter titles change length. */}
      <button
        type="button"
        onClick={goPrev}
        data-testid="autostep-prev"
        className="flex w-24 flex-shrink-0 items-center justify-center gap-1 rounded-md bg-gray-700/80 px-2.5 py-1.5 text-sm font-bold text-white hover:bg-gray-600 transition-colors"
        title={
          prevChapterTitle
            ? `Back to: ${prevChapterTitle} (←)`
            : "Restart from the beginning (←)"
        }
      >
        <ChevronLeft className="h-4 w-4" />
        <span>Prev</span>
      </button>

      {/* Next chapter — always enabled while a scenario is loaded.
          Pulses bright green when the player is paused at a chapter
          boundary waiting on a click; otherwise the same neutral chrome
          as Prev. The chapter-title slot is rendered at a FIXED width
          regardless of content (or its absence) so the button group
          never reflows as chapters change. */}
      <button
        type="button"
        onClick={goNext}
        data-testid="autostep-next"
        className={
          "flex flex-shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-bold transition-all " +
          (awaitingNextClick
            ? "bg-emerald-500 text-white hover:bg-emerald-400 animate-pulse shadow-[0_0_12px_rgba(16,185,129,0.6)]"
            : "bg-gray-700/80 text-white hover:bg-gray-600")
        }
        title={
          nextChapterTitle
            ? `Advance to: ${nextChapterTitle} (Space / →)`
            : "End of demo — no further chapters"
        }
      >
        <span>Next</span>
        <ChevronRight className="h-4 w-4" />
        {/* Fixed-width title slot — always reserves space so the
            button cannot grow / shrink as the upcoming chapter title
            changes (or disappears at the end of the demo). */}
        <span
          className="ml-1 inline-block w-[14rem] truncate text-xs font-normal opacity-90 text-left"
          aria-hidden={!nextChapterTitle}
        >
          {nextChapterTitle ? `· ${nextChapterTitle}` : "\u00A0"}
        </span>
      </button>
    </div>
  );
}
