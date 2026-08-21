import type { GraphNode } from "./domain";
import { orderedNodes } from "./domain";

export interface CardSearchResult {
  node: GraphNode;
  score: number;
  seq: number;
  label: string;
  snippet: string;
}

function parseSequenceQuery(query: string): number | null {
  const m = query.trim().match(/^#\s*(\d+)\s*$/);
  if (m) return Number(m[1]);
  const bare = query.trim().match(/^(\d+)$/);
  if (bare) return Number(bare[1]);
  return null;
}

function subsequenceScore(query: string, text: string): number {
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  if (!q || !t) return 0;
  if (t.includes(q)) return 90 + Math.min(10, q.length);
  let qi = 0;
  for (let i = 0; i < t.length && qi < q.length; i++) {
    if (t[i] === q[qi]) qi++;
  }
  if (qi === q.length) return 45 + (q.length / Math.max(t.length, 1)) * 35;
  return 0;
}

function tokenScore(query: string, text: string): number {
  const tokens = query.toLowerCase().split(/\s+/).filter((t) => t.length > 0);
  if (!tokens.length) return 0;
  const t = text.toLowerCase();
  let hit = 0;
  for (const tok of tokens) {
    if (t.includes(tok)) hit++;
  }
  return (hit / tokens.length) * 55;
}

export function searchCards(nodes: GraphNode[], query: string, limit = 16): CardSearchResult[] {
  const q = query.trim();
  if (!q) return [];

  const seqQuery = parseSequenceQuery(q);
  const ordered = orderedNodes(nodes).filter((n) => n.type !== "frame");
  const results: CardSearchResult[] = [];

  for (let i = 0; i < ordered.length; i++) {
    const node = ordered[i];
    const seq = node.sequenceIndex || i + 1;
    const label = `#${seq} · ${node.type}`;
    const haystack = `${label} ${node.title || ""} ${node.body || ""} ${node.type} ${node.id}`;
    let score = Math.max(subsequenceScore(q, haystack), tokenScore(q, haystack));

    if (seqQuery !== null) {
      if (seq === seqQuery) score = Math.max(score, 250);
      else if (String(seq).startsWith(String(seqQuery))) score = Math.max(score, 120);
    }
    if (q.startsWith("#")) {
      score = Math.max(score, subsequenceScore(q.slice(1).trim(), String(seq)));
    }

    if (score >= 30) {
      const snippet = (node.body || node.title || "").replace(/\s+/g, " ").trim().slice(0, 72);
      results.push({ node, score, seq, label, snippet: snippet || "(empty)" });
    }
  }

  return results.sort((a, b) => b.score - a.score || a.seq - b.seq).slice(0, limit);
}

export function matchCardIds(nodes: GraphNode[], query: string): Set<string> {
  return new Set(searchCards(nodes, query, 999).map((r) => r.node.id));
}
