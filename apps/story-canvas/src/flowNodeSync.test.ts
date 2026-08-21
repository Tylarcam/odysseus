import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mergeFlowNodeFromPrev } from "./flowNodeSync.ts";

describe("mergeFlowNodeFromPrev", () => {
  it("preserves measured, width, height from prev and keeps selected", () => {
    const next = {
      id: "a",
      type: "story" as const,
      position: { x: 1, y: 2 },
      data: { body: "hello" },
      style: undefined as undefined,
    };
    const prev = {
      measured: { width: 240, height: 180 },
      width: 240,
      height: 180,
      selected: true,
    };

    const merged = mergeFlowNodeFromPrev(next, prev, true);

    assert.equal(merged.selected, true);
    assert.deepEqual(merged.measured, { width: 240, height: 180 });
    assert.equal(merged.width, 240);
    assert.equal(merged.height, 180);
    assert.equal(merged.data.body, "hello");
    assert.deepEqual(merged.position, { x: 1, y: 2 });
  });

  it("does not invent layout fields when prev has none", () => {
    const next = { id: "b", position: { x: 0, y: 0 } };
    const merged = mergeFlowNodeFromPrev(next, { selected: false }, false);
    assert.equal(merged.selected, false);
    assert.equal(merged.measured, undefined);
    assert.equal(merged.width, undefined);
    assert.equal(merged.height, undefined);
  });

  it("keeps next style sizing for frames (does not copy style from prev)", () => {
    const next = {
      id: "frame-1",
      style: { width: 500, height: 400, zIndex: -1 },
      position: { x: 10, y: 20 },
    };
    const prev = {
      measured: { width: 480, height: 360 },
      width: 480,
      height: 360,
      selected: false,
      // stale style must not win over next
      style: { width: 999, height: 999, zIndex: -1 },
    } as { measured: { width: number; height: number }; width: number; height: number; selected: boolean };

    const merged = mergeFlowNodeFromPrev(next, prev, false);

    assert.deepEqual(merged.style, { width: 500, height: 400, zIndex: -1 });
    assert.deepEqual(merged.measured, { width: 480, height: 360 });
  });
});
