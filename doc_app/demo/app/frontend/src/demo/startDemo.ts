/**
 * Kiosk demo trigger.
 *
 * Module role:
 *   Kiosk builds ship a single scenario and no picker, so the Scan button in
 *   SituationControlBar starts the demo. This is the sequence the retired
 *   PlayDemoButton used: load -> loadScenario -> start -> play.
 */

import { SCENARIOS } from "@/demo";
import { useDemoPlayerStore } from "@/demo/demoPlayerStore";
import { playScenario } from "@/demo/framePlayer";

/** True when no scenario is loaded or playing. */
export function isDemoIdle(): boolean {
  return useDemoPlayerStore.getState().mode === "off";
}

/**
 * Loads and plays the bundled scenario. Resolves once playback has been
 * kicked off; `playScenario` then runs on its own and owns its errors.
 * No-op when a scenario is already running.
 */
export async function startDemoScenario(): Promise<void> {
  const entry = SCENARIOS[0];
  if (!entry || !isDemoIdle()) return;
  try {
    const scenario = await entry.load();
    if (!isDemoIdle()) return;
    useDemoPlayerStore.getState().loadScenario(scenario);
    useDemoPlayerStore.getState().start();
    void playScenario();
  } catch (err) {
    console.error("[demo] failed to start scenario", entry.id, err);
  }
}
