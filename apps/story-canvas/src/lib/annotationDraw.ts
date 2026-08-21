import type { Annotation, AnnotationStyle, ConnectorAnnotation, ShapeAnnotation, TextAnnotation } from "./annotationTypes";
import { cloneStyle, resolveStrokeWidth, toRgba } from "./annotationPaint";

export const TEXT_BACKDROP_PAD = 5;
export const TEXT_BACKDROP_BORDER = "rgba(0, 0, 0, 0.14)";
export const SELECTION_PAD = 6;
export const TEXT_LINE_HEIGHT_RATIO = 1.25;

let measureCanvas: HTMLCanvasElement | null = null;

export function textAnnotationFont(fontSize: number): string {
  return `${fontSize}px system-ui, sans-serif`;
}

function getMeasureContext(): CanvasRenderingContext2D {
  measureCanvas ??= document.createElement("canvas");
  const ctx = measureCanvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context unavailable");
  return ctx;
}

export function measureTextLineWidth(line: string, fontSize: number): number {
  const ctx = getMeasureContext();
  ctx.font = textAnnotationFont(fontSize);
  return ctx.measureText(line).width;
}

function wrapParagraph(paragraph: string, maxWidth: number, fontSize: number): string[] {
  if (!paragraph) return [""];
  const measure = (value: string) => measureTextLineWidth(value, fontSize);
  const words = paragraph.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let line = "";

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word;
    if (measure(candidate) <= maxWidth) {
      line = candidate;
      continue;
    }
    if (line) {
      lines.push(line);
      line = "";
    }
    if (measure(word) > maxWidth) {
      let chunk = "";
      for (const ch of word) {
        const next = chunk + ch;
        if (measure(next) > maxWidth && chunk) {
          lines.push(chunk);
          chunk = ch;
        } else {
          chunk = next;
        }
      }
      line = chunk;
    } else {
      line = word;
    }
  }

  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

export function wrapTextAnnotationLines(text: string, maxWidth: number, fontSize: number): string[] {
  const contentWidth = Math.max(maxWidth, 1);
  const normalized = text.replace(/\r\n/g, "\n");
  const paragraphs = normalized.split("\n");
  const lines: string[] = [];
  for (const paragraph of paragraphs) {
    lines.push(...wrapParagraph(paragraph, contentWidth, fontSize));
  }
  return lines.length ? lines : [""];
}

export function layoutTextAnnotation(ann: Pick<TextAnnotation, "text" | "width" | "fontSize">) {
  const lines = wrapTextAnnotationLines(ann.text, ann.width, ann.fontSize);
  const lineHeight = ann.fontSize * TEXT_LINE_HEIGHT_RATIO;
  const height = Math.max(lineHeight, lines.length * lineHeight);
  return { lines, lineHeight, height };
}

export function resolveTextAnnotationHeight(ann: Pick<TextAnnotation, "text" | "width" | "fontSize" | "height">): number {
  if (!ann.text.trim()) return ann.height;
  return layoutTextAnnotation(ann).height;
}

export type ShapeDraft = Pick<ShapeAnnotation, "tool" | "x1" | "y1" | "x2" | "y2" | "style">;

function drawLine(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, style: AnnotationStyle) {
  ctx.strokeStyle = toRgba(style.stroke.color, style.stroke.opacity);
  ctx.lineWidth = resolveStrokeWidth(style);
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
}

function drawArrow(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, style: AnnotationStyle, dashed = false) {
  const strokeColor = toRgba(style.stroke.color, style.stroke.opacity);
  ctx.save();
  if (dashed) ctx.setLineDash([10, 7]);
  drawLine(ctx, x1, y1, x2, y2, style);
  ctx.setLineDash([]);
  const angle = Math.atan2(y2 - y1, x2 - x1);
  const headLen = Math.max(10, resolveStrokeWidth(style) * 4);
  ctx.fillStyle = strokeColor;
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - headLen * Math.cos(angle - Math.PI / 6), y2 - headLen * Math.sin(angle - Math.PI / 6));
  ctx.lineTo(x2 - headLen * Math.cos(angle + Math.PI / 6), y2 - headLen * Math.sin(angle + Math.PI / 6));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function drawRectangle(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, style: AnnotationStyle) {
  const left = Math.min(x1, x2), top = Math.min(y1, y2), w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
  if (style.fill) { ctx.fillStyle = toRgba(style.fill.color, style.fill.opacity); ctx.fillRect(left, top, w, h); }
  ctx.strokeStyle = toRgba(style.stroke.color, style.stroke.opacity);
  ctx.lineWidth = resolveStrokeWidth(style);
  ctx.strokeRect(left, top, w, h);
}

function drawEllipse(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, style: AnnotationStyle) {
  const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2, rx = Math.abs(x2 - x1) / 2, ry = Math.abs(y2 - y1) / 2;
  if (rx < 1 && ry < 1) return;
  ctx.beginPath();
  ctx.ellipse(cx, cy, Math.max(rx, 0.5), Math.max(ry, 0.5), 0, 0, 2 * Math.PI);
  if (style.fill) { ctx.fillStyle = toRgba(style.fill.color, style.fill.opacity); ctx.fill(); }
  ctx.strokeStyle = toRgba(style.stroke.color, style.stroke.opacity);
  ctx.lineWidth = resolveStrokeWidth(style);
  ctx.stroke();
}

function drawTextAnnotation(ctx: CanvasRenderingContext2D, ann: Extract<Annotation, { tool: "text" }>) {
  if (!ann.text.trim()) return;
  const { style } = ann;
  const { lines, lineHeight, height } = layoutTextAnnotation(ann);
  const pad = TEXT_BACKDROP_PAD;
  const boxLeft = ann.x - pad;
  const boxTop = ann.y - pad;
  const boxWidth = ann.width + pad * 2;
  const boxHeight = height + pad * 2;
  if (style.background) {
    ctx.fillStyle = toRgba(style.background.color, style.background.opacity);
    ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
    ctx.strokeStyle = TEXT_BACKDROP_BORDER;
    ctx.lineWidth = 1;
    ctx.strokeRect(boxLeft + 0.5, boxTop + 0.5, boxWidth - 1, boxHeight - 1);
  }
  ctx.fillStyle = toRgba(style.stroke.color, style.stroke.opacity);
  ctx.font = textAnnotationFont(ann.fontSize);
  ctx.textBaseline = "top";
  for (let i = 0; i < lines.length; i++) ctx.fillText(lines[i], ann.x, ann.y + i * lineHeight);
}

export function getAnnotationCenter(ann: Exclude<Annotation, ConnectorAnnotation>): { x: number; y: number } {
  if (ann.tool === "text") {
    const height = resolveTextAnnotationHeight(ann);
    return { x: ann.x + ann.width / 2, y: ann.y + height / 2 };
  }
  const left = Math.min(ann.x1, ann.x2);
  const top = Math.min(ann.y1, ann.y2);
  const right = Math.max(ann.x1, ann.x2);
  const bottom = Math.max(ann.y1, ann.y2);
  return { x: (left + right) / 2, y: (top + bottom) / 2 };
}

function getAnchorBounds(ann: Exclude<Annotation, ConnectorAnnotation>) {
  if (ann.tool === "text") {
    const height = resolveTextAnnotationHeight(ann);
    return { left: ann.x, top: ann.y, width: Math.max(ann.width, 1), height: Math.max(height, 1) };
  }
  const left = Math.min(ann.x1, ann.x2);
  const top = Math.min(ann.y1, ann.y2);
  const right = Math.max(ann.x1, ann.x2);
  const bottom = Math.max(ann.y1, ann.y2);
  return {
    left,
    top,
    width: Math.max(right - left, 4),
    height: Math.max(bottom - top, 4),
  };
}

function boundaryPointToward(
  bounds: { left: number; top: number; width: number; height: number },
  center: { x: number; y: number },
  toward: { x: number; y: number }
) {
  const dx = toward.x - center.x;
  const dy = toward.y - center.y;
  if (dx === 0 && dy === 0) return center;
  const halfW = bounds.width / 2;
  const halfH = bounds.height / 2;
  const scaleX = dx !== 0 ? halfW / Math.abs(dx) : Number.POSITIVE_INFINITY;
  const scaleY = dy !== 0 ? halfH / Math.abs(dy) : Number.POSITIVE_INFINITY;
  const scale = Math.min(scaleX, scaleY);
  return { x: center.x + dx * scale, y: center.y + dy * scale };
}

export function resolveConnectorEndpoints(
  connector: ConnectorAnnotation,
  byId: Map<string, Annotation>
): { x1: number; y1: number; x2: number; y2: number } | null {
  const from = byId.get(connector.fromId);
  const to = byId.get(connector.toId);
  if (!from || !to || from.tool === "connector" || to.tool === "connector") return null;
  const fromCenter = getAnnotationCenter(from);
  const toCenter = getAnnotationCenter(to);
  const fromBounds = getAnchorBounds(from);
  const toBounds = getAnchorBounds(to);
  const start = boundaryPointToward(fromBounds, fromCenter, toCenter);
  const end = boundaryPointToward(toBounds, toCenter, fromCenter);
  return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
}

export function drawConnector(
  ctx: CanvasRenderingContext2D,
  connector: ConnectorAnnotation,
  byId: Map<string, Annotation>
) {
  const endpoints = resolveConnectorEndpoints(connector, byId);
  if (!endpoints) return;
  drawArrow(ctx, endpoints.x1, endpoints.y1, endpoints.x2, endpoints.y2, connector.style, true);
}

export function drawShape(ctx: CanvasRenderingContext2D, shape: ShapeAnnotation | ShapeDraft) {
  switch (shape.tool) {
    case "arrow": drawArrow(ctx, shape.x1, shape.y1, shape.x2, shape.y2, shape.style); break;
    case "rectangle": drawRectangle(ctx, shape.x1, shape.y1, shape.x2, shape.y2, shape.style); break;
    case "circle": drawEllipse(ctx, shape.x1, shape.y1, shape.x2, shape.y2, shape.style); break;
    default: drawLine(ctx, shape.x1, shape.y1, shape.x2, shape.y2, shape.style);
  }
}

export function drawAnnotation(ctx: CanvasRenderingContext2D, ann: Annotation, byId?: Map<string, Annotation>) {
  if (ann.tool === "connector") {
    if (byId) drawConnector(ctx, ann, byId);
    return;
  }
  if (ann.tool === "text") drawTextAnnotation(ctx, ann);
  else drawShape(ctx, ann);
}

export function drawAllAnnotations(ctx: CanvasRenderingContext2D, annotations: Annotation[]) {
  const byId = new Map(annotations.map((ann) => [ann.id, ann]));
  for (const ann of annotations) {
    if (ann.tool !== "connector") drawAnnotation(ctx, ann, byId);
  }
  for (const ann of annotations) {
    if (ann.tool === "connector") drawConnector(ctx, ann, byId);
  }
}

export function getAnnotationBounds(ann: Annotation, byId?: Map<string, Annotation>) {
  const pad = SELECTION_PAD;
  if (ann.tool === "connector") {
    const endpoints = byId ? resolveConnectorEndpoints(ann, byId) : null;
    if (!endpoints) return { left: 0, top: 0, width: pad * 2, height: pad * 2 };
    const left = Math.min(endpoints.x1, endpoints.x2) - pad;
    const top = Math.min(endpoints.y1, endpoints.y2) - pad;
    const right = Math.max(endpoints.x1, endpoints.x2) + pad;
    const bottom = Math.max(endpoints.y1, endpoints.y2) + pad;
    return { left, top, width: right - left, height: bottom - top };
  }
  if (ann.tool === "text") {
    const height = resolveTextAnnotationHeight(ann);
    return { left: ann.x - pad, top: ann.y - pad, width: ann.width + pad * 2, height: height + pad * 2 };
  }
  const left = Math.min(ann.x1, ann.x2) - pad, top = Math.min(ann.y1, ann.y2) - pad;
  const right = Math.max(ann.x1, ann.x2) + pad, bottom = Math.max(ann.y1, ann.y2) + pad;
  return { left, top, width: right - left, height: bottom - top };
}

export function drawSelectionHighlight(ctx: CanvasRenderingContext2D, ann: Annotation, byId?: Map<string, Annotation>) {
  const { left, top, width, height } = getAnnotationBounds(ann, byId);
  ctx.save();
  ctx.strokeStyle = "#1976d2";
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 5]);
  ctx.strokeRect(left, top, width, height);
  ctx.setLineDash([]);
  ctx.restore();
}

export function translateAnnotation(ann: Annotation, dx: number, dy: number): Annotation {
  if (ann.tool === "connector") return ann;
  if (ann.tool === "text") return { ...ann, x: ann.x + dx, y: ann.y + dy };
  return { ...ann, x1: ann.x1 + dx, y1: ann.y1 + dy, x2: ann.x2 + dx, y2: ann.y2 + dy };
}

export function pruneOrphanConnectors(annotations: Annotation[]): Annotation[] {
  const ids = new Set(annotations.map((ann) => ann.id));
  return annotations.filter(
    (ann) => ann.tool !== "connector" || (ids.has(ann.fromId) && ids.has(ann.toId))
  );
}

export function cloneAnnotation(ann: Annotation): Annotation {
  return { ...ann, style: cloneStyle(ann.style) } as Annotation;
}
