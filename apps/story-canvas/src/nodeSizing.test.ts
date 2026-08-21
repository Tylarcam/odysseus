import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { dimensionsFromFlowNode, flowNodeStyleForGraphNode, isResizableNodeKind } from "./nodeSizing.ts";
import type { GraphNode } from "./domain.ts";

describe("nodeSizing", () => {
  it("marks text-like kinds as resizable", () => {
    assert.equal(isResizableNodeKind("text"), true);
    assert.equal(isResizableNodeKind("beat"), true);
    assert.equal(isResizableNodeKind("frame"), true);
    assert.equal(isResizableNodeKind("image"), false);
  });

  it("builds flow style for resizable graph nodes", () => {
    const node: GraphNode = {
      id: "t1",
      type: "text",
      x: 0,
      y: 0,
      title: "TEXT",
      body: "hello",
      sequenceIndex: 1,
      width: 320,
      height: 200,
    };
    assert.deepEqual(flowNodeStyleForGraphNode(node), { width: 320, height: 200 });
  });

  it("reads dimensions from flow node width/height", () => {
    const dims = dimensionsFromFlowNode({
      id: "a",
      position: { x: 0, y: 0 },
      data: {},
      width: 300,
      height: 180,
    });
    assert.deepEqual(dims, { width: 300, height: 180 });
  });

  it("falls back to style dimensions", () => {
    const dims = dimensionsFromFlowNode({
      id: "a",
      position: { x: 0, y: 0 },
      data: {},
      style: { width: 260, height: 140 },
    });
    assert.deepEqual(dims, { width: 260, height: 140 });
  });
});
