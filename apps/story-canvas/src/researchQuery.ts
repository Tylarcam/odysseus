import type { GraphNode } from "./domain";

export interface FirecrawlHit {
  title?: string;
  url?: string;
  snippet?: string;
  age?: string;
}

export function queryFromNode(node: GraphNode): string {
  const title = (node.title || "").trim();
  const body = (node.body || "").replace(/\s+/g, " ").trim().slice(0, 240);
  if (title && body && !body.toLowerCase().startsWith(title.toLowerCase())) {
    return `${title}: ${body}`;
  }
  return title || body || "Untitled";
}

export function researchBodyFromHits(
  query: string,
  hits: FirecrawlHit[],
  sourceLabel?: string
): string {
  const claims = hits
    .slice(0, 5)
    .map((h) => {
      const label = (h.title || h.url || "Source").trim();
      const snippet = (h.snippet || "").replace(/\s+/g, " ").trim().slice(0, 140);
      return snippet ? `- ${label}: ${snippet}` : `- ${label}`;
    })
    .join("\n");
  const sources = hits
    .map((h) => {
      const label = (h.title || h.url || "link").trim();
      const url = (h.url || "").trim();
      return url ? `- ${label} (${url})` : `- ${label}`;
    })
    .join("\n");
  const header = sourceLabel ? `Query: ${query}\nFrom: ${sourceLabel}` : `Query: ${query}`;
  return `${header}\n\nClaims (edit):\n${claims || "- Summarize findings below\n"}\n\nSources:\n${sources || "- (none)"}`;
}
