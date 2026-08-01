/**
 * V.A.U.L.T. global hotkeys — pure, DOM-free timer logic for "hold Space to
 * arm voice delegate". Separated from cmdCenter.js so the hold-threshold
 * behavior is unit-testable without a browser (see
 * tests/test_cmd_center_hotkeys.mjs). Real scheduling (setTimeout/clearTimeout)
 * is injected so tests can drive the callback manually.
 */

export const SPACE_HOLD_MS = 3000;

/**
 * @param {{
 *   thresholdMs?: number,
 *   onArm?: () => void,
 *   schedule?: (fn: () => void, ms: number) => unknown,
 *   cancel?: (id: unknown) => void,
 * }} [opts]
 */
export function createSpaceHoldTracker({
  thresholdMs = SPACE_HOLD_MS,
  onArm,
  schedule = (fn, ms) => setTimeout(fn, ms),
  cancel = (id) => clearTimeout(id),
} = {}) {
  let timer = null;

  /** Call on every keydown for the tracked key (repeats are no-ops while held). */
  function keydown() {
    if (timer != null) return;
    timer = schedule(() => {
      timer = null;
      onArm?.();
    }, thresholdMs);
  }

  /** Call on keyup / blur / anything that should cancel a pending hold. */
  function release() {
    if (timer != null) {
      cancel(timer);
      timer = null;
    }
  }

  return { keydown, release };
}
