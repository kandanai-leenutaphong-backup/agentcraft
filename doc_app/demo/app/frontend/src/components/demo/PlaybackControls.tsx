/**
 * PlaybackControls — fixed-position overlay shown while the demo is running.
 *
 * Provides Restart, Skip-chapter, Skip-end, Speed selector, and
 * Narration-visibility toggle. Only mounts when the demo player is in
 * 'playing' / 'paused' / 'done' state.
 *
 * State source: useDemoPlayerStore.
 */

import { useDemoPlayerStore } from "@/demo/demoPlayerStore";

/* Full speed range. The low end (0.1x, 0.25x) lets a presenter narrate
   over fast cascades of streamed tokens; the high end (6x) is for
   skipping through warmups in rehearsal. Step-mode toggle was removed
   here because Autostep in the top header is the single source of
   truth for pacing — they were redundant and confusingly different. */
const SPEED_PRESETS = [0.1, 0.25, 0.5, 1, 1.5, 2, 3, 6] as const;

export function PlaybackControls() {
  const mode = useDemoPlayerStore((s) => s.mode);
  const speed = useDemoPlayerStore((s) => s.speed);
  const narrationVisible = useDemoPlayerStore((s) => s.narrationVisible);
  const currentChapterIndex = useDemoPlayerStore((s) => s.currentChapterIndex);
  const chapterIndexes = useDemoPlayerStore((s) => s.chapterIndexes);

  /* All hook calls must precede any conditional return. Putting these
     after the `if (mode === "off") return null` below would change the
     hook count between renders the first time the demo starts and trip
     React error #310. */
  const restart = useDemoPlayerStore((s) => s.restart);
  const stop = useDemoPlayerStore((s) => s.stop);
  const skipToNextChapter = useDemoPlayerStore((s) => s.skipToNextChapter);
  const skipToEnd = useDemoPlayerStore((s) => s.skipToEnd);
  const setSpeed = useDemoPlayerStore((s) => s.setSpeed);
  const toggleNarration = useDemoPlayerStore((s) => s.toggleNarration);

  /* Only show controls during/after a run, never when the demo is off. */
  if (mode === "off") return null;

  const canSkipChapter = currentChapterIndex + 1 < chapterIndexes.length;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-gray-900/95 text-white rounded-lg shadow-lg px-3 py-2 flex items-center gap-3 text-sm">
      {/* Pause/Resume removed — Autostep slider + Next/Prev in the top
          header are the single source of truth for run-time pacing. */}

      {/* Restart */}
      <button
        type="button"
        onClick={restart}
        className="px-2 py-1 rounded hover:bg-white/10"
        title="Restart from the beginning"
      >
        ⟲ Restart
      </button>

      {/* Skip chapter */}
      <button
        type="button"
        onClick={skipToNextChapter}
        disabled={!canSkipChapter}
        data-testid="playback-skip-chapter"
        className="px-2 py-1 rounded hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent"
        title="Skip to next chapter"
      >
        ⏭ Chapter
      </button>

      {/* Skip to end */}
      <button
        type="button"
        onClick={skipToEnd}
        disabled={mode === "done"}
        data-testid="playback-skip-end"
        className="px-2 py-1 rounded hover:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent"
        title="Skip to the end of this scenario"
      >
        ⏩ End
      </button>

      {/* Speed */}
      <div className="flex items-center gap-1 border-l border-white/20 pl-3">
        <span className="text-xs text-gray-400">Speed</span>
        {SPEED_PRESETS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSpeed(s)}
            className={
              "px-2 py-0.5 rounded text-xs " +
              (speed === s ? "bg-emerald-600" : "hover:bg-white/10")
            }
          >
            {s}×
          </button>
        ))}
      </div>

      {/* Narration toggle */}
      <button
        type="button"
        onClick={toggleNarration}
        className={
          "px-2 py-1 rounded " +
          (narrationVisible ? "text-emerald-400" : "hover:bg-white/10")
        }
        title="Show or hide narration overlay"
      >
        {narrationVisible ? "💬 Narration" : "🔇 Narration"}
      </button>

      {/* Done — only shown when the player has reached the end. Bright
          glowing red button; click stops the player which clears mode
          to "off" and the entire control bar unmounts. The header
          scenario picker remains available for a fresh selection. */}
      {mode === "done" && (
        <button
          type="button"
          onClick={stop}
          data-testid="playback-done"
          className="ml-2 rounded-md border-l border-white/20 bg-red-600 px-4 py-1.5 text-sm font-bold text-white transition-all hover:bg-red-500 animate-pulse shadow-[0_0_18px_rgba(239,68,68,0.7)]"
          title="End the demo and dismiss the playback bar"
        >
          ✓ Done
        </button>
      )}
    </div>
  );
}
