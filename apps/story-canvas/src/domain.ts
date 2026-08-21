/** Renderer-independent story graph (RF adapters live elsewhere). */

import type { Annotation } from "./lib/annotationTypes";

export type NodeKind =
  | "image"
  | "video"
  | "text"
  | "research"
  | "prompt"
  | "beat"
  | "scene"
  | "frame";

export type EdgeType =
  | "follows"
  | "supports"
  | "references"
  | "visualReference"
  | "researchContext";

export interface GraphNode {
  id: string;
  type: NodeKind;
  x: number;
  y: number;
  title: string;
  body: string;
  src?: string | null;
  sequenceIndex: number;
  provenance?: string | null;
  frameId?: string | null;
  researchSessionId?: string | null;
  width?: number;
  height?: number;
  /** Vector annotations for round-trip image editing (see annotationTypes). */
  annotations?: Annotation[];
  annotationSchemaVersion?: number;
  /** Side-panel notes from the image annotator (not drawn on canvas). */
  annotationNotes?: string;
}

export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  type: EdgeType;
}

export interface StoryProject {
  id?: string | null;
  title: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  template?: string | null;
  updatedAt?: number;
}

export const EDGE_TYPES: { id: EdgeType; label: string }[] = [
  { id: "follows", label: "follows" },
  { id: "supports", label: "supports" },
  { id: "references", label: "references" },
  { id: "visualReference", label: "visual ref" },
  { id: "researchContext", label: "research context" },
];

export function uid(prefix: string): string {
  return `${prefix}${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
}

export function typeLabel(type: NodeKind): string {
  return (
    {
      image: "IMAGE",
      video: "VIDEO",
      text: "TEXT",
      research: "RESEARCH CONTEXT",
      prompt: "PROMPT",
      beat: "BEAT",
      scene: "SCENE",
      frame: "FRAME",
    }[type] || type.toUpperCase()
  );
}

export function nextSequence(nodes: GraphNode[]): number {
  return nodes.reduce((m, n) => Math.max(m, n.sequenceIndex || 0), 0) + 1;
}

export function orderedNodes(nodes: GraphNode[]): GraphNode[] {
  return [...nodes].sort((a, b) => (a.sequenceIndex || 0) - (b.sequenceIndex || 0));
}

export function placeholderSvg(label: string, hue = 200): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="280" height="360">
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="hsl(${hue},35%,78%)"/>
      <stop offset="100%" stop-color="hsl(${hue},40%,42%)"/>
    </linearGradient></defs>
    <rect width="280" height="360" fill="url(#g)"/>
    <text x="140" y="180" text-anchor="middle" fill="white" font-family="Segoe UI,sans-serif" font-size="16">${label.slice(0, 18)}</text>
  </svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

export function guidedStoryTemplate(): StoryProject {
  const n1: GraphNode = {
    id: "tpl-ref",
    type: "image",
    x: 80,
    y: 120,
    title: "IMAGE · REF",
    body: "",
    src: placeholderSvg("REF", 210),
    sequenceIndex: 1,
    provenance: "template",
  };
  const n2: GraphNode = {
    id: "tpl-text",
    type: "text",
    x: 420,
    y: 100,
    title: "TEXT",
    body: "a bird lands on the shoulder. model looks to camera. cinematic.",
    sequenceIndex: 2,
  };
  const n3: GraphNode = {
    id: "tpl-research",
    type: "research",
    x: 420,
    y: 300,
    title: "RESEARCH CONTEXT",
    body: "Query: …\n\nClaims (edit):\n- …\n\nSources:\n- …",
    sequenceIndex: 3,
  };
  const n4: GraphNode = {
    id: "tpl-beat",
    type: "beat",
    x: 760,
    y: 160,
    title: "BEAT",
    body: "Look to camera — hold — release.",
    sequenceIndex: 4,
  };
  const frame: GraphNode = {
    id: "tpl-frame",
    type: "frame",
    x: 40,
    y: 40,
    title: "FRAME · Act 1",
    body: "Opening beat cluster",
    sequenceIndex: 0,
    width: 520,
    height: 420,
  };
  return {
    title: "Guided story",
    template: "guided",
    nodes: [frame, n1, n2, n3, n4],
    edges: [
      { id: "e1", from: "tpl-ref", to: "tpl-text", type: "visualReference" },
      { id: "e2", from: "tpl-text", to: "tpl-beat", type: "follows" },
      { id: "e3", from: "tpl-research", to: "tpl-beat", type: "researchContext" },
    ],
  };
}

export function blankTemplate(): StoryProject {
  return { title: "Untitled story", template: "blank", nodes: [], edges: [] };
}
