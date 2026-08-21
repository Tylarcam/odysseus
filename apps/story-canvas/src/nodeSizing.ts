import type { CSSProperties } from "react";
import type { Node } from "@xyflow/react";
import type { GraphNode, NodeKind } from "./domain";

export const TEXT_NODE_DEFAULT_W = 280;
export const TEXT_NODE_DEFAULT_H = 160;
export const FRAME_DEFAULT_W = 480;
export const FRAME_DEFAULT_H = 360;

const RESIZABLE_KINDS = new Set<NodeKind>([
  "text",
  "beat",
  "scene",
  "research",
  "prompt",
  "frame",
]);

export function isResizableNodeKind(kind: NodeKind): boolean {
  return RESIZABLE_KINDS.has(kind);
}

export function defaultNodeSize(kind: NodeKind): { width: number; height: number } {
  if (kind === "frame") return { width: FRAME_DEFAULT_W, height: FRAME_DEFAULT_H };
  return { width: TEXT_NODE_DEFAULT_W, height: TEXT_NODE_DEFAULT_H };
}

export function flowNodeStyleForGraphNode(n: GraphNode): CSSProperties | undefined {
  if (!isResizableNodeKind(n.type)) return undefined;
  const defaults = defaultNodeSize(n.type);
  const style: CSSProperties = {
    width: n.width ?? defaults.width,
    height: n.height ?? defaults.height,
  };
  if (n.type === "frame") style.zIndex = -1;
  return style;
}

type FlowSizedNode = Node & {
  measured?: { width?: number; height?: number };
  width?: number;
  height?: number;
};

/** Read persisted width/height from a React Flow node after resize. */
export function dimensionsFromFlowNode(n: Node): { width?: number; height?: number } {
  const fn = n as FlowSizedNode;
  if (typeof fn.width === "number" && typeof fn.height === "number") {
    return { width: fn.width, height: fn.height };
  }
  const styleW = fn.style?.width;
  const styleH = fn.style?.height;
  if (styleW != null && styleH != null) {
    return { width: Number(styleW), height: Number(styleH) };
  }
  if (fn.measured?.width && fn.measured?.height) {
    return { width: fn.measured.width, height: fn.measured.height };
  }
  return {};
}
