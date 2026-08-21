export type Paint = {
  color: string;
  opacity: number;
};

export type AnnotationStyle = {
  stroke: Paint;
  fill: Paint | null;
  background: Paint | null;
  strokeWidth?: number;
};

export type ToolKind = "line" | "arrow" | "rectangle" | "circle" | "text" | "connector";

export type ShapeAnnotation = {
  id: string;
  tool: Exclude<ToolKind, "text" | "connector">;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  style: AnnotationStyle;
};

export type TextAnnotation = {
  id: string;
  tool: "text";
  x: number;
  y: number;
  width: number;
  height: number;
  text: string;
  fontSize: number;
  style: AnnotationStyle;
};

/** Dashed arrow linking two annotations (or a note callout region). */
export type ConnectorAnnotation = {
  id: string;
  tool: "connector";
  fromId: string;
  toId: string;
  label?: string;
  style: AnnotationStyle;
};

export type Annotation = ShapeAnnotation | TextAnnotation | ConnectorAnnotation;

export const ANNOTATION_SCHEMA_VERSION = 1;

export const TOOL_CAPABILITIES = {
  line: { fill: false, background: false },
  arrow: { fill: false, background: false },
  rectangle: { fill: true, background: false },
  circle: { fill: true, background: false },
  text: { fill: false, background: true },
  connector: { fill: false, background: false },
} as const;

export type AnnotatorTool = "select" | ToolKind;

export type AnnotationSaveResult = {
  rasterDataUrl: string;
  annotations: Annotation[];
  /** Freeform side-panel notes alongside the annotated image. */
  annotationNotes?: string;
  schemaVersion: typeof ANNOTATION_SCHEMA_VERSION;
};
