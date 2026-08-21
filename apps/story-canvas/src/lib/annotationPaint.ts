import type {
  Annotation,
  AnnotationStyle,
  Paint,
  ShapeAnnotation,
  TextAnnotation,
  ToolKind,
} from "./annotationTypes";

export const DEFAULT_STROKE: Paint = { color: "#e53935", opacity: 1 };
export const DEFAULT_TEXT_BACKGROUND: Paint = { color: "#ffffff", opacity: 0.92 };
export const DEFAULT_STROKE_WIDTH = 3;

export function toRgba(color: string, opacity: number): string {
  const hex = color.replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

export function resolveStrokeWidth(style: AnnotationStyle): number {
  return style.strokeWidth ?? DEFAULT_STROKE_WIDTH;
}

export function defaultStyleForTool(tool: ToolKind): AnnotationStyle {
  switch (tool) {
    case "text":
      return { stroke: { ...DEFAULT_STROKE }, fill: null, background: { ...DEFAULT_TEXT_BACKGROUND } };
    case "rectangle":
    case "circle":
      return { stroke: { ...DEFAULT_STROKE }, fill: null, background: null };
    case "connector":
      return { stroke: { color: "#1e88e5", opacity: 1 }, fill: null, background: null, strokeWidth: 2 };
    default:
      return { stroke: { ...DEFAULT_STROKE }, fill: null, background: null };
  }
}

export function activePaintSlot(tool: ToolKind): "fill" | "background" | null {
  if (tool === "text") return "background";
  if (tool === "rectangle" || tool === "circle") return "fill";
  return null;
}

export type LegacyAnnotation = {
  id: string;
  tool: string;
  color?: string;
  fillColor?: string | null;
  style?: AnnotationStyle;
  x1?: number; y1?: number; x2?: number; y2?: number;
  x?: number; y?: number; width?: number; height?: number;
  text?: string; fontSize?: number;
};

export function isLegacyAnnotation(ann: Annotation | LegacyAnnotation): ann is LegacyAnnotation {
  return !("style" in ann) || ann.style == null;
}

export function migrateLegacyAnnotation(ann: LegacyAnnotation): Annotation {
  const stroke: Paint = { color: ann.color ?? DEFAULT_STROKE.color, opacity: 1 };
  if (ann.tool === "text") {
    return {
      id: ann.id, tool: "text", x: ann.x ?? 0, y: ann.y ?? 0, width: ann.width ?? 0, height: ann.height ?? 0,
      text: ann.text ?? "", fontSize: ann.fontSize ?? 20,
      style: { stroke, fill: null, background: ann.fillColor ? { color: ann.fillColor, opacity: 1 } : null },
    };
  }
  return {
    id: ann.id, tool: ann.tool as ShapeAnnotation["tool"],
    x1: ann.x1 ?? 0, y1: ann.y1 ?? 0, x2: ann.x2 ?? 0, y2: ann.y2 ?? 0,
    style: { stroke, fill: ann.fillColor ? { color: ann.fillColor, opacity: 1 } : null, background: null },
  };
}

export function normalizeAnnotation(ann: Annotation | LegacyAnnotation): Annotation {
  if (!isLegacyAnnotation(ann)) return ann;
  return migrateLegacyAnnotation(ann);
}

export function migrateAnnotations(raw: unknown[] | undefined): Annotation[] {
  if (!Array.isArray(raw) || !raw.length) return [];
  return raw.map((item) => normalizeAnnotation(item as Annotation | LegacyAnnotation));
}

export function maxAnnotationIdNumber(annotations: Annotation[]): number {
  return annotations.reduce((max, ann) => {
    const match = ann.id.match(/^ann-(\d+)$/);
    return match ? Math.max(max, parseInt(match[1], 10)) : max;
  }, 0);
}

export function cloneStyle(style: AnnotationStyle): AnnotationStyle {
  return {
    stroke: { ...style.stroke },
    fill: style.fill ? { ...style.fill } : null,
    background: style.background ? { ...style.background } : null,
    strokeWidth: style.strokeWidth,
  };
}
