/**
 * NarrationOverlay — bottom caption bar shown during demo playback.
 *
 * Displays the current chapter title and narration text. Persists the
 * most recent chapter's narration even on non-chapter frames so the
 * caption doesn't blank out between chapter boundaries.
 */

import { useEffect, useState } from "react";
import { useDemoPlayerStore } from "@/demo/demoPlayerStore";

export function NarrationOverlay() {
  const mode = useDemoPlayerStore((s) => s.mode);
  const visible = useDemoPlayerStore((s) => s.narrationVisible);
  const scenario = useDemoPlayerStore((s) => s.scenario);
  const currentChapterIndex = useDemoPlayerStore((s) => s.currentChapterIndex);
  const currentFrameIndex = useDemoPlayerStore((s) => s.currentFrameIndex);
  const chapterIndexes = useDemoPlayerStore((s) => s.chapterIndexes);

  /* Track the chapter frame so we can read its title + narration. */
  const [chapterTitle, setChapterTitle] = useState<string>("");
  const [chapterText, setChapterText] = useState<string>("");

  useEffect(() => {
    if (!scenario || currentChapterIndex < 0) {
      setChapterTitle("");
      setChapterText("");
      return;
    }
    const chapterFrame = scenario.frames[chapterIndexes[currentChapterIndex]];
    setChapterTitle(chapterFrame?.chapter ?? "");
    /* Narration is per frame, not per chapter: every beat that carries a line
       should speak it. Frames without one hold the last line on screen. */
    const current = scenario.frames[currentFrameIndex];
    if (current?.narration) {
      setChapterText(current.narration);
    } else if (currentFrameIndex === chapterIndexes[currentChapterIndex]) {
      setChapterText(chapterFrame?.narration ?? "");
    }
  }, [scenario, currentChapterIndex, currentFrameIndex, chapterIndexes]);

  if (!visible) return null;
  if (mode === "off") return null;
  if (!chapterTitle && !chapterText) return null;

  return (
    <div className="fixed bottom-20 left-1/2 -translate-x-1/2 z-30 max-w-2xl w-[90%] bg-gray-900/90 text-white rounded-lg shadow-lg px-4 py-3">
      {chapterTitle && (
        <div className="text-xs uppercase tracking-wide text-emerald-400 font-semibold mb-1">
          {chapterTitle}
        </div>
      )}
      {chapterText && <div className="text-sm leading-relaxed">{chapterText}</div>}
    </div>
  );
}
