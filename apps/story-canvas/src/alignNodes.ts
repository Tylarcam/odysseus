import type { GraphNode } from "./domain";

export interface NodeRect {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

const DEFAULT_W = 280;
const DEFAULT_H = 200;
const FRAME_W = 480;
const FRAME_H = 360;
const VIDEO_W = 320;

export const DISTRIBUTE_GAP = 24;

export type HorizontalAlign = "top" | "center" | "bottom";
export type VerticalAlign = "left" | "center" | "right";
export type DistributeAxis = "horizontal" | "vertical";

export type AlignAction =
  | { kind: "align-h"; mode: HorizontalAlign }
  | { kind: "align-v"; mode: VerticalAlign }
  | { kind: "distribute"; axis: DistributeAxis };

export function graphNodeRect(node: GraphNode, measured?: { width: number; height: number }): NodeRect {
  if (measured) {
    return { id: node.id, x: node.x, y: node.y, width: measured.width, height: measured.height };
  }
  if (node.type === "frame") {
    return {
      id: node.id,
      x: node.x,
      y: node.y,
      width: node.width ?? FRAME_W,
      height: node.height ?? FRAME_H,
    };
  }
  return {
    id: node.id,
    x: node.x,
    y: node.y,
    width: node.width ?? (node.type === "video" ? VIDEO_W : DEFAULT_W),
    height: node.height ?? DEFAULT_H,
  };
}

export function rectsForIds(
  nodes: GraphNode[],
  ids: string[],
  measuredById?: Map<string, { width: number; height: number }>
): NodeRect[] {
  const idSet = new Set(ids);
  return nodes
    .filter((n) => idSet.has(n.id))
    .map((n) => graphNodeRect(n, measuredById?.get(n.id)));
}

export function alignHorizontal(
  rects: NodeRect[],
  mode: HorizontalAlign
): Record<string, { x: number; y: number }> {
  if (rects.length < 2) return {};
  const out: Record<string, { x: number; y: number }> = {};
  const tops = rects.map((r) => r.y);
  const bottoms = rects.map((r) => r.y + r.height);
  const centers = rects.map((r) => r.y + r.height / 2);

  if (mode === "top") {
    const ref = Math.min(...tops);
    for (const r of rects) out[r.id] = { x: r.x, y: ref };
  } else if (mode === "bottom") {
    const ref = Math.max(...bottoms);
    for (const r of rects) out[r.id] = { x: r.x, y: ref - r.height };
  } else {
    const ref = centers.reduce((a, b) => a + b, 0) / centers.length;
    for (const r of rects) out[r.id] = { x: r.x, y: ref - r.height / 2 };
  }
  return out;
}

export function alignVertical(
  rects: NodeRect[],
  mode: VerticalAlign
): Record<string, { x: number; y: number }> {
  if (rects.length < 2) return {};
  const out: Record<string, { x: number; y: number }> = {};
  const lefts = rects.map((r) => r.x);
  const rights = rects.map((r) => r.x + r.width);
  const centers = rects.map((r) => r.x + r.width / 2);

  if (mode === "left") {
    const ref = Math.min(...lefts);
    for (const r of rects) out[r.id] = { x: ref, y: r.y };
  } else if (mode === "right") {
    const ref = Math.max(...rights);
    for (const r of rects) out[r.id] = { x: ref - r.width, y: r.y };
  } else {
    const ref = centers.reduce((a, b) => a + b, 0) / centers.length;
    for (const r of rects) out[r.id] = { x: ref - r.width / 2, y: r.y };
  }
  return out;
}

export function distributeHorizontal(
  rects: NodeRect[],
  gap = DISTRIBUTE_GAP
): Record<string, { x: number; y: number }> {
  if (rects.length < 2) return {};
  const sorted = [...rects].sort((a, b) => a.x - b.x);
  const out: Record<string, { x: number; y: number }> = {};
  let cx = sorted[0].x;
  for (const r of sorted) {
    out[r.id] = { x: cx, y: r.y };
    cx += r.width + gap;
  }
  return out;
}

export function distributeVertical(
  rects: NodeRect[],
  gap = DISTRIBUTE_GAP
): Record<string, { x: number; y: number }> {
  if (rects.length < 2) return {};
  const sorted = [...rects].sort((a, b) => a.y - b.y);
  const out: Record<string, { x: number; y: number }> = {};
  let cy = sorted[0].y;
  for (const r of sorted) {
    out[r.id] = { x: r.x, y: cy };
    cy += r.height + gap;
  }
  return out;
}

export function applyAlignAction(
  rects: NodeRect[],
  action: AlignAction
): Record<string, { x: number; y: number }> {
  switch (action.kind) {
    case "align-h":
      return alignHorizontal(rects, action.mode);
    case "align-v":
      return alignVertical(rects, action.mode);
    case "distribute":
      return action.axis === "horizontal"
        ? distributeHorizontal(rects)
        : distributeVertical(rects);
  }
}
