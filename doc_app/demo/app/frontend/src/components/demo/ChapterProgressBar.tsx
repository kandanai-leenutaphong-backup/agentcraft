/**
 * ChapterProgressBar — segmented progress bar showing chapter positions.
 *
 * Each chapter is one segment whose width is proportional to the number
 * of frames it contains. Past chapters are filled emerald, the current
 * one is pulsing emerald, future ones are gray.
 *
 * Mounts at the top of the viewport during demo playback.
 */

import { useDemoPlayerStore } from "@/demo/demoPlayerStore";

export function ChapterProgressBar() {
  const mode = useDemoPlayerStore((s) => s.mode);
  const scenario = useDemoPlayerStore((s) => s.scenario);
  const chapterIndexes = useDemoPlayerStore((s) => s.chapterIndexes);
  const currentChapterIndex = useDemoPlayerStore((s) => s.currentChapterIndex);
  const skipToChapter = useDemoPlayerStore((s) => s.skipToChapter);

  if (mode === "off" || !scenario || chapterIndexes.length === 0) return null;

  /* Compute per-chapter frame counts so each segment is proportionally wide. */
  const totalFrames = scenario.frames.length;
  const widths: number[] = chapterIndexes.map((startIdx, i) => {
    const nextStart = chapterIndexes[i + 1] ?? totalFrames;
    return ((nextStart - startIdx) / totalFrames) * 100;
  });

  return (
    <div className="fixed top-0 left-0 right-0 z-30 h-1.5 flex bg-gray-200">
      {chapterIndexes.map((_, i) => {
        const past = i < currentChapterIndex;
        const current = i === currentChapterIndex;
        const cls = past
          ? "bg-emerald-500"
          : current
          ? "bg-emerald-400 animate-pulse"
          : "bg-gray-300";
        const title = scenario.frames[chapterIndexes[i]]?.chapter ?? `Chapter ${i + 1}`;
        return (
          <button
            key={i}
            type="button"
            onClick={() => skipToChapter(i)}
            className={cls + " hover:brightness-110"}
            style={{ width: `${widths[i]}%` }}
            title={`Jump to: ${title}`}
          />
        );
      })}
    </div>
  );
}
