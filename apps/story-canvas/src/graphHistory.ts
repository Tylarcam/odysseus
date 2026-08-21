import type { GraphEdge, GraphNode } from "./domain";

export interface GraphSnapshot {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

const MAX_UNDO = 50;

export function cloneSnapshot(nodes: GraphNode[], edges: GraphEdge[]): GraphSnapshot {
  return {
    nodes: structuredClone(nodes),
    edges: structuredClone(edges),
  };
}

export function createUndoStacks() {
  const undo: GraphSnapshot[] = [];
  const redo: GraphSnapshot[] = [];
  return {
    push(current: GraphSnapshot) {
      undo.push(cloneSnapshot(current.nodes, current.edges));
      if (undo.length > MAX_UNDO) undo.shift();
      redo.length = 0;
    },
    undo(current: GraphSnapshot): GraphSnapshot | null {
      if (!undo.length) return null;
      redo.push(cloneSnapshot(current.nodes, current.edges));
      return undo.pop()!;
    },
    redo(current: GraphSnapshot): GraphSnapshot | null {
      if (!redo.length) return null;
      undo.push(cloneSnapshot(current.nodes, current.edges));
      return redo.pop()!;
    },
    clear() {
      undo.length = 0;
      redo.length = 0;
    },
    canUndo: () => undo.length > 0,
    canRedo: () => redo.length > 0,
  };
}

export type UndoStacks = ReturnType<typeof createUndoStacks>;
