/** True when the node carries user media (not an SVG placeholder). */
export function hasRealMedia(node: { type: string; src?: string | null }): boolean {
  if (!node.src) return false;
  if (node.type === "video") return true;
  return !node.src.startsWith("data:image/svg+xml");
}
