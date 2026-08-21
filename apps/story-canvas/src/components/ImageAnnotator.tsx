import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  cloneAnnotation,
  drawAllAnnotations,
  drawSelectionHighlight,
  drawShape,
  layoutTextAnnotation,
  pruneOrphanConnectors,
  resolveConnectorEndpoints,
  resolveTextAnnotationHeight,
  type ShapeDraft,
  translateAnnotation,
} from "../lib/annotationDraw";
import {
  activePaintSlot,
  cloneStyle,
  DEFAULT_TEXT_BACKGROUND,
  defaultStyleForTool,
  maxAnnotationIdNumber,
  migrateAnnotations,
  resolveStrokeWidth,
  toRgba,
} from "../lib/annotationPaint";
import type {
  AnnotatorTool,
  Annotation,
  AnnotationSaveResult,
  AnnotationStyle,
  ConnectorAnnotation,
  Paint,
  ShapeAnnotation,
  TextAnnotation,
  ToolKind,
} from "../lib/annotationTypes";
import { ANNOTATION_SCHEMA_VERSION, TOOL_CAPABILITIES } from "../lib/annotationTypes";
import { annotationsToInstructions, hasMeaningfulAnnotations } from "../annotationInstructions";

const HIT_TOLERANCE = 10;
const COLOR_SWATCHES = [
  { label: "Red", value: "#e53935", light: false },
  { label: "Orange", value: "#fb8c00", light: false },
  { label: "Yellow", value: "#fdd835", light: true },
  { label: "Green", value: "#43a047", light: false },
  { label: "Blue", value: "#1e88e5", light: false },
  { label: "Purple", value: "#8e24aa", light: false },
  { label: "Black", value: "#212121", light: false },
  { label: "White", value: "#ffffff", light: true },
] as const;
type TextSize = "S" | "M" | "L";
const TEXT_FONT_SIZES: Record<TextSize, number> = { S: 14, M: 20, L: 28 };
type TextEditorState = { x: number; y: number; width: number; height: number; value: string; fontSize: number; style: AnnotationStyle };

function paintsEqual(a: Paint | null, b: Paint | null) {
  if (!a && !b) return true;
  if (!a || !b) return false;
  return a.color === b.color && a.opacity === b.opacity;
}
function whitePaintForTool(tool: ToolKind): Paint {
  return tool === "text" ? { color: "#ffffff", opacity: 0.92 } : { color: "#ffffff", opacity: 1 };
}
function distToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number) {
  const dx = x2 - x1, dy = y2 - y1, lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - x1, py - y1);
  let t = ((px - x1) * dx + (py - y1) * dy) / lenSq;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}
function hitTestAnnotation(ann: Annotation, x: number, y: number, byId?: Map<string, Annotation>) {
  const tol = HIT_TOLERANCE + resolveStrokeWidth(ann.style);
  if (ann.tool === "connector") {
    if (!byId) return false;
    const endpoints = resolveConnectorEndpoints(ann, byId);
    if (!endpoints) return false;
    return distToSegment(x, y, endpoints.x1, endpoints.y1, endpoints.x2, endpoints.y2) <= tol;
  }
  if (ann.tool === "text") {
    const height = resolveTextAnnotationHeight(ann);
    return x >= ann.x && x <= ann.x + ann.width && y >= ann.y && y <= ann.y + height;
  }
  switch (ann.tool) {
    case "line":
    case "arrow":
      return distToSegment(x, y, ann.x1, ann.y1, ann.x2, ann.y2) <= tol;
    case "rectangle": {
      const left = Math.min(ann.x1, ann.x2), top = Math.min(ann.y1, ann.y2), right = Math.max(ann.x1, ann.x2), bottom = Math.max(ann.y1, ann.y2);
      return x >= left - tol && x <= right + tol && y >= top - tol && y <= bottom + tol;
    }
    case "circle": {
      const cx = (ann.x1 + ann.x2) / 2, cy = (ann.y1 + ann.y2) / 2;
      const rx = Math.max(Math.abs(ann.x2 - ann.x1) / 2, 0.5), ry = Math.max(Math.abs(ann.y2 - ann.y1) / 2, 0.5);
      const nx = (x - cx) / rx, ny = (y - cy) / ry;
      return nx * nx + ny * ny <= 1 + (tol / Math.min(rx, ry)) ** 2;
    }
    default:
      return false;
  }
}
function findAnnotationAt(annotations: Annotation[], x: number, y: number) {
  const byId = new Map(annotations.map((ann) => [ann.id, ann]));
  for (let i = annotations.length - 1; i >= 0; i--) {
    if (hitTestAnnotation(annotations[i], x, y, byId)) return annotations[i];
  }
  return null;
}
function isLinkableAnnotation(ann: Annotation | null): ann is Exclude<Annotation, ConnectorAnnotation> {
  return Boolean(ann && ann.tool !== "connector");
}
function clientToImagePoint(canvas: HTMLCanvasElement, img: HTMLImageElement, clientX: number, clientY: number) {
  const rect = canvas.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  const x = ((clientX - rect.left) / rect.width) * img.naturalWidth;
  const y = ((clientY - rect.top) / rect.height) * img.naturalHeight;
  if (x < 0 || y < 0 || x > img.naturalWidth || y > img.naturalHeight) return null;
  return { x, y };
}
function imageToDisplayRect(canvas: HTMLCanvasElement, img: HTMLImageElement, x: number, y: number, width: number, height: number) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = rect.width / img.naturalWidth, scaleY = rect.height / img.naturalHeight;
  return { left: x * scaleX, top: y * scaleY, width: Math.max(width * scaleX, 48), height: Math.max(height * scaleY, 24) };
}
function renderAnnotatedImageCanvas(img: HTMLImageElement, annotations: Annotation[]) {
  const exportCanvas = document.createElement("canvas");
  exportCanvas.width = img.naturalWidth;
  exportCanvas.height = img.naturalHeight;
  const ctx = exportCanvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(img, 0, 0);
  drawAllAnnotations(ctx, annotations);
  return exportCanvas;
}
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
function downloadDataUrl(dataUrl: string, filename: string) {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  a.click();
}
function isCommittableDraft(draft: ShapeDraft | null, draftTool: AnnotatorTool): draft is ShapeDraft {
  if (!draft || draftTool === "text") return false;
  return Math.hypot(draft.x2 - draft.x1, draft.y2 - draft.y1) >= 2;
}

function pendingTextAnnotation(editor: TextEditorState): TextAnnotation | null {
  if (!editor.value.trim()) return null;
  const text = editor.value.replace(/\r\n/g, "\n");
  const { height } = layoutTextAnnotation({ text, width: editor.width, fontSize: editor.fontSize });
  return {
    id: "pending-text",
    tool: "text",
    x: editor.x,
    y: editor.y,
    width: editor.width,
    height,
    text,
    fontSize: editor.fontSize,
    style: cloneStyle(editor.style),
  };
}

function withTextEditorLayout(editor: TextEditorState, value: string): TextEditorState {
  const text = value.replace(/\r\n/g, "\n");
  const { height } = layoutTextAnnotation({ text, width: editor.width, fontSize: editor.fontSize });
  const minHeight = editor.fontSize * 1.5;
  return { ...editor, value, height: Math.max(minHeight, height) };
}

function pendingShapeAnnotation(draft: ShapeDraft): ShapeAnnotation {
  return {
    tool: draft.tool,
    x1: draft.x1,
    y1: draft.y1,
    x2: draft.x2,
    y2: draft.y2,
    id: "pending-shape",
    style: cloneStyle(draft.style),
  };
}

export function ImageAnnotator({
  src,
  initialAnnotations,
  initialAnnotationNotes,
  onSave,
  onCancel,
}: {
  src: string;
  initialAnnotations?: Annotation[];
  initialAnnotationNotes?: string;
  onSave: (result: AnnotationSaveResult) => void;
  onCancel: () => void;
}) {
  const initial = useMemo(() => migrateAnnotations(initialAnnotations), [initialAnnotations]);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textInputRef = useRef<HTMLTextAreaElement>(null);
  const annotationIdRef = useRef(maxAnnotationIdNumber(initial));
  const [tool, setTool] = useState<AnnotatorTool>("select");
  const [activeStyle, setActiveStyle] = useState<AnnotationStyle>(() => defaultStyleForTool("line"));
  const [textSize, setTextSize] = useState<TextSize>("M");
  const [annotations, setAnnotations] = useState<Annotation[]>(initial);
  const [annotationNotes, setAnnotationNotes] = useState(initialAnnotationNotes ?? "");
  const [connectorSourceId, setConnectorSourceId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [draft, setDraft] = useState<ShapeDraft | null>(null);
  const [textEditor, setTextEditor] = useState<TextEditorState | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const copyFeedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const drawingRef = useRef(false);
  const draftToolRef = useRef<AnnotatorTool>("line");
  const draftSnapshotRef = useRef<ShapeDraft | null>(null);
  const draggingRef = useRef(false);
  const dragOriginRef = useRef<{ x: number; y: number; id: string; snapshot: Annotation } | null>(null);

  useEffect(() => { draftSnapshotRef.current = draft; }, [draft]);

  const hasCommittedAnnotations = useMemo(() => hasMeaningfulAnnotations(annotations), [annotations]);
  const canCopyInstructions = useMemo(() => {
    if (annotationNotes.trim()) return true;
    if (hasCommittedAnnotations) return true;
    if (textEditor?.value.trim()) return true;
    return isCommittableDraft(draft, draftToolRef.current);
  }, [annotationNotes, hasCommittedAnnotations, textEditor, draft]);
  const canUndoOrClear =
    hasCommittedAnnotations ||
    Boolean(annotationNotes.trim()) ||
    isCommittableDraft(draft, draftToolRef.current) ||
    Boolean(textEditor?.value.trim()) ||
    Boolean(connectorSourceId);

  const selected = selectedId ? annotations.find((a) => a.id === selectedId) ?? null : null;
  const capabilityTool: ToolKind | null = selected?.tool ?? (tool !== "select" ? tool : null);
  const paintSlot = capabilityTool ? activePaintSlot(capabilityTool) : null;
  const activeFillPaint = paintSlot === "background" ? activeStyle.background : paintSlot === "fill" ? activeStyle.fill : null;
  const showFillRow = capabilityTool !== null && (TOOL_CAPABILITIES[capabilityTool].fill || TOOL_CAPABILITIES[capabilityTool].background);
  const fillLabel = capabilityTool === "text" || selected?.tool === "text" ? "Background" : "Fill";
  const whitePreset = capabilityTool !== null ? whitePaintForTool(capabilityTool) : DEFAULT_TEXT_BACKGROUND;

  const nextAnnotationId = useCallback(() => { annotationIdRef.current += 1; return `ann-${annotationIdRef.current}`; }, []);
  const patchSelectedStyle = useCallback((patch: Partial<AnnotationStyle>) => {
    if (!selectedId) return;
    setAnnotations((prev) => prev.map((ann) => (ann.id === selectedId ? { ...ann, style: { ...ann.style, ...patch } } : ann)));
  }, [selectedId]);
  const handleColorChange = useCallback((color: string) => {
    setActiveStyle((prev) => ({ ...prev, stroke: { ...prev.stroke, color } }));
    if (selectedId) setAnnotations((prev) => prev.map((ann) => ann.id === selectedId ? { ...ann, style: { ...ann.style, stroke: { ...ann.style.stroke, color } } } : ann));
  }, [selectedId]);
  const handleFillChange = useCallback((paint: Paint | null) => {
    if (!paintSlot) return;
    const nextPaint = paint ? { ...paint } : null;
    setActiveStyle((prev) => ({ ...prev, [paintSlot]: nextPaint }));
    if (selectedId) patchSelectedStyle({ [paintSlot]: nextPaint });
    setTextEditor((prev) => (prev ? { ...prev, style: { ...prev.style, [paintSlot]: nextPaint } } : prev));
  }, [paintSlot, patchSelectedStyle, selectedId]);
  const syncFromAnnotation = useCallback((ann: Annotation) => setActiveStyle(cloneStyle(ann.style)), []);

  const paint = useCallback(() => {
    const canvas = canvasRef.current, img = imgRef.current;
    if (!canvas || !img || !img.naturalWidth) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(rect.width));
    canvas.height = Math.max(1, Math.round(rect.height));
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.scale(canvas.width / img.naturalWidth, canvas.height / img.naturalHeight);
    const byId = new Map(annotations.map((ann) => [ann.id, ann]));
    drawAllAnnotations(ctx, annotations);
    if (draft) drawShape(ctx, draft);
    if (connectorSourceId) {
      const source = byId.get(connectorSourceId);
      if (source && source.tool !== "connector") drawSelectionHighlight(ctx, source, byId);
    }
    if (selectedId) {
      const sel = byId.get(selectedId);
      if (sel) drawSelectionHighlight(ctx, sel, byId);
    }
    ctx.restore();
  }, [annotations, draft, selectedId, connectorSourceId]);

  useEffect(() => { paint(); }, [paint, loaded]);
  useEffect(() => { const onResize = () => paint(); window.addEventListener("resize", onResize); return () => window.removeEventListener("resize", onResize); }, [paint]);
  useEffect(() => { if (textEditor) textInputRef.current?.focus(); }, [textEditor]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { if (textEditor) { setTextEditor(null); return; } setSelectedId(null); onCancel(); return; }
      if ((e.key === "Delete" || e.key === "Backspace") && selectedId && !textEditor && !(e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement)) {
        e.preventDefault();
        setAnnotations((s) => pruneOrphanConnectors(s.filter((a) => a.id !== selectedId)));
        setSelectedId(null);
        setConnectorSourceId((cur) => (cur === selectedId ? null : cur));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel, textEditor, selectedId]);

  const beginStroke = useCallback((clientX: number, clientY: number) => {
    if (textEditor) return;
    const canvas = canvasRef.current, img = imgRef.current;
    if (!canvas || !img) return;
    const pt = clientToImagePoint(canvas, img, clientX, clientY);
    if (!pt) return;
    if (tool === "connector") {
      const hit = findAnnotationAt(annotations, pt.x, pt.y);
      if (!isLinkableAnnotation(hit)) {
        setConnectorSourceId(null);
        setSelectedId(null);
        return;
      }
      if (!connectorSourceId) {
        setConnectorSourceId(hit.id);
        setSelectedId(hit.id);
        syncFromAnnotation(hit);
        return;
      }
      if (connectorSourceId === hit.id) {
        setConnectorSourceId(null);
        setSelectedId(null);
        return;
      }
      setAnnotations((s) =>
        pruneOrphanConnectors([
          ...s,
          {
            id: nextAnnotationId(),
            tool: "connector",
            fromId: connectorSourceId,
            toId: hit.id,
            style: cloneStyle(activeStyle),
          } satisfies ConnectorAnnotation,
        ])
      );
      setConnectorSourceId(null);
      setSelectedId(null);
      return;
    }
    if (tool === "select") {
      const hit = findAnnotationAt(annotations, pt.x, pt.y);
      if (hit) {
        setSelectedId(hit.id);
        syncFromAnnotation(hit);
        if (hit.tool !== "connector") {
          draggingRef.current = true;
          setIsDragging(true);
          dragOriginRef.current = { x: pt.x, y: pt.y, id: hit.id, snapshot: cloneAnnotation(hit) };
        }
      } else setSelectedId(null);
      return;
    }
    setSelectedId(null); drawingRef.current = true; draftToolRef.current = tool;
    const style = cloneStyle(activeStyle);
    if (tool === "text") setDraft({ tool: "rectangle", x1: pt.x, y1: pt.y, x2: pt.x, y2: pt.y, style });
    else setDraft({ tool, x1: pt.x, y1: pt.y, x2: pt.x, y2: pt.y, style });
  }, [tool, textEditor, annotations, activeStyle, syncFromAnnotation, connectorSourceId, nextAnnotationId]);

  const moveStroke = useCallback((clientX: number, clientY: number) => {
    if (textEditor) return;
    if (tool === "select" && draggingRef.current && dragOriginRef.current) {
      const canvas = canvasRef.current, img = imgRef.current;
      if (!canvas || !img) return;
      const pt = clientToImagePoint(canvas, img, clientX, clientY);
      if (!pt) return;
      const { x, y, id, snapshot } = dragOriginRef.current;
      setAnnotations((prev) => prev.map((a) => (a.id === id ? translateAnnotation(snapshot, pt.x - x, pt.y - y) : a)));
      return;
    }
    if (!drawingRef.current) return;
    const canvas = canvasRef.current, img = imgRef.current;
    if (!canvas || !img) return;
    const pt = clientToImagePoint(canvas, img, clientX, clientY);
    if (!pt) return;
    setDraft((prev) => (prev ? { ...prev, x2: pt.x, y2: pt.y } : prev));
  }, [textEditor, tool]);

  const openTextEditor = useCallback((x1: number, y1: number, x2: number, y2: number) => {
    const fontSize = TEXT_FONT_SIZES[textSize];
    const left = Math.min(x1, x2), top = Math.min(y1, y2);
    let width = Math.abs(x2 - x1), height = Math.abs(y2 - y1);
    if (width < 8 && height < 8) { width = fontSize * 8; height = fontSize * 2; }
    else { width = Math.max(width, fontSize * 4); height = Math.max(height, fontSize * 1.5); }
    setTextEditor({ x: left, y: top, width, height, value: "", fontSize, style: cloneStyle(activeStyle) });
  }, [textSize, activeStyle]);

  const endStroke = useCallback(() => {
    if (tool === "select") { draggingRef.current = false; dragOriginRef.current = null; setIsDragging(false); return; }
    if (!drawingRef.current) return;
    drawingRef.current = false;
    const activeTool = draftToolRef.current;
    const prev = draftSnapshotRef.current;
    setDraft(null);
    if (!prev) return;
    if (activeTool === "text") {
      openTextEditor(prev.x1, prev.y1, prev.x2, prev.y2);
      return;
    }
    if (Math.hypot(prev.x2 - prev.x1, prev.y2 - prev.y1) < 2) return;
    setAnnotations((s) => [
      ...s,
      {
        tool: prev.tool,
        x1: prev.x1,
        y1: prev.y1,
        x2: prev.x2,
        y2: prev.y2,
        id: nextAnnotationId(),
        style: cloneStyle(prev.style),
      },
    ]);
  }, [openTextEditor, tool, nextAnnotationId]);

  const commitTextEditor = useCallback(() => {
    setTextEditor((editor) => {
      if (!editor || !editor.value.trim()) return null;
      const text = editor.value.replace(/\r\n/g, "\n");
      const { height } = layoutTextAnnotation({ text, width: editor.width, fontSize: editor.fontSize });
      setAnnotations((s) => [...s, { id: nextAnnotationId(), tool: "text", x: editor.x, y: editor.y, width: editor.width, height, text, fontSize: editor.fontSize, style: cloneStyle(editor.style) }]);
      return null;
    });
  }, [nextAnnotationId]);

  const undoAnnotation = useCallback(() => {
    if (textEditor?.value.trim()) {
      setTextEditor(null);
      return;
    }
    if (isCommittableDraft(draft, draftToolRef.current)) {
      setDraft(null);
      drawingRef.current = false;
      return;
    }
    setAnnotations((s) => {
      if (!s.length) return s;
      const removed = s[s.length - 1];
      setSelectedId((cur) => (cur === removed.id ? null : cur));
      return s.slice(0, -1);
    });
    setDraft(null);
    setTextEditor(null);
    drawingRef.current = false;
  }, [draft, textEditor]);
  const clearAll = useCallback(() => {
    setAnnotations([]);
    setAnnotationNotes("");
    setSelectedId(null);
    setConnectorSourceId(null);
    setDraft(null);
    setTextEditor(null);
    drawingRef.current = false;
  }, []);
  const selectTool = useCallback((next: AnnotatorTool) => {
    setTool(next);
    setConnectorSourceId(null);
    if (next !== "select") {
      setSelectedId(null);
      setActiveStyle(defaultStyleForTool(next));
    }
  }, []);

  const showCopyFeedback = useCallback((message: string) => {
    setCopyFeedback(message);
    if (copyFeedbackTimerRef.current) clearTimeout(copyFeedbackTimerRef.current);
    copyFeedbackTimerRef.current = setTimeout(() => setCopyFeedback(null), 2200);
  }, []);

  useEffect(() => () => { if (copyFeedbackTimerRef.current) clearTimeout(copyFeedbackTimerRef.current); }, []);

  const handleSave = useCallback(() => {
    const img = imgRef.current;
    if (!img || !img.naturalWidth) return;
    const exportCanvas = renderAnnotatedImageCanvas(img, annotations);
    if (!exportCanvas) return;
    try {
      onSave({
        rasterDataUrl: exportCanvas.toDataURL("image/png"),
        annotations: pruneOrphanConnectors(annotations),
        annotationNotes: annotationNotes.trim() || undefined,
        schemaVersion: ANNOTATION_SCHEMA_VERSION,
      });
    } catch { /* tainted */ }
  }, [onSave, annotations, annotationNotes]);

  const handleCopyInstructions = useCallback(async () => {
    const img = imgRef.current;
    const instructionAnnotations: Annotation[] = [...annotations];
    const pendingText = textEditor ? pendingTextAnnotation(textEditor) : null;
    if (pendingText) instructionAnnotations.push(pendingText);
    if (isCommittableDraft(draft, draftToolRef.current)) {
      instructionAnnotations.push(pendingShapeAnnotation(draft));
    }
    if (!hasMeaningfulAnnotations(instructionAnnotations) && !annotationNotes.trim()) return;

    const text = annotationsToInstructions(instructionAnnotations, {
      imageWidth: img?.naturalWidth,
      imageHeight: img?.naturalHeight,
      sideNotes: annotationNotes.trim() || undefined,
    });
    if (!text) return;

    try {
      await navigator.clipboard.writeText(text);
      showCopyFeedback("Instructions copied ✓");
    } catch {
      showCopyFeedback("Could not copy instructions");
    }
  }, [annotations, annotationNotes, draft, textEditor, showCopyFeedback]);

  const handleCopyImage = useCallback(async () => {
    const img = imgRef.current;
    if (!img || !img.naturalWidth) return;
    const exportCanvas = renderAnnotatedImageCanvas(img, annotations);
    if (!exportCanvas) return;

    const blob = await new Promise<Blob | null>((resolve) => exportCanvas.toBlob((b) => resolve(b), "image/png"));
    if (!blob) {
      try {
        downloadDataUrl(exportCanvas.toDataURL("image/png"), "annotated-image.png");
        showCopyFeedback("Image downloaded ✓");
      } catch { /* tainted canvas */ }
      return;
    }

    if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
      try {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        showCopyFeedback("Image copied ✓");
        return;
      } catch { /* fall through to download */ }
    }

    downloadBlob(blob, "annotated-image.png");
    showCopyFeedback("Image downloaded ✓");
  }, [annotations, showCopyFeedback]);

  const textEditorStyle = textEditor && canvasRef.current && imgRef.current ? imageToDisplayRect(canvasRef.current, imgRef.current, textEditor.x, textEditor.y, textEditor.width, textEditor.height) : null;

  return (
    <div className="sc-image-annotator" role="dialog" aria-modal="true" aria-label="Annotate image" onMouseDown={(e) => e.stopPropagation()}>
      <div className="sc-image-annotator-toolbar" role="toolbar" aria-label="Annotation tools">
        <button type="button" className={tool === "select" ? "active" : ""} onClick={() => selectTool("select")} aria-pressed={tool === "select"}>Select</button>
        <span className="sc-image-annotator-sep" aria-hidden="true" />
        {(["line", "arrow", "rectangle", "circle", "text", "connector"] as const).map((t) => (
          <button key={t} type="button" className={tool === t ? "active" : ""} onClick={() => selectTool(t)} aria-pressed={tool === t}>
            {t === "text" ? "Text" : t === "connector" ? "Connector" : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
        {tool === "text" ? (
          <span className="sc-image-annotator-text-sizes" role="group" aria-label="Text size">
            {(["S", "M", "L"] as const).map((size) => (
              <button key={size} type="button" className={`sc-image-annotator-text-size${textSize === size ? " active" : ""}`} onClick={() => setTextSize(size)} aria-pressed={textSize === size}>{size}</button>
            ))}
          </span>
        ) : null}
        <span className="sc-image-annotator-colors" role="group" aria-label="Stroke color">
          {COLOR_SWATCHES.map((swatch) => (
            <button key={swatch.value} type="button" className={`sc-image-annotator-color-swatch${swatch.light ? " light" : ""}${activeStyle.stroke.color === swatch.value ? " active" : ""}`} style={{ backgroundColor: swatch.value }} onClick={() => handleColorChange(swatch.value)} aria-pressed={activeStyle.stroke.color === swatch.value} title={swatch.label} />
          ))}
        </span>
        {showFillRow ? (
          <>
            <span className="sc-image-annotator-sep" aria-hidden="true" />
            <span className="sc-image-annotator-fill-label">{fillLabel}:</span>
            <span className="sc-image-annotator-fill" role="group" aria-label={`${fillLabel} color`}>
              <button type="button" className={`sc-image-annotator-fill-none${activeFillPaint === null ? " active" : ""}`} onClick={() => handleFillChange(null)} aria-pressed={activeFillPaint === null}>None</button>
              <button type="button" className={`sc-image-annotator-color-swatch light${paintsEqual(activeFillPaint, whitePreset) ? " active" : ""}`} style={{ backgroundColor: whitePreset.color }} onClick={() => handleFillChange(whitePreset)} aria-pressed={paintsEqual(activeFillPaint, whitePreset)} title="White" />
              {COLOR_SWATCHES.filter((s) => s.value !== "#ffffff").map((swatch) => {
                const p = { color: swatch.value, opacity: 1 };
                return <button key={`fill-${swatch.value}`} type="button" className={`sc-image-annotator-color-swatch${swatch.light ? " light" : ""}${paintsEqual(activeFillPaint, p) ? " active" : ""}`} style={{ backgroundColor: swatch.value }} onClick={() => handleFillChange(p)} aria-pressed={paintsEqual(activeFillPaint, p)} title={swatch.label} />;
              })}
            </span>
          </>
        ) : null}
        <span className="sc-image-annotator-sep" aria-hidden="true" />
        <button type="button" onClick={undoAnnotation} disabled={!canUndoOrClear}>Undo</button>
        <button type="button" onClick={clearAll} disabled={!canUndoOrClear}>Clear</button>
        <span className="sc-image-annotator-sep" aria-hidden="true" />
        <button type="button" onClick={() => void handleCopyImage()} disabled={!loaded || loadError} aria-label="Copy annotated image to clipboard">Copy image</button>
        <button type="button" onClick={() => void handleCopyInstructions()} disabled={!canCopyInstructions} aria-label="Copy edit instructions for current annotations">Copy instructions</button>
        <button type="button" className="primary" onClick={handleSave} disabled={!loaded || loadError}>Save</button>
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
      <div className="sc-image-annotator-body">
        <div className="sc-image-annotator-stage">
          <div className="sc-image-annotator-frame">
            <img ref={imgRef} src={src} alt="" draggable={false} crossOrigin="anonymous" onLoad={() => { setLoaded(true); setLoadError(false); paint(); }} onError={() => setLoadError(true)} />
            <canvas ref={canvasRef} className={`sc-image-annotator-canvas${tool === "select" ? " select-tool" : ""}${isDragging ? " dragging" : ""}`} onMouseDown={(e) => { e.preventDefault(); beginStroke(e.clientX, e.clientY); }} onMouseMove={(e) => moveStroke(e.clientX, e.clientY)} onMouseUp={endStroke} onMouseLeave={endStroke} onTouchStart={(e) => { e.preventDefault(); const t = e.changedTouches[0]; if (t) beginStroke(t.clientX, t.clientY); }} onTouchMove={(e) => { e.preventDefault(); const t = e.changedTouches[0]; if (t) moveStroke(t.clientX, t.clientY); }} onTouchEnd={(e) => { e.preventDefault(); endStroke(); }} />
            {textEditor && textEditorStyle ? (
              <textarea ref={textInputRef} className="sc-image-annotator-text-input" style={{ left: textEditorStyle.left, top: textEditorStyle.top, width: textEditorStyle.width, height: textEditorStyle.height, fontSize: `${textEditor.fontSize * (textEditorStyle.width / textEditor.width)}px`, color: toRgba(textEditor.style.stroke.color, textEditor.style.stroke.opacity), backgroundColor: textEditor.style.background ? toRgba(textEditor.style.background.color, textEditor.style.background.opacity) : "transparent", border: textEditor.style.background ? "1px solid rgba(0, 0, 0, 0.14)" : "1px dashed rgba(0, 0, 0, 0.25)" }} value={textEditor.value} placeholder="Type annotation…" onChange={(e) => setTextEditor((prev) => (prev ? withTextEditorLayout(prev, e.target.value) : prev))} onBlur={commitTextEditor} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commitTextEditor(); } }} />
            ) : null}
          </div>
          {loadError ? (
            <p className="sc-image-annotator-error">Could not load image for annotation.</p>
          ) : copyFeedback ? (
            <p className="sc-image-annotator-hint sc-image-annotator-hint-success" role="status">{copyFeedback}</p>
          ) : (
            <p className="sc-image-annotator-hint">
              {tool === "select"
                ? "Click an annotation to select · drag to move · Delete to remove · Esc to cancel"
                : tool === "connector"
                  ? connectorSourceId
                    ? "Click target annotation to link · click source again to cancel"
                    : "Click source annotation, then target · Esc to cancel"
                  : tool === "text"
                    ? "Click or drag to place text · Enter to confirm · Esc to cancel"
                    : "Draw on the image · Esc to cancel"}
            </p>
          )}
        </div>
        <aside className="sc-image-annotator-notes-panel" aria-label="Annotation notes">
          <label className="sc-image-annotator-notes-label" htmlFor="sc-image-annotator-notes">Notes</label>
          <textarea
            id="sc-image-annotator-notes"
            className="sc-image-annotator-notes-textarea"
            value={annotationNotes}
            onChange={(e) => setAnnotationNotes(e.target.value)}
            placeholder="Add change notes alongside this image…"
            spellCheck
          />
        </aside>
      </div>
    </div>
  );
}
