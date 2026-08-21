import { annotationsToInstructions } from "./annotationInstructions";
import {
  EDGE_TYPES,
  orderedNodes,
  type GraphEdge,
  type GraphNode,
  type NodeKind,
  type StoryProject,
  typeLabel,
} from "./domain";
import { migrateAnnotations } from "./lib/annotationPaint";
import { hasRealMedia } from "./mediaHelpers";

export interface AgentBriefOptions {
  /** When set, scope selection/focus lines to these node ids. */
  selectedNodeIds?: string[];
  /** Default 3000; expand mode allows up to 4000. */
  maxChars?: number;
  /** Include extra node body snippets and raise char cap. */
  expand?: boolean;
}

const DEFAULT_MAX_CHARS = 3000;
const EXPANDED_MAX_CHARS = 4000;
const BODY_TRUNC = 80;

function truncate(text: string, max: number): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (oneLine.length <= max) return oneLine;
  return `${oneLine.slice(0, max - 1)}…`;
}

function countByType(nodes: GraphNode[]): Partial<Record<NodeKind, number>> {
  const counts: Partial<Record<NodeKind, number>> = {};
  for (const n of nodes) {
    counts[n.type] = (counts[n.type] || 0) + 1;
  }
  return counts;
}

function formatUpdatedAt(ts?: number): string {
  if (!ts) return "unknown";
  return new Date(ts).toISOString().slice(0, 16).replace("T", " ");
}

function nodeRef(n: GraphNode): string {
  const seq = n.sequenceIndex != null && n.sequenceIndex > 0 ? `#${n.sequenceIndex}` : `\`${n.id}\``;
  const title = n.title?.trim() ? ` "${truncate(n.title, 40)}"` : "";
  return `node ${seq}${title}`;
}

function edgeTypeCounts(edges: GraphEdge[]): Partial<Record<string, number>> {
  const counts: Partial<Record<string, number>> = {};
  for (const e of edges) {
    counts[e.type] = (counts[e.type] || 0) + 1;
  }
  return counts;
}

function edgeTypeLabel(type: string): string {
  return EDGE_TYPES.find((e) => e.id === type)?.label || type;
}

function suggestTasks(nodes: GraphNode[], edges: GraphEdge[]): string[] {
  const tasks: string[] = [];
  const seen = new Set<string>();

  const push = (task: string) => {
    if (!seen.has(task)) {
      seen.add(task);
      tasks.push(task);
    }
  };

  for (const n of nodes) {
    if ((n.type === "image" || n.type === "video") && !hasRealMedia(n)) {
      push(`Restore missing ${n.type} on ${nodeRef(n)}`);
    }
    if (["text", "beat", "scene", "prompt", "research"].includes(n.type) && !n.body.trim()) {
      push(`Fill empty body on ${nodeRef(n)}`);
    }
  }

  const connected = new Set<string>();
  for (const e of edges) {
    connected.add(e.from);
    connected.add(e.to);
  }
  const orphans = nodes.filter((n) => n.type !== "frame" && !connected.has(n.id));
  if (orphans.length === 1) {
    push(`Connect orphan node ${nodeRef(orphans[0])}`);
  } else if (orphans.length > 1 && orphans.length <= 5) {
    for (const n of orphans) push(`Connect orphan node ${nodeRef(n)}`);
  } else if (orphans.length > 5) {
    push(`Connect ${orphans.length} orphan nodes to the story graph`);
  }

  const annotatedWithoutVectors = nodes.filter((n) => {
    if (n.type !== "image") return false;
    const anns = n.annotations;
    return hasRealMedia(n) && (!Array.isArray(anns) || anns.length === 0);
  });
  if (annotatedWithoutVectors.length && tasks.length < 6) {
    push(
      "Vector annotations may be baked into PNG only — re-annotate or persist annotations[] on nodes for round-trip editing"
    );
  }

  return tasks.slice(0, 8);
}

function getAnnotations(node: GraphNode) {
  return migrateAnnotations(Array.isArray(node.annotations) ? node.annotations : undefined);
}

export function buildAgentBrief(project: StoryProject, options?: AgentBriefOptions): string {
  const maxChars =
    options?.maxChars ?? (options?.expand ? EXPANDED_MAX_CHARS : DEFAULT_MAX_CHARS);
  const nodes = project.nodes;
  const edges = project.edges;
  const selectedIds = options?.selectedNodeIds?.filter((id) => nodes.some((n) => n.id === id));

  const lines: string[] = [];
  lines.push("## Story Canvas — Agent Brief");

  const idPart = project.id ? ` (${project.id})` : "";
  lines.push(`**Project:** ${project.title}${idPart}`);
  lines.push(`**Nodes:** ${nodes.length} | **Edges:** ${edges.length}`);
  if (project.updatedAt) {
    lines.push(`**Updated:** ${formatUpdatedAt(project.updatedAt)}`);
  }
  lines.push("");

  lines.push("### Canvas summary");
  const counts = countByType(nodes);
  const countParts = (Object.entries(counts) as [NodeKind, number][])
    .filter(([, c]) => c > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([t, c]) => `${c} ${t}${c === 1 ? "" : "s"}`);
  lines.push(countParts.length ? `- ${countParts.join(", ")}` : "- (empty canvas)");

  if (selectedIds?.length) {
    if (selectedIds.length === 1) {
      const n = nodes.find((x) => x.id === selectedIds[0]);
      if (n) {
        lines.push(`- Selected/focused: ${nodeRef(n)} (${typeLabel(n.type)})`);
        if (n.body.trim()) {
          lines.push(`  - Body: ${truncate(n.body, BODY_TRUNC)}`);
        }
      }
    } else {
      lines.push(`- Selected: ${selectedIds.length} nodes`);
      for (const id of selectedIds.slice(0, 5)) {
        const n = nodes.find((x) => x.id === id);
        if (n) lines.push(`  - ${nodeRef(n)} (${typeLabel(n.type)})`);
      }
      if (selectedIds.length > 5) {
        lines.push(`  - …and ${selectedIds.length - 5} more`);
      }
    }
  }

  const annotatedNodes = nodes.filter(
    (n) => getAnnotations(n).length > 0 || Boolean(n.annotationNotes?.trim())
  );
  if (annotatedNodes.length) {
    lines.push("");
    lines.push("### Image edit instructions");
    for (const n of annotatedNodes) {
      const anns = getAnnotations(n);
      const title = n.title?.trim();
      const block = annotationsToInstructions(anns, {
        nodeId: n.id,
        nodeTitle: title || undefined,
        imageLabel: title ? `${typeLabel(n.type)} · ${truncate(title, 40)}` : typeLabel(n.type),
        sideNotes: n.annotationNotes?.trim() || undefined,
      });
      if (block) {
        lines.push("");
        lines.push(block);
      }
    }
  }

  lines.push("");
  lines.push("### Recent edits / structure notes");
  if (project.template) {
    lines.push(`- Template: ${project.template}`);
  }

  const ordered = orderedNodes(nodes.filter((n) => n.type !== "frame"));
  const beatNodes = ordered.filter((n) => n.type === "beat");
  if (beatNodes.length >= 2) {
    lines.push("- Beat sequence follows canvas order (sequenceIndex)");
  }

  const eCounts = edgeTypeCounts(edges);
  for (const [type, count] of Object.entries(eCounts)) {
    if (!count) continue;
    const label = edgeTypeLabel(type);
    lines.push(`- ${count} ${label} edge${count === 1 ? "" : "s"}`);
  }

  const frames = nodes.filter((n) => n.type === "frame");
  if (frames.length) {
    lines.push(`- ${frames.length} frame group${frames.length === 1 ? "" : "s"} on canvas`);
  }

  if (options?.expand && ordered.length) {
    lines.push("");
    lines.push("### Node details");
    for (const n of ordered.slice(0, 20)) {
      const body = n.body.trim();
      const detail = body ? truncate(body, BODY_TRUNC) : "(no body)";
      lines.push(`- ${nodeRef(n)} (${typeLabel(n.type)}): ${detail}`);
    }
    if (ordered.length > 20) {
      lines.push(`- …and ${ordered.length - 20} more nodes`);
    }
  }

  const tasks = suggestTasks(nodes, edges);
  if (tasks.length) {
    lines.push("");
    lines.push("### Agent tasks (suggested)");
    for (const t of tasks) {
      lines.push(`- ${t}`);
    }
  }

  let brief = lines.join("\n");
  if (brief.length > maxChars) {
    brief = `${brief.slice(0, maxChars - 24).trimEnd()}\n\n…(brief truncated)`;
  }
  return brief;
}
