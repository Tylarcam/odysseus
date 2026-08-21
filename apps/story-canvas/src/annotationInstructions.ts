import { typeLabel, type GraphNode } from "./domain";
import { migrateAnnotations } from "./lib/annotationPaint";
import type { Annotation, ConnectorAnnotation, ShapeAnnotation, TextAnnotation } from "./lib/annotationTypes";

export type InstructionContext = {
  nodeTitle?: string;
  nodeId?: string;
  imageLabel?: string;
  imageWidth?: number;
  imageHeight?: number;
  /** Side-panel notes from the annotator (not on-canvas text). */
  sideNotes?: string;
};

const COLOR_NAMES: Record<string, string> = {
  "#e53935": "red",
  "#fb8c00": "orange",
  "#fdd835": "yellow",
  "#43a047": "green",
  "#1e88e5": "blue",
  "#8e24aa": "purple",
  "#212121": "black",
  "#ffffff": "white",
};

const REFERENCE_RE =
  /\b(like this|good example|reference|keep this|this (spacing|padding|margin|style|layout|branding)|i like (this|the)|branding|logo|wordmark)\b/i;
const INSTRUCTION_RE =
  /\b(add|apply|use|match|fix|change|move|increase|decrease|same|where the|make|copy|replicate|please)\b/i;
const BRANDING_REFERENCE_RE =
  /\b(branding|logo|wordmark|monogram|brand(?:ing)?\s+(?:reference|asset|guide|banner))\b/i;
const TRAVERS_BRAND_RE = /\b(ts|travers['']?n?\s*spaces|traversing spaces)\b/i;
const MOVE_DOWN_RE = /\bmove\b.*\bdown\b|\bmove down\b/i;
const BRANDING_ADD_RE = /\b(add|insert|place|apply|use)\b/i;
const REFERENCE_POINTER_RE = /\b(that|same|like this|the reference|i like|where the)\b/i;
const ARROW_COLOR_RE =
  /\b(red|orange|yellow|green|blue|purple|black|white)\s+arrows?\b/i;

function isTextAnn(ann: Annotation): ann is TextAnnotation {
  return ann.tool === "text";
}

function isShapeAnn(ann: Annotation): ann is ShapeAnnotation {
  return ann.tool !== "text" && ann.tool !== "connector";
}

function isConnectorAnn(ann: Annotation): ann is ConnectorAnnotation {
  return ann.tool === "connector";
}

function colorLabel(hex: string): string {
  return COLOR_NAMES[hex.toLowerCase()] || hex;
}

function colorFromName(name: string): string | null {
  const entry = Object.entries(COLOR_NAMES).find(([, label]) => label === name.toLowerCase());
  return entry?.[0] ?? null;
}

function truncate(text: string, max: number): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (oneLine.length <= max) return oneLine;
  return `${oneLine.slice(0, max - 1)}…`;
}

/** Map image coordinates to a human-readable region label. */
export function describeRegion(x: number, y: number, imageWidth?: number, imageHeight?: number): string {
  if (!imageWidth || !imageHeight) {
    return `region at (${Math.round(x)}, ${Math.round(y)})`;
  }

  const hx = x / imageWidth;
  const hy = y / imageHeight;
  const hBand = hx < 0.33 ? "left" : hx > 0.66 ? "right" : "center";
  const vBand = hy < 0.33 ? "top" : hy > 0.66 ? "bottom" : "middle";

  if (hBand === "left" && vBand === "top") return "top-left of the layout";
  if (hBand === "right" && vBand === "top") return "top-right of the layout";
  if (hBand === "left" && vBand === "bottom") return "bottom-left section";
  if (hBand === "right" && vBand === "bottom") return "bottom-right section";
  if (hBand === "left") return "left margin / main content column";
  if (hBand === "right") return "right side of the layout";
  if (vBand === "top") return "top section";
  if (vBand === "bottom") return "bottom section";
  if (hBand === "center" && vBand === "middle") return "center of the layout";
  return `${vBand} ${hBand} area`;
}

export function shapeTargetPoint(ann: ShapeAnnotation): { x: number; y: number } {
  switch (ann.tool) {
    case "arrow":
      return { x: ann.x2, y: ann.y2 };
    case "line":
      return { x: (ann.x1 + ann.x2) / 2, y: (ann.y1 + ann.y2) / 2 };
    default: {
      const left = Math.min(ann.x1, ann.x2);
      const top = Math.min(ann.y1, ann.y2);
      const right = Math.max(ann.x1, ann.x2);
      const bottom = Math.max(ann.y1, ann.y2);
      return { x: (left + right) / 2, y: (top + bottom) / 2 };
    }
  }
}

function textCenter(ann: TextAnnotation): { x: number; y: number } {
  return { x: ann.x + ann.width / 2, y: ann.y + ann.height / 2 };
}

function distance(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function proximityThreshold(w?: number, h?: number): number {
  if (w && h) return Math.max(120, Math.min(w, h) * 0.2);
  return 150;
}

function describeShape(ann: ShapeAnnotation, ctx: InstructionContext): string {
  const color = colorLabel(ann.style.stroke.color);
  const pt = shapeTargetPoint(ann);
  const region = describeRegion(pt.x, pt.y, ctx.imageWidth, ctx.imageHeight);

  switch (ann.tool) {
    case "arrow":
      return `${color} arrow pointing to ${region}`;
    case "line":
      return `${color} line marking ${region}`;
    case "rectangle":
      return ann.style.fill
        ? `${color} highlight box over ${region}`
        : `${color} rectangle around ${region}`;
    case "circle":
      return ann.style.fill
        ? `${color} highlight circle on ${region}`
        : `${color} circle around ${region}`;
    default:
      return `${color} mark at ${region}`;
  }
}

/** Infer a content-type label from arrow/highlight placement (no OCR). */
export function inferTargetLabel(ann: ShapeAnnotation, ctx: InstructionContext): string {
  const pt = shapeTargetPoint(ann);
  const region = describeRegion(pt.x, pt.y, ctx.imageWidth, ctx.imageHeight);

  if (ctx.imageWidth && ctx.imageHeight) {
    const hx = pt.x / ctx.imageWidth;
    const hy = pt.y / ctx.imageHeight;

    if (hx < 0.55) {
      if (hy < 0.25) return "header or title area";
      if (hy < 0.55) return "upper list / bullet items in the main column";
      if (hy < 0.72) return "mid-column list items";
      return "blockquote or lower text block";
    }
  }

  return `UI element at ${region}`;
}

function extractPropertyFromReference(text: string): string {
  const match = text.match(/\b(spacing|padding|margin|style|layout|alignment|size|color)\b/i);
  return match ? match[1].toLowerCase() : "styling";
}

function findNearestReference(
  instr: TextAnnotation,
  references: TextAnnotation[],
  threshold: number
): TextAnnotation | undefined {
  const center = textCenter(instr);
  let best: TextAnnotation | undefined;
  let bestDist = Infinity;
  for (const ref of references) {
    const d = distance(center, textCenter(ref));
    if (d < bestDist && d <= threshold) {
      bestDist = d;
      best = ref;
    }
  }
  return best;
}

/** Link instruction text to a reference callout even when far apart on the canvas. */
function resolveReferenceForInstruction(
  instr: TextAnnotation,
  references: TextAnnotation[],
  threshold: number
): TextAnnotation | undefined {
  if (!references.length || !REFERENCE_POINTER_RE.test(instr.text)) return undefined;
  if (references.length === 1) return references[0];

  for (const ref of references) {
    const property = extractPropertyFromReference(ref.text);
    if (property !== "styling" && new RegExp(`\\b${property}\\b`, "i").test(instr.text)) {
      return ref;
    }
  }

  return findNearestReference(instr, references, threshold * 3);
}

function shapesNearPoint(
  shapes: ShapeAnnotation[],
  point: { x: number; y: number },
  threshold: number
): ShapeAnnotation[] {
  return shapes.filter((s) => distance(point, shapeTargetPoint(s)) <= threshold);
}

function resolveLinkedShapes(
  instr: TextAnnotation,
  shapes: ShapeAnnotation[],
  references: TextAnnotation[],
  threshold: number
): ShapeAnnotation[] {
  const colorMatch = instr.text.match(ARROW_COLOR_RE);
  if (colorMatch) {
    const hex = colorFromName(colorMatch[1]);
    if (hex) {
      const colored = shapes.filter((s) => s.style.stroke.color.toLowerCase() === hex);
      if (colored.length) return colored;
    }
  }

  if (/\barrows?\b/i.test(instr.text)) {
    const arrows = shapes.filter((s) => s.tool === "arrow");
    if (arrows.length) return arrows;
  }

  const nearInstr = shapesNearPoint(shapes, textCenter(instr), threshold * 1.5);
  if (nearInstr.length) return nearInstr;

  if (references.length === 1 && shapes.length <= 6) return shapes;

  return [];
}

function buildHeader(ctx: InstructionContext): string {
  const parts: string[] = [];
  if (ctx.nodeId) parts.push(`node ${ctx.nodeId}`);
  if (ctx.imageLabel) parts.push(ctx.imageLabel);
  else if (ctx.nodeTitle) parts.push(ctx.nodeTitle);
  const suffix = parts.length ? ` (${parts.join(" · ")})` : "";
  return `### Image edit instructions${suffix}`;
}

function capitalizeSentence(text: string): string {
  const t = text.trim();
  if (!t) return t;
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Short human label for an annotation (used in connector copy). */
export function annotationShortLabel(ann: Annotation, ctx: InstructionContext): string {
  if (ann.tool === "text") {
    const quote = truncate(ann.text.trim(), 48);
    return quote ? `text "${quote}"` : "text callout";
  }
  if (ann.tool === "connector") return "connector";
  const pt = shapeTargetPoint(ann);
  const region = describeRegion(pt.x, pt.y, ctx.imageWidth, ctx.imageHeight);
  switch (ann.tool) {
    case "arrow":
      return `${colorLabel(ann.style.stroke.color)} arrow at ${region}`;
    case "rectangle":
      return `${colorLabel(ann.style.stroke.color)} box at ${region}`;
    case "circle":
      return `${colorLabel(ann.style.stroke.color)} circle at ${region}`;
    case "line":
      return `${colorLabel(ann.style.stroke.color)} line at ${region}`;
    default:
      return `mark at ${region}`;
  }
}

function describeConnector(
  connector: ConnectorAnnotation,
  byId: Map<string, Annotation>,
  ctx: InstructionContext
): string {
  const from = byId.get(connector.fromId);
  const to = byId.get(connector.toId);
  if (!from || !to) return "Connector links related annotations";
  const fromLabel = annotationShortLabel(from, ctx);
  const toLabel = annotationShortLabel(to, ctx);
  const color = colorLabel(connector.style.stroke.color);
  const detail = connector.label?.trim() ? `: ${truncate(connector.label.trim(), 80)}` : "";
  return `${color} connector arrow from ${fromLabel} to ${toLabel}${detail}`;
}

function isBrandingReference(text: string): boolean {
  return BRANDING_REFERENCE_RE.test(text) || TRAVERS_BRAND_RE.test(text);
}

function isBrandingAddInstruction(text: string): boolean {
  return BRANDING_ADD_RE.test(text) && isBrandingReference(text);
}

function isMoveDownInstruction(text: string): boolean {
  return MOVE_DOWN_RE.test(text);
}

function appendTraversingSpacesBrandLines(lines: string[], referenceQuote?: string): void {
  lines.push(`   Add Travers'N Spaces header branding:`);
  lines.push(
    `   - **Monogram:** rounded-square icon, white serif italic "TS", copper/brown gradient fill`
  );
  lines.push(
    `   - **Wordmark:** "TRAVERS'N SPACES" in all-caps sans-serif, same copper/brown palette`
  );
  lines.push(`   - **Layout:** monogram left, wordmark to its right; align to left content margin`);
  lines.push(
    `   - **Spacing:** ~24–32px padding from top and left slide edge (match Soundcestral slide rhythm if available)`
  );
  if (referenceQuote) {
    lines.push(`   - **Style source:** branding reference ("${referenceQuote}")`);
  }
  lines.push(`   - **Preserve:** do not overlap "upcoming" block or ep. 2_roughCut badge (top-right)`);
}

function appendMoveDownSpacingLines(lines: string[]): void {
  lines.push(`   - Shift as a unit; preserve left-column alignment (~24px content margin)`);
  lines.push(
    `   - Leave ~32–48px vertical gap below the new header before the "upcoming" label`
  );
  lines.push(`   - Keep bullet list hierarchy and dates intact (Aug 26, September entries)`);
}

function appendInstructionDetailLines(
  lines: string[],
  instr: TextAnnotation,
  linkedRef?: TextAnnotation
): void {
  if (
    isBrandingAddInstruction(instr.text) ||
    (linkedRef && isBrandingReference(linkedRef.text) && BRANDING_ADD_RE.test(instr.text))
  ) {
    appendTraversingSpacesBrandLines(
      lines,
      linkedRef ? truncate(linkedRef.text, 50) : undefined
    );
    return;
  }
  if (isMoveDownInstruction(instr.text)) {
    appendMoveDownSpacingLines(lines);
  }
}

export type NodeInstructionContext = Pick<GraphNode, "id" | "title" | "type" | "annotations" | "annotationNotes">;

/** True when a graph node has vector annotations that can produce instructions. */
export function nodeHasAnnotationInstructions(node: NodeInstructionContext | undefined): boolean {
  if (node?.annotationNotes?.trim()) return true;
  return hasMeaningfulAnnotations(node?.annotations);
}

/** Build agent-ready markdown for a saved node's vector annotations. */
export function buildNodeAnnotationInstructions(
  node: NodeInstructionContext,
  dims?: { imageWidth?: number; imageHeight?: number }
): string {
  if (!nodeHasAnnotationInstructions(node)) return "";
  return annotationsToInstructions(node.annotations ?? [], {
    nodeId: node.id,
    nodeTitle: node.title?.trim() || undefined,
    imageLabel: node.title?.trim()
      ? `${typeLabel(node.type)} · ${truncate(node.title, 40)}`
      : typeLabel(node.type),
    imageWidth: dims?.imageWidth,
    imageHeight: dims?.imageHeight,
    sideNotes: node.annotationNotes?.trim() || undefined,
  });
}

/** Copy a node's annotation instructions to the clipboard. */
export async function copyNodeAnnotationInstructions(
  node: NodeInstructionContext,
  dims?: { imageWidth?: number; imageHeight?: number }
): Promise<{ ok: boolean; message: string }> {
  const text = buildNodeAnnotationInstructions(node, dims);
  if (!text) {
    return { ok: false, message: "No annotation instructions on this image" };
  }
  try {
    await navigator.clipboard.writeText(text);
    return { ok: true, message: "Instructions copied ✓" };
  } catch {
    return { ok: false, message: "Could not copy instructions — check clipboard permission" };
  }
}

/** True when annotations include drawable shapes or non-empty text labels. */
export function hasMeaningfulAnnotations(rawAnnotations: unknown[] | undefined): boolean {
  const annotations = migrateAnnotations(
    Array.isArray(rawAnnotations) ? rawAnnotations : undefined
  );
  return annotations.some((ann) => {
    if (ann.tool === "text") return ann.text.trim().length > 0;
    return true;
  });
}

/**
 * Convert canvas annotations into concise, agent-ready markdown edit instructions.
 */
export function annotationsToInstructions(
  rawAnnotations: Annotation[] | unknown[],
  context: InstructionContext = {}
): string {
  const annotations = migrateAnnotations(
    Array.isArray(rawAnnotations) ? rawAnnotations : undefined
  );
  const sideNotes = context.sideNotes?.trim();
  if (!annotations.length && !sideNotes) return "";

  const ctx: InstructionContext = { ...context };
  const byId = new Map(annotations.map((ann) => [ann.id, ann]));
  const texts = annotations.filter(isTextAnn).filter((t) => t.text.trim());
  const shapes = annotations.filter(isShapeAnn);
  const connectors = annotations.filter(isConnectorAnn);
  const threshold = proximityThreshold(ctx.imageWidth, ctx.imageHeight);

  const references = texts.filter((t) => REFERENCE_RE.test(t.text));
  const instructions = texts.filter(
    (t) => INSTRUCTION_RE.test(t.text) && !references.includes(t)
  );
  const notes = texts.filter((t) => !references.includes(t) && !instructions.includes(t));

  const lines: string[] = [buildHeader(ctx)];
  if (sideNotes) {
    lines.push("");
    lines.push("**Side notes:**");
    for (const paragraph of sideNotes.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean)) {
      lines.push(paragraph.replace(/\n/g, " "));
    }
  }
  let stepNum = 0;
  const usedShapeIds = new Set<string>();
  const usedConnectorIds = new Set<string>();

  for (const instr of instructions) {
    stepNum += 1;
    const linkedShapes = resolveLinkedShapes(instr, shapes, references, threshold);
    linkedShapes.forEach((s) => usedShapeIds.add(s.id));

    const mentionsRef = REFERENCE_POINTER_RE.test(instr.text);
    const linkedRef = resolveReferenceForInstruction(instr, references, threshold);

    const action = truncate(instr.text, 120);

    if (linkedRef && mentionsRef) {
      const refQuote = truncate(linkedRef.text, 50);
      const refCenter = textCenter(linkedRef);
      const refRegion = describeRegion(refCenter.x, refCenter.y, ctx.imageWidth, ctx.imageHeight);
      const property = extractPropertyFromReference(linkedRef.text);

      lines.push(`${stepNum}. ${capitalizeSentence(action)}`);
      lines.push(
        `   Apply the same ${property} as the reference callout ("${refQuote}") to:`
      );

      const arrowTargets = linkedShapes.filter((s) => s.tool === "arrow");
      const targets = arrowTargets.length ? arrowTargets : linkedShapes;

      if (targets.length) {
        for (const s of targets) {
          lines.push(`   - ${inferTargetLabel(s, ctx)}`);
        }
      } else {
        lines.push(`   - Targets indicated by arrows on the annotated image`);
      }
      lines.push(`   Match the reference box at ${refRegion}.`);
      appendInstructionDetailLines(lines, instr, linkedRef);
    } else {
      lines.push(`${stepNum}. ${capitalizeSentence(action)}`);
      if (linkedShapes.length) {
        for (const s of linkedShapes) {
          lines.push(`   - ${inferTargetLabel(s, ctx)} (${describeShape(s, ctx)})`);
        }
      }
      appendInstructionDetailLines(lines, instr, linkedRef);
    }
  }

  for (const ref of references) {
    const consumed = instructions.some(
      (i) =>
        REFERENCE_POINTER_RE.test(i.text) &&
        resolveReferenceForInstruction(i, [ref], threshold * 3)?.id === ref.id
    );
    if (consumed) continue;

    stepNum += 1;
    const center = textCenter(ref);
    const region = describeRegion(center.x, center.y, ctx.imageWidth, ctx.imageHeight);
    if (isBrandingReference(ref.text)) {
      lines.push(
        `${stepNum}. Branding reference: "${truncate(ref.text, 80)}" — replicate at ${region}.`
      );
      appendTraversingSpacesBrandLines(lines, truncate(ref.text, 50));
    } else {
      lines.push(`${stepNum}. Reference: "${truncate(ref.text, 80)}" — use as example at ${region}.`);
    }
  }

  const orphans = shapes.filter((s) => !usedShapeIds.has(s.id));
  if (orphans.length) {
    const byColor = new Map<string, ShapeAnnotation[]>();
    for (const s of orphans) {
      const c = colorLabel(s.style.stroke.color);
      const group = byColor.get(c) ?? [];
      group.push(s);
      byColor.set(c, group);
    }

    for (const [color, group] of byColor) {
      const arrows = group.filter((s) => s.tool === "arrow");
      stepNum += 1;

      if (arrows.length >= 2) {
        lines.push(`${stepNum}. ${color.charAt(0).toUpperCase() + color.slice(1)} arrows mark these regions:`);
        for (const s of arrows) {
          lines.push(`   - ${inferTargetLabel(s, ctx)}`);
        }
      } else if (group.length === 1) {
        const desc = describeShape(group[0], ctx);
        lines.push(`${stepNum}. ${capitalizeSentence(desc)}.`);
      } else {
        lines.push(`${stepNum}. Annotations to address:`);
        for (const s of group) {
          lines.push(`   - ${describeShape(s, ctx)}`);
        }
      }
    }
  }

  for (const note of notes) {
    stepNum += 1;
    lines.push(`${stepNum}. Note: "${truncate(note.text, 80)}"`);
  }

  for (const connector of connectors) {
    if (usedConnectorIds.has(connector.id)) continue;
    usedConnectorIds.add(connector.id);
    stepNum += 1;
    lines.push(`${stepNum}. ${capitalizeSentence(describeConnector(connector, byId, ctx))}.`);
  }

  let result = lines.join("\n");
  const MAX = 2200;
  if (result.length > MAX) {
    result = `${result.slice(0, MAX - 20).trimEnd()}\n…(truncated)`;
  }
  return result;
}
