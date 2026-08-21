# Story Canvas — ImageAnnotator Fill Architecture (Design Spec)

> **Status:** Ready for implementation  
> **Research session:** `rp-story-canvas-fill-arch-20260813`  
> **Target files:** `apps/story-canvas/src/components/ImageAnnotator.tsx` + new `lib/annotation*.ts`  
> **Scope:** Phase 1 + Phase 2 blueprint

---

## Problem statement

`ImageAnnotator.tsx` uses flat `color` (stroke) and `fillColor` (nullable string) for all annotation types. This works for v0 but:

- Conflates **shape fill** and **text backdrop** under one property
- Shows Fill controls for line/arrow where they have no effect
- Defaults `activeFillColor` to white for all tools (shape tools should default to no fill)
- No opacity control — text on busy photos fails accessibility without adjustable backdrop
- Export bakes PNG only; annotations are lost on re-open
- Arrowhead fill is hardcoded to stroke color with no independent control

---

## Design goals

1. **Semantic clarity** — stroke, fill, and background are distinct paints
2. **Tool-appropriate UX** — controls match what each tool can do
3. **Accessibility** — text defaults to readable backdrop on photos
4. **Round-trip editing** — persist vector annotations on the node
5. **Minimal diff** — extract draw helpers; don't rewrite the component

---

## Type definitions

Create `apps/story-canvas/src/lib/annotationTypes.ts`:

```typescript
export type Paint = {
  color: string;   // #RRGGBB
  opacity: number; // 0–1, default 1
};

export type AnnotationStyle = {
  stroke: Paint;
  fill: Paint | null;        // closed shapes only
  background: Paint | null;  // text only
  strokeWidth?: number;      // default 3, Phase 2
};

export type ToolKind = "line" | "arrow" | "rectangle" | "circle" | "text";

export type ShapeAnnotation = {
  id: string;
  tool: Exclude<ToolKind, "text">;
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

export type Annotation = ShapeAnnotation | TextAnnotation;

export const ANNOTATION_SCHEMA_VERSION = 1;

export const TOOL_CAPABILITIES = {
  line: { fill: false, background: false },
  arrow: { fill: false, background: false },
  rectangle: { fill: true, background: false },
  circle: { fill: true, background: false },
  text: { fill: false, background: true },
} as const;
```

---

## Paint utilities

Create `apps/story-canvas/src/lib/annotationPaint.ts`:

```typescript
import type { Annotation, AnnotationStyle, Paint, ToolKind } from "./annotationTypes";

export const DEFAULT_STROKE: Paint = { color: "#e53935", opacity: 1 };
export const DEFAULT_TEXT_BACKGROUND: Paint = { color: "#ffffff", opacity: 0.92 };

export function toRgba(color: string, opacity: number): string {
  const hex = color.replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

export function defaultStyleForTool(tool: ToolKind): AnnotationStyle {
  switch (tool) {
    case "text":
      return {
        stroke: { ...DEFAULT_STROKE },
        fill: null,
        background: { ...DEFAULT_TEXT_BACKGROUND },
      };
    case "rectangle":
    case "circle":
      return { stroke: { ...DEFAULT_STROKE }, fill: null, background: null };
    default:
      return { stroke: { ...DEFAULT_STROKE }, fill: null, background: null };
  }
}

/** Migrate legacy { color?, fillColor? } annotations */
export function migrateLegacyAnnotation(ann: LegacyAnnotation): Annotation {
  const stroke: Paint = {
    color: ann.color ?? DEFAULT_STROKE.color,
    opacity: 1,
  };
  if (ann.tool === "text") {
    return {
      ...ann,
      style: {
        stroke,
        fill: null,
        background: ann.fillColor
          ? { color: ann.fillColor, opacity: 1 }
          : null,
      },
    };
  }
  return {
    ...ann,
    style: {
      stroke,
      fill: ann.fillColor ? { color: ann.fillColor, opacity: 1 } : null,
      background: null,
    },
  };
}
```

---

## Draw pipeline refactor

Extract to `apps/story-canvas/src/lib/annotationDraw.ts`:

### Render order (per annotation)

| Tool | Order |
|------|-------|
| rectangle, circle | 1. fill 2. stroke |
| line, arrow | stroke (+ filled arrowhead using stroke paint) |
| text | 1. background rect 2. border 3. text glyphs |

### Key functions

```typescript
export function drawAnnotation(
  ctx: CanvasRenderingContext2D,
  ann: Annotation,
  constants: DrawConstants
): void;

export function drawAllAnnotations(
  ctx: CanvasRenderingContext2D,
  annotations: Annotation[],
  constants: DrawConstants
): void;
```

### Text backdrop (preserve current behavior, use Paint)

```typescript
const pad = TEXT_BACKDROP_PAD;
if (style.background) {
  ctx.fillStyle = toRgba(style.background.color, style.background.opacity);
  ctx.fillRect(boxLeft, boxTop, boxWidth, boxHeight);
  ctx.strokeStyle = TEXT_BACKDROP_BORDER; // keep subtle border
  ctx.lineWidth = 1;
  ctx.strokeRect(boxLeft + 0.5, boxTop + 0.5, boxWidth - 1, boxHeight - 1);
}
ctx.fillStyle = toRgba(style.stroke.color, style.stroke.opacity);
// fillText...
```

---

## Toolbar UX

### Stroke row (unchanged visually)

- Label: **Stroke**
- Swatches update `activeStyle.stroke.color`
- When annotation selected, patch `style.stroke`

### Fill / Background row (contextual label)

```typescript
const fillLabel = tool === "text" || selected?.tool === "text"
  ? "Background"
  : "Fill";

const showFillRow =
  TOOL_CAPABILITIES[currentTool].fill ||
  TOOL_CAPABILITIES[currentTool].background ||
  (selected && (selected.tool === "text" || selected.tool === "rectangle" || selected.tool === "circle"));
```

- **None** → set `fill` or `background` to `null` (depending on tool)
- **White** → `{ color: "#ffffff", opacity: tool === "text" ? 0.92 : 1 }`
- Color swatches → set active paint slot

### Active paint slot resolver

```typescript
function activePaintSlot(tool: ToolKind): "fill" | "background" | null {
  if (tool === "text") return "background";
  if (tool === "rectangle" || tool === "circle") return "fill";
  return null;
}
```

### Phase 2: Opacity slider

- Range 0–100%, maps to `paint.opacity`
- Default: stroke 100%, shape fill 100%, text background 92%
- Show only when active paint slot is non-null OR selected annotation has that paint set

---

## Export & persistence

### Save payload

```typescript
export type AnnotationSaveResult = {
  rasterDataUrl: string;
  annotations: Annotation[];
  schemaVersion: typeof ANNOTATION_SCHEMA_VERSION;
};

// ImageAnnotator props
onSave: (result: AnnotationSaveResult) => void;
initialAnnotations?: Annotation[];
```

### App.tsx integration

Extend image node data:

```typescript
type ImageNodeData = {
  src: string;
  annotations?: Annotation[];
  annotationSchemaVersion?: number;
};
```

On annotate save:
1. Store `annotations` on node
2. Replace node `src` with baked PNG (current behavior)
3. On re-open annotator, pass `initialAnnotations`

---

## Implementation phases

### Phase 1 — Quick wins (target: 1 PR, ≤5 files)

| Task | File |
|------|------|
| Add types + paint utils | `lib/annotationTypes.ts`, `lib/annotationPaint.ts` |
| Extract draw functions | `lib/annotationDraw.ts` |
| Wire ImageAnnotator to new types | `ImageAnnotator.tsx` |
| Tool-scoped fill row visibility + labels | `ImageAnnotator.tsx` |
| Persist annotations on save | `ImageAnnotator.tsx`, `App.tsx` |
| Legacy migration on load | `annotationPaint.ts` |

**Acceptance criteria:**
- [ ] Rect/circle fill works as today
- [ ] Text backdrop works as today
- [ ] Line tool hides Fill row
- [ ] Re-opening annotator restores annotations
- [ ] PNG export visually identical to today
- [ ] `npx tsc --noEmit` passes in story-canvas

### Phase 2 — Structural (target: 1 PR)

| Task | Notes |
|------|-------|
| Opacity slider | Toolbar + `toRgba` already supports |
| Stroke width control | Add to `AnnotationStyle`, draw functions |
| Selection sync for all paints | `syncFromAnnotation` reads full style |
| Arrow head fill mode | `headFill: 'stroke'` default |

### Phase 3 — Optional

- Highlight/pen tool (semi-transparent freehand)
- Gradient fills via `CanvasGradient`
- "Match stroke" fill shortcut

---

## File change map

```
apps/story-canvas/src/
  lib/
    annotationTypes.ts      NEW
    annotationPaint.ts      NEW
    annotationDraw.ts       NEW (extracted from ImageAnnotator)
  components/
    ImageAnnotator.tsx      MODIFY — state uses AnnotationStyle, thinner component
  App.tsx                   MODIFY — persist annotations on image nodes
```

---

## Testing checklist

1. Draw rect outline only (fill None) → export → re-open → still outline
2. Draw rect filled red → export → re-open → fill preserved
3. Text with white backdrop on busy photo → readable
4. Text with None backdrop → no box
5. Line tool → no Fill row visible
6. Select rect, change fill while stroke unchanged
7. Resize window → annotations scale correctly (existing behavior)
8. Undo/clear all still works

---

## References

- Research report: `rp-story-canvas-fill-arch-20260813`
- Excalidraw elements: https://docs.excalidraw.com/docs/@excalidraw/excalidraw/api/excalidraw-element-skeleton
- tldraw default shapes: https://tldraw.dev/sdk-features/default-shapes
- Figma Paint: https://developers.figma.com/docs/plugins/api/Paint/
- Current implementation: `apps/story-canvas/src/components/ImageAnnotator.tsx`
