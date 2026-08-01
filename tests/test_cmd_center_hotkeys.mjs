// V.A.U.L.T. keyboard shortcuts — space-hold timer smoke test.
// Uses Node's built-in test runner (no new devDependency). Run with:
//   node --test tests/test_cmd_center_hotkeys.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createSpaceHoldTracker, SPACE_HOLD_MS } from '../static/js/cmdCenterHotkeys.js';

function fakeScheduler() {
  const calls = [];
  return {
    calls,
    schedule: (fn, ms) => {
      const id = { fn, ms };
      calls.push(id);
      return id;
    },
    cancel: (id) => {
      const i = calls.indexOf(id);
      if (i >= 0) calls.splice(i, 1);
    },
  };
}

test('holding past the threshold arms voice exactly once', () => {
  const { schedule, cancel, calls } = fakeScheduler();
  let armCount = 0;
  const tracker = createSpaceHoldTracker({ onArm: () => armCount++, schedule, cancel });

  tracker.keydown();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].ms, SPACE_HOLD_MS);

  calls[0].fn(); // simulate the scheduled callback firing after 3000ms
  assert.equal(armCount, 1);
});

test('releasing before the threshold never arms voice', () => {
  const { schedule, cancel, calls } = fakeScheduler();
  let armCount = 0;
  const tracker = createSpaceHoldTracker({ onArm: () => armCount++, schedule, cancel });

  tracker.keydown();
  tracker.release(); // e.g. keyup at 1000ms, well under the 3000ms threshold

  assert.equal(calls.length, 0, 'pending timer must be cancelled on early release');
  assert.equal(armCount, 0);
});

test('key-repeat keydown events do not stack a second timer or double-fire', () => {
  const { schedule, cancel, calls } = fakeScheduler();
  let armCount = 0;
  const tracker = createSpaceHoldTracker({ onArm: () => armCount++, schedule, cancel });

  tracker.keydown();
  tracker.keydown();
  tracker.keydown();
  assert.equal(calls.length, 1, 'only the first keydown schedules a timer');

  calls[0].fn();
  assert.equal(armCount, 1);
});

test('a fresh hold after release schedules a new timer', () => {
  const { schedule, cancel, calls } = fakeScheduler();
  const tracker = createSpaceHoldTracker({ onArm: () => {}, schedule, cancel });

  tracker.keydown();
  tracker.release();
  tracker.keydown();

  assert.equal(calls.length, 1, 'release clears state so the next hold can schedule again');
});
