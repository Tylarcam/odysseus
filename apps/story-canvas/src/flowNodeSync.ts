/**
 * Preserve React Flow layout fields across graph→flow rebuilds.
 * Dropping `measured` causes RF to hide the node (visibility:hidden) and blur inputs.
 */
export type FlowLayoutCarry = {
  measured?: { width?: number; height?: number };
  width?: number;
  height?: number;
  selected?: boolean;
};

export function mergeFlowNodeFromPrev<T extends { id: string }>(
  next: T,
  prev: FlowLayoutCarry | undefined,
  selected: boolean
): T & { selected: boolean } & FlowLayoutCarry {
  if (!prev) return { ...next, selected };

  const merged: T & { selected: boolean } & FlowLayoutCarry = { ...next, selected };
  if (prev.measured != null) merged.measured = prev.measured;
  if (prev.width != null) merged.width = prev.width;
  if (prev.height != null) merged.height = prev.height;
  return merged;
}
