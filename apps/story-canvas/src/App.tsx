import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  MiniMap,
  Panel,
  useReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type OnSelectionChangeParams,
  type ReactFlowInstance,
  MarkerType,
  ConnectionMode,
  SelectionMode,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import {
  EDGE_TYPES,
  type EdgeType,
  type GraphEdge,
  type GraphNode,
  type NodeKind,
  type StoryProject,
  blankTemplate,
  guidedStoryTemplate,
  nextSequence,
  typeLabel,
  uid,
} from "./domain";
import {
  deleteProject,
  downloadPortableProjectJson,
  portableProjectJsonString,
  exportOd,
  getLocalHistoryEntry,
  hasSavedStories,
  importLocalProject,
  listProjects,
  loadLastProjectId,
  loadLocal,
  loadLocalHistory,
  loadProject,
  persistLocal,
  preloadLocalCreations,
  readProjectFile,
  removeLocalHistory,
  removeLocalHistoryBulk,
  researchDetail,
  researchLibrary,
  friendlyResearchErrorMessage,
  friendlySaveErrorMessage,
  saveProject,
  storyCanvasResearch,
  toEpochMs,
  uploadAsset,
  type ProjectSummary,
} from "./api";
import { mergeFlowNodeFromPrev } from "./flowNodeSync";
import { dimensionsFromFlowNode, flowNodeStyleForGraphNode } from "./nodeSizing";
import { nodeTypes, type StoryFlowNode, type StoryNodeData } from "./nodes/StoryNodes";
import {
  MAX_VIDEO_BYTES,
  classifyFile,
  isEditableTarget,
  parseClipboardData,
  parseFileList,
  type ClipboardAsset,
} from "./clipboardAssets";
import { BoardView, OutlineView, PresentView } from "./views/SideViews";
import {
  mergeProjectRows,
  ProjectsPanel,
  ProjectsSidebar,
  type ProjectSource,
} from "./views/ProjectsPanel";
import { CardSearchBar } from "./CardSearchBar";
import type { CardSearchResult } from "./cardSearch";
import { createUndoStacks, type GraphSnapshot } from "./graphHistory";
import { NodeResearchMenu, type ResearchMenuState } from "./NodeResearchMenu";
import { ImageAnnotator } from "./components/ImageAnnotator";
import type { AnnotationSaveResult } from "./lib/annotationTypes";
import { hasRealMedia } from "./mediaHelpers";
import { captureEditableFocus, type EditableFocusSnap } from "./editableFocus";
import { queryFromNode, researchBodyFromHits } from "./researchQuery";
import { applyAlignAction, rectsForIds, type AlignAction } from "./alignNodes";
import { buildAgentBrief } from "./agentBrief";
import { copyNodeAnnotationInstructions, nodeHasAnnotationInstructions } from "./annotationInstructions";

type ViewMode = "canvas" | "outline" | "board" | "present";
type CanvasTool = "select" | "pan";

const STORIES_PANEL_KEY = "story-canvas:storiesPanelOpen";
const CANVAS_TOOL_KEY = "story-canvas:canvasTool";

function readCanvasTool(): CanvasTool {
  try {
    return sessionStorage.getItem(CANVAS_TOOL_KEY) === "pan" ? "pan" : "select";
  } catch {
    return "select";
  }
}

function CanvasDock({
  tool,
  onChange,
}: {
  tool: CanvasTool;
  onChange: (tool: CanvasTool) => void;
}) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();

  return (
    <Panel position="bottom-left" className="sc-canvas-dock">
      <div className="sc-canvas-tools" role="toolbar" aria-label="Canvas tools">
        <button
          type="button"
          className={tool === "select" ? "active" : ""}
          onClick={() => onChange("select")}
          aria-pressed={tool === "select"}
          aria-label="Select tool"
          title="Select (V)"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path
              d="M3.5 2.5 12 8.5 8 9.5 9.5 13.5 8 14 6.5 9.5 3.5 10.5Z"
              fill="currentColor"
              stroke="currentColor"
              strokeWidth="0.5"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        <button
          type="button"
          className={tool === "pan" ? "active" : ""}
          onClick={() => onChange("pan")}
          aria-pressed={tool === "pan"}
          aria-label="Hand tool"
          title="Hand (H)"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path
              d="M8 2.5c-.4 0-.8.3-.8.8V8H6.5c-.4 0-.8.3-.8.8v.2c0 .4.3.7.7.7H7v1.5c0 .8.7 1.5 1.5 1.5h2c.8 0 1.5-.7 1.5-1.5V9.7h1.3c.4 0 .7-.3.7-.7v-.2c0-.4-.3-.8-.7-.8H10V3.3c0-.4-.3-.8-.8-.8-.4 0-.8.3-.8.8V8H8.8V3.3c0-.4-.3-.8-.8-.8Z"
              fill="currentColor"
            />
          </svg>
        </button>
      </div>
      <div className="sc-canvas-controls" role="toolbar" aria-label="Zoom controls">
        <button type="button" onClick={() => zoomIn()} aria-label="Zoom in" title="Zoom in">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
        <button type="button" onClick={() => zoomOut()} aria-label="Zoom out" title="Zoom out">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M3 8h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
        <button
          type="button"
          onClick={() => fitView({ padding: 0.15 })}
          aria-label="Fit view"
          title="Fit view"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path
              d="M3 6V3h3M10 3h3v3M13 10v3h-3M6 13H3v-3"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </Panel>
  );
}

function readStoriesPanelOpen(): boolean {
  try {
    return localStorage.getItem(STORIES_PANEL_KEY) === "true";
  } catch {
    return false;
  }
}

function StoriesPanelToggle({
  open,
  onClick,
  className,
}: {
  open: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`sc-stories-toggle${open ? " active" : ""}${className ? ` ${className}` : ""}`}
      onClick={onClick}
      aria-label="Toggle stories panel"
      aria-expanded={open}
      title={open ? "Hide stories panel" : "Show stories panel"}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </button>
  );
}

function edgesToGraph(flowEdges: Edge[]): GraphEdge[] {
  return flowEdges.map((e) => ({
    id: e.id,
    from: e.source,
    to: e.target,
    type: ((e.data as { edgeType?: EdgeType })?.edgeType || "follows") as EdgeType,
  }));
}

function fileToDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

async function persistImageSrc(
  src: string,
  projectId: string | null,
  filename?: string
): Promise<string> {
  let out = src;
  if (out.startsWith("blob:")) {
    try {
      const res = await fetch(out);
      const blob = await res.blob();
      out = await fileToDataUrl(
        new File([blob], filename || "paste.png", { type: blob.type || "image/png" })
      );
    } catch {
      return src;
    }
  }
  if (projectId && out.startsWith("data:") && out.length > 120_000) {
    try {
      const up = await uploadAsset(projectId, out, filename);
      out = up.url;
    } catch {
      /* keep data url */
    }
  }
  return out;
}

function toFlowNodes(
  graph: GraphNode[],
  bind: (id: string, kind: GraphNode["type"]) => Partial<StoryNodeData>
): StoryFlowNode[] {
  return graph.map((n) => ({
    id: n.id,
    type: "story",
    position: { x: n.x, y: n.y },
    style: flowNodeStyleForGraphNode(n),
    data: {
      kind: n.type,
      title: n.title,
      body: n.body,
      src: n.src,
      sequenceIndex: n.sequenceIndex,
      provenance: n.provenance,
      researchSessionId: n.researchSessionId,
      ...bind(n.id, n.type),
    },
  }));
}

function toFlowEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((e) => ({
    id: e.id,
    source: e.from,
    target: e.to,
    className: `edge-${e.type}`,
    label: e.type,
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    data: { edgeType: e.type },
  }));
}

function fromFlow(
  nodes: Node[],
  edges: Edge[],
  prev: GraphNode[]
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const prevMap = new Map(prev.map((n) => [n.id, n]));
  const gNodes: GraphNode[] = nodes.map((n) => {
    const d = n.data as StoryNodeData;
    const old = prevMap.get(n.id);
    // Prefer graphRef (prev) for content — board edits update graphNodes but hidden
    // React Flow nodes can stay stale until the next canvas visit.
    const dims = dimensionsFromFlowNode(n);
    return {
      id: n.id,
      type: old?.type ?? d.kind,
      x: n.position.x,
      y: n.position.y,
      title: old?.title ?? d.title,
      body: old?.body ?? d.body ?? "",
      src: old?.src ?? d.src,
      sequenceIndex: old?.sequenceIndex ?? d.sequenceIndex ?? 0,
      provenance: old?.provenance ?? d.provenance,
      researchSessionId: old?.researchSessionId ?? d.researchSessionId,
      width: dims.width ?? old?.width,
      height: dims.height ?? old?.height,
      frameId: old?.frameId,
      annotations: old?.annotations,
      annotationSchemaVersion: old?.annotationSchemaVersion,
    };
  });
  const gEdges: GraphEdge[] = edges.map((e) => ({
    id: e.id,
    from: e.source,
    to: e.target,
    type: ((e.data as any)?.edgeType || "follows") as EdgeType,
  }));
  return { nodes: gNodes, edges: gEdges };
}

export default function App() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [title, setTitle] = useState("Untitled story");
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [edgeType, setEdgeType] = useState<EdgeType>("follows");
  const [view, setView] = useState<ViewMode>("canvas");
  const [status, setStatus] = useState("Ready");
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [localHistory, setLocalHistory] = useState(() => loadLocalHistory());
  const [projectsOpen, setProjectsOpen] = useState(false);
  const [welcomeMode, setWelcomeMode] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const [storiesPanelOpen, setStoriesPanelOpen] = useState(readStoriesPanelOpen);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [boardFocusId, setBoardFocusId] = useState<string | null>(null);
  const [cardSearchQuery, setCardSearchQuery] = useState("");
  const [scrollToCardId, setScrollToCardId] = useState<string | null>(null);
  const [presentIndex, setPresentIndex] = useState(0);
  const [composerMode, setComposerMode] = useState<"text" | "beat" | "research" | "prompt" | "session">("text");
  const [query, setQuery] = useState("");
  const [researchUi, setResearchUi] = useState<ResearchMenuState>(null);
  const [researchLoading, setResearchLoading] = useState(false);
  const [annotateTarget, setAnnotateTarget] = useState<{
    nodeId: string;
    src: string;
    initialAnnotations?: import("./lib/annotationTypes").Annotation[];
    initialAnnotationNotes?: string;
  } | null>(null);
  const [canvasTool, setCanvasTool] = useState<CanvasTool>(readCanvasTool);
  const saveTimer = useRef<number | null>(null);
  const saveBtnTimer = useRef<number | null>(null);
  const statusHoldUntilRef = useRef(0);
  const [saving, setSaving] = useState(false);
  const [copying, setCopying] = useState(false);
  const [copyingBrief, setCopyingBrief] = useState(false);
  const [saveBtnFlash, setSaveBtnFlash] = useState<"idle" | "saved" | "local">("idle");
  const graphRef = useRef<GraphNode[]>([]);
  const bootedRef = useRef(false);
  const canvasReadyRef = useRef(false);
  const flowRef = useRef<ReactFlowInstance<StoryFlowNode, Edge> | null>(null);
  const selectedIdsRef = useRef<string[]>([]);
  const edgesRef = useRef<Edge[]>([]);
  const undoStacksRef = useRef(createUndoStacks());
  const textEditNodeRef = useRef<string | null>(null);
  /** Editable focused when the node context menu opened — restored on dismiss. */
  const priorEditFocusRef = useRef<EditableFocusSnap | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<StoryFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  const syncEdgesFromGraph = useCallback(
    (gEdges: GraphEdge[]) => setEdges(toFlowEdges(gEdges)),
    [setEdges]
  );

  const getSnapshot = useCallback((): GraphSnapshot => {
    return {
      nodes: structuredClone(graphRef.current),
      edges: edgesToGraph(edgesRef.current),
    };
  }, []);

  const applySnapshot = useCallback(
    (snap: GraphSnapshot) => {
      graphRef.current = snap.nodes;
      setGraphNodes(snap.nodes);
      syncEdgesFromGraph(snap.edges);
      textEditNodeRef.current = null;
    },
    [syncEdgesFromGraph]
  );

  const pushUndo = useCallback(() => {
    undoStacksRef.current.push(getSnapshot());
  }, [getSnapshot]);

  const performUndo = useCallback(() => {
    const prev = undoStacksRef.current.undo(getSnapshot());
    if (!prev) {
      setStatus("Nothing to undo");
      return;
    }
    applySnapshot(prev);
    setStatus("Undone");
  }, [applySnapshot, getSnapshot]);

  const performRedo = useCallback(() => {
    const next = undoStacksRef.current.redo(getSnapshot());
    if (!next) {
      setStatus("Nothing to redo");
      return;
    }
    applySnapshot(next);
    setStatus("Redone");
  }, [applySnapshot, getSnapshot]);

  const beginTextEdit = useCallback(
    (id: string) => {
      if (textEditNodeRef.current !== id) {
        pushUndo();
        textEditNodeRef.current = id;
      }
    },
    [pushUndo]
  );

  const endTextEdit = useCallback(() => {
    textEditNodeRef.current = null;
  }, []);

  const replaceNodeImage = useCallback(
    async (nodeId: string, file: File, provenance: string) => {
      pushUndo();
      let src = await fileToDataUrl(file);
      if (projectId && src.length > 120_000) {
        try {
          const up = await uploadAsset(projectId, src, file.name);
          src = up.url;
        } catch {
          /* keep data url */
        }
      }
      setGraphNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                src,
                annotations: undefined,
                annotationSchemaVersion: undefined,
                provenance: `${provenance} · ${file.type} · ${Math.round(file.size / 1024)}kb`,
              }
            : n
        )
      );
      setStatus("Image replaced");
    },
    [projectId, pushUndo]
  );

  const replaceNodeImageSrc = useCallback(
    async (nodeId: string, src: string, provenance: string) => {
      pushUndo();
      const persisted = await persistImageSrc(src, projectId);
      setGraphNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                src: persisted,
                annotations: undefined,
                annotationSchemaVersion: undefined,
                provenance: `${provenance} · html`,
              }
            : n
        )
      );
      setStatus("Image replaced");
    },
    [projectId, pushUndo]
  );

  const openImageAnnotator = useCallback((nodeId: string) => {
    const node = graphRef.current.find((n) => n.id === nodeId);
    if (!node || node.type !== "image" || !hasRealMedia(node) || !node.src) return;
    setResearchUi(null);
    setAnnotateTarget({
      nodeId,
      src: node.src,
      initialAnnotations: node.annotations,
      initialAnnotationNotes: node.annotationNotes,
    });
  }, []);

  const loadImageDimensions = useCallback((src: string) => {
    return new Promise<{ imageWidth?: number; imageHeight?: number }>((resolve) => {
      const img = new Image();
      img.onload = () => resolve({ imageWidth: img.naturalWidth, imageHeight: img.naturalHeight });
      img.onerror = () => resolve({});
      img.crossOrigin = "anonymous";
      img.src = src;
    });
  }, []);

  const copyAnnotationInstructions = useCallback(
    async (nodeId: string) => {
      const node = graphRef.current.find((n) => n.id === nodeId);
      if (!node || !nodeHasAnnotationInstructions(node)) {
        setStatus("No annotation instructions on this image");
        return;
      }
      const dims = node.src ? await loadImageDimensions(node.src) : {};
      const result = await copyNodeAnnotationInstructions(node, dims);
      setStatus(result.message);
    },
    [loadImageDimensions]
  );

  const saveAnnotatedImage = useCallback(
    async (nodeId: string, result: AnnotationSaveResult) => {
      pushUndo();
      const persisted = await persistImageSrc(result.rasterDataUrl, projectId);
      setGraphNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                src: persisted,
                annotations: result.annotations,
                annotationNotes: result.annotationNotes,
                annotationSchemaVersion: result.schemaVersion,
                provenance: "annotate · html",
              }
            : n
        )
      );
      setAnnotateTarget(null);
      setStatus("Annotations saved");
    },
    [persistImageSrc, projectId, pushUndo]
  );

  const replaceNodeVideo = useCallback(
    (nodeId: string, file: File, provenance: string) => {
      if (file.size > MAX_VIDEO_BYTES) {
        setStatus(`Video too large (max ${Math.round(MAX_VIDEO_BYTES / 1024 / 1024)}MB)`);
        return;
      }
      pushUndo();
      const src = URL.createObjectURL(file);
      setGraphNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId
            ? {
                ...n,
                type: "video",
                title: n.title || typeLabel("video"),
                src,
                provenance: `${provenance} · ${file.type || "video"} · ${Math.round(file.size / 1024)}kb`,
              }
            : n
        )
      );
      setStatus("Video replaced");
    },
    [pushUndo]
  );

  const replaceMediaOnNode = useCallback(
    async (nodeId: string, file: File, provenance: string) => {
      const node = graphRef.current.find((n) => n.id === nodeId);
      if (!node) return;
      const kind = classifyFile(file);
      if (node.type === "image" && kind === "image") {
        await replaceNodeImage(nodeId, file, provenance);
        return;
      }
      if (node.type === "video" && kind === "video") {
        replaceNodeVideo(nodeId, file, provenance);
        return;
      }
      pushUndo();
      if (kind === "image") {
        let src = await fileToDataUrl(file);
        if (projectId && src.length > 120_000) {
          try {
            const up = await uploadAsset(projectId, src, file.name);
            src = up.url;
          } catch {
            /* keep data url */
          }
        }
        setGraphNodes((prev) =>
          prev.map((n) =>
            n.id === nodeId
              ? {
                  ...n,
                  type: "image",
                  title: n.title || typeLabel("image"),
                  src,
                  provenance: `${provenance} · ${file.type} · ${Math.round(file.size / 1024)}kb`,
                }
              : n
          )
        );
        setStatus("Image updated");
        return;
      }
      if (kind === "video") {
        replaceNodeVideo(nodeId, file, provenance);
      }
    },
    [projectId, pushUndo, replaceNodeImage, replaceNodeVideo]
  );

  const updateGraphNode = useCallback((id: string, patch: Partial<GraphNode>) => {
    setGraphNodes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n)));
  }, []);

  const bindNode = useCallback(
    (id: string, kind: GraphNode["type"]) => {
      return {
        onChange: (patch: Partial<StoryNodeData>) => {
          setGraphNodes((prev) =>
            prev.map((n) =>
              n.id === id
                ? {
                    ...n,
                    body: patch.body ?? n.body,
                    sequenceIndex: patch.sequenceIndex ?? n.sequenceIndex,
                    title: patch.title ?? n.title,
                    src: patch.src ?? n.src,
                    provenance: patch.provenance ?? n.provenance,
                  }
                : n
            )
          );
        },
        onDelete: () => {
          pushUndo();
          setGraphNodes((prev) => prev.filter((n) => n.id !== id));
          setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
        },
        onBeginTextEdit: () => beginTextEdit(id),
        onEndTextEdit: endTextEdit,
        onReplaceMedia:
          kind === "image"
            ? (file: File) => void replaceNodeImage(id, file, "replace")
            : kind === "video"
              ? (file: File) => replaceNodeVideo(id, file, "replace")
              : undefined,
        onAnnotateImage: kind === "image" ? () => openImageAnnotator(id) : undefined,
        onCopyAnnotationInstructions:
          kind === "image" && nodeHasAnnotationInstructions(graphRef.current.find((n) => n.id === id))
            ? () => void copyAnnotationInstructions(id)
            : undefined,
        onMediaFocus:
          kind === "image" || kind === "video"
            ? (additive?: boolean) => {
                setNodes((nds) => {
                  if (additive) {
                    const next = nds.map((n) =>
                      n.id === id ? { ...n, selected: !n.selected } : n
                    );
                    selectedIdsRef.current = next.filter((n) => n.selected).map((n) => n.id);
                    return next;
                  }
                  selectedIdsRef.current = [id];
                  return nds.map((n) => ({ ...n, selected: n.id === id }));
                });
              }
            : undefined,
        onResizeEnd: () => {
          pushUndo();
          requestAnimationFrame(() => {
            const rf = flowRef.current;
            if (!rf) return;
            const { nodes: n, edges: e } = fromFlow(rf.getNodes(), rf.getEdges(), graphRef.current);
            graphRef.current = n;
            setGraphNodes(n);
            syncEdgesFromGraph(e);
          });
        },
      };
    },
    [replaceNodeImage, replaceNodeVideo, setEdges, setNodes, pushUndo, beginTextEdit, endTextEdit, openImageAnnotator, copyAnnotationInstructions, syncEdgesFromGraph]
  );

  useEffect(() => {
    graphRef.current = graphNodes;
    // Keep React Flow nodes in sync even on board/outline — otherwise fromFlow/serialize
    // reads stale flow data and drops board-only image replacements on save.
    // Merge measured/width/height from prev so RF does not remount-hide nodes (focus loss).
    setNodes((prev) => {
      const prevById = new Map(prev.map((n) => [n.id, n]));
      return toFlowNodes(graphNodes, bindNode).map((n) => {
        const old = prevById.get(n.id);
        return mergeFlowNodeFromPrev(n, old, !!old?.selected);
      });
    });
  }, [graphNodes, bindNode, setNodes]);

  const applyProject = useCallback(
    (p: StoryProject, id?: string | null) => {
      undoStacksRef.current.clear();
      textEditNodeRef.current = null;
      setTitle(p.title || "Untitled story");
      setGraphNodes(p.nodes || []);
      syncEdgesFromGraph(p.edges || []);
      if (id !== undefined) setProjectId(id || null);
      canvasReadyRef.current = false;
      setSessionReady(true);
      setWelcomeMode(false);
      setStatus("Loaded");
    },
    [syncEdgesFromGraph]
  );

  const syncGraphFromFlow = useCallback(() => {
    const flowNodes = flowRef.current?.getNodes() ?? nodes;
    const flowEdges = flowRef.current?.getEdges() ?? edges;
    const { nodes: n, edges: e } = fromFlow(flowNodes, flowEdges, graphRef.current);
    graphRef.current = n;
    setGraphNodes(n);
    syncEdgesFromGraph(e);
    return { nodes: n, edges: e };
  }, [nodes, edges, syncEdgesFromGraph]);

  const refreshList = useCallback(async () => {
    setProjectsLoading(true);
    try {
      setProjects(await listProjects());
    } catch {
      /* offline */
    } finally {
      setLocalHistory(loadLocalHistory());
      setProjectsLoading(false);
    }
  }, []);

  const projectRows = useMemo(
    () => mergeProjectRows(projects, localHistory, projectId),
    [projects, localHistory, projectId]
  );

  const setProjectUrl = useCallback((id: string | null) => {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("project", id);
    else url.searchParams.delete("project");
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  }, []);

  const loadProjectById = useCallback(
    async (id: string, source: ProjectSource) => {
      if (view === "canvas") syncGraphFromFlow();
      try {
        if (source === "server") {
          const full = await loadProject(id);
          applyProject((full.payload || full) as StoryProject, full.id);
        } else {
          const entry = getLocalHistoryEntry(id);
          if (entry?.payload) {
            applyProject(entry.payload, entry.id);
          } else {
            const lastSnapshot = loadLocal();
            if (lastSnapshot?.nodes?.length && lastSnapshot.id === id) {
              applyProject(lastSnapshot, lastSnapshot.id);
            } else {
              const full = await loadProject(id);
              applyProject((full.payload || full) as StoryProject, full.id);
            }
          }
        }
        setProjectUrl(id);
        setProjectsOpen(false);
        setStatus("Loaded");
      } catch (err) {
        const fallback = getLocalHistoryEntry(id);
        if (fallback?.payload) {
          applyProject(fallback.payload, fallback.id);
          setProjectUrl(fallback.id);
          setProjectsOpen(false);
          setStatus("Loaded from browser backup");
        } else {
          setStatus("Could not load story");
          console.warn(err);
        }
      }
    },
    [applyProject, setProjectUrl, syncGraphFromFlow, view]
  );

  const resumeLastProject = useCallback(async () => {
    const lastId = loadLastProjectId() || projectRows[0]?.id;
    if (!lastId) return;
    const row = projectRows.find((r) => r.id === lastId);
    await loadProjectById(lastId, row?.source || "local");
  }, [loadProjectById, projectRows]);

  const startNewStory = useCallback(() => {
    if (view === "canvas") syncGraphFromFlow();
    setProjectId(null);
    applyProject(blankTemplate(), null);
    setProjectUrl(null);
    setProjectsOpen(false);
    setStatus("New story");
  }, [applyProject, setProjectUrl, syncGraphFromFlow, view]);

  const deleteStory = useCallback(
    async (id: string, source: ProjectSource) => {
      const row = projectRows.find((r) => r.id === id);
      const label = row?.title || id;
      if (!window.confirm(`Delete "${label}"? This cannot be undone.`)) return;
      removeLocalHistory(id);
      setLocalHistory(loadLocalHistory());
      if (source === "server") {
        try {
          await deleteProject(id);
          await refreshList();
        } catch (err) {
          console.warn(err);
        }
      }
      if (projectId === id) {
        setProjectId(null);
        setGraphNodes([]);
        syncEdgesFromGraph([]);
        setProjectUrl(null);
        setSessionReady(false);
        if (projectRows.length <= 1) {
          setWelcomeMode(true);
          setProjectsOpen(true);
        }
        setStatus("Deleted");
      } else setStatus("Deleted");
    },
    [projectId, projectRows, refreshList, setProjectUrl, syncEdgesFromGraph]
  );

  const bulkDeleteStories = useCallback(
    async (items: Array<{ id: string; source: ProjectSource }>) => {
      if (!items.length) return;
      const label = items.length === 1 ? projectRows.find((r) => r.id === items[0].id)?.title || items[0].id : `${items.length} stories`;
      if (!window.confirm(`Delete ${label}? This cannot be undone.`)) return;

      const ids = items.map((i) => i.id);
      removeLocalHistoryBulk(ids);
      setLocalHistory(loadLocalHistory());

      const serverIds = items.filter((i) => i.source === "server").map((i) => i.id);
      for (const id of serverIds) {
        try {
          await deleteProject(id);
        } catch (err) {
          console.warn(err);
        }
      }
      if (serverIds.length) await refreshList();

      if (projectId && ids.includes(projectId)) {
        setProjectId(null);
        setGraphNodes([]);
        syncEdgesFromGraph([]);
        setProjectUrl(null);
        setSessionReady(false);
        const remaining = projectRows.filter((r) => !ids.includes(r.id));
        if (remaining.length === 0) {
          setWelcomeMode(true);
          setProjectsOpen(true);
        }
      }
      setStatus(`Deleted ${items.length} stor${items.length === 1 ? "y" : "ies"}`);
    },
    [projectId, projectRows, refreshList, setProjectUrl, syncEdgesFromGraph]
  );

  const importProjectFiles = useCallback(
    async (files: FileList | File[]) => {
      const list = [...files];
      if (!list.length) return;
      let imported = 0;
      let last: StoryProject | null = null;
      const errors: string[] = [];
      setImportStatus("Importing…");
      for (const file of list) {
        try {
          const parsed = await readProjectFile(file);
          last = importLocalProject(parsed, { freshId: true });
          imported++;
        } catch (err) {
          errors.push(`${file.name}: ${err instanceof Error ? err.message : "invalid file"}`);
        }
      }
      setLocalHistory(loadLocalHistory());
      if (last) {
        applyProject(last, last.id || null);
        setProjectUrl(last.id || null);
        setProjectsOpen(false);
      }
      const msg =
        imported > 0
          ? `Imported ${imported} stor${imported === 1 ? "y" : "ies"}${errors.length ? ` (${errors.length} failed)` : ""}`
          : errors[0] || "Import failed";
      setImportStatus(msg);
      setStatus(msg);
      if (errors.length) console.warn("Story import errors", errors);
    },
    [applyProject, setProjectUrl]
  );

  const snapshotGraph = useCallback((): { nodes: GraphNode[]; edges: GraphEdge[] } => {
    const flowEdges: GraphEdge[] = edges.map((e) => ({
      id: e.id,
      from: e.source,
      to: e.target,
      type: ((e.data as { edgeType?: EdgeType })?.edgeType || "follows") as EdgeType,
    }));
    if (view === "canvas" && nodes.length) {
      return fromFlow(nodes, edges, graphRef.current);
    }
    return { nodes: graphRef.current, edges: flowEdges };
  }, [nodes, edges, view]);

  const serialize = useCallback((): StoryProject => {
    const snapshot = snapshotGraph();
    graphRef.current = snapshot.nodes;
    return { id: projectId, title, nodes: snapshot.nodes, edges: snapshot.edges, updatedAt: Date.now() };
  }, [snapshotGraph, projectId, title]);

  const doSave = useCallback(async (): Promise<{ server: boolean; error?: string }> => {
    const payload = serialize();
    const canUpdateStatus = () => Date.now() >= statusHoldUntilRef.current;
    try {
      const res = await saveProject(projectId, title, payload);
      setProjectId(res.id);
      payload.id = res.id;
      persistLocal(payload);
      setLocalHistory(loadLocalHistory());
      if (canUpdateStatus()) setStatus("Saved to server");
      refreshList();
      return { server: true };
    } catch (err) {
      persistLocal(payload);
      setLocalHistory(loadLocalHistory());
      const errorMsg = friendlySaveErrorMessage(err);
      if (canUpdateStatus()) setStatus(errorMsg);
      return { server: false, error: errorMsg };
    }
  }, [serialize, projectId, title, refreshList]);

  const handleManualSave = useCallback(async () => {
    if (saving) return;
    if (saveTimer.current) {
      window.clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    if (saveBtnTimer.current) {
      window.clearTimeout(saveBtnTimer.current);
      saveBtnTimer.current = null;
    }
    if (view === "canvas") syncGraphFromFlow();

    setSaving(true);
    setSaveBtnFlash("idle");
    setStatus("Saving…");
    statusHoldUntilRef.current = Date.now() + 3000;

    const result = await doSave();

    setSaving(false);
    statusHoldUntilRef.current = Date.now() + 2500;

    if (result.server) {
      setStatus("Saved to server ✓");
      setSaveBtnFlash("saved");
    } else {
      setStatus(result.error || "Couldn't reach the server — saved to this browser only.");
      setSaveBtnFlash("local");
    }

    saveBtnTimer.current = window.setTimeout(() => {
      setSaveBtnFlash("idle");
      saveBtnTimer.current = null;
    }, 2000);
  }, [doSave, saving, syncGraphFromFlow, view]);

  const flushSave = useCallback(async () => {
    if (saveTimer.current) {
      window.clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    if (view === "canvas") syncGraphFromFlow();
    await doSave();
  }, [doSave, syncGraphFromFlow, view]);

  const exportProjectJson = useCallback(async () => {
    if (view === "canvas") syncGraphFromFlow();
    setStatus("Exporting JSON…");
    try {
      await downloadPortableProjectJson(serialize());
      setStatus("Exported JSON");
    } catch (err) {
      console.warn(err);
      setStatus("Export failed");
    }
  }, [serialize, syncGraphFromFlow, view]);

  const copyProjectJson = useCallback(async () => {
    if (copying) return;
    if (view === "canvas") syncGraphFromFlow();
    setCopying(true);
    setStatus("Copying JSON…");
    try {
      const json = await portableProjectJsonString(serialize());
      await navigator.clipboard.writeText(json);
      setStatus("Copied to clipboard ✓");
    } catch (err) {
      console.warn(err);
      const denied =
        err instanceof DOMException &&
        (err.name === "NotAllowedError" || err.name === "SecurityError");
      setStatus(
        denied
          ? "Clipboard blocked — allow clipboard access or use Export JSON"
          : "Copy failed — try Export JSON"
      );
    } finally {
      setCopying(false);
    }
  }, [copying, serialize, syncGraphFromFlow, view]);

  const copyAgentBrief = useCallback(async () => {
    if (copyingBrief) return;
    if (view === "canvas") syncGraphFromFlow();
    setCopyingBrief(true);
    setStatus("Building agent brief…");
    try {
      const selectedNodeIds = selectedIdsRef.current.filter((id) =>
        graphRef.current.some((n) => n.id === id)
      );
      const brief = buildAgentBrief(serialize(), {
        selectedNodeIds: selectedNodeIds.length ? selectedNodeIds : undefined,
      });
      await navigator.clipboard.writeText(brief);
      setStatus("Agent brief copied ✓");
    } catch (err) {
      console.warn(err);
      const denied =
        err instanceof DOMException &&
        (err.name === "NotAllowedError" || err.name === "SecurityError");
      setStatus(
        denied
          ? "Clipboard blocked — allow clipboard access for agent brief"
          : "Agent brief copy failed"
      );
    } finally {
      setCopyingBrief(false);
    }
  }, [copyingBrief, serialize, syncGraphFromFlow, view]);

  useEffect(() => {
    if (!sessionReady) return;
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      void doSave();
    }, 900);
    return () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, [graphNodes, edges, title, doSave, sessionReady]);

  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const urlProject = params.get("project");

    (async () => {
      const preloaded = await preloadLocalCreations();
      const history = loadLocalHistory();
      setLocalHistory(history);
      const local = loadLocal();
      void refreshList();

      let serverList: ProjectSummary[] = [];
      try {
        serverList = await listProjects();
        setProjects(serverList);
      } catch {
        /* offline — browser history only */
      }

      if (preloaded > 0) setStatus(`Pre-loaded ${preloaded} saved stor${preloaded === 1 ? "y" : "ies"}`);

      const isFirstVisit = !hasSavedStories(history, serverList) && !urlProject;

      if (isFirstVisit) {
        setWelcomeMode(true);
        setProjectsOpen(true);
        setStatus("Import a story or create a new one");
        return;
      }

      const pick =
        (urlProject &&
          (serverList.find((p) => p.id === urlProject)?.id ||
            history.find((h) => h.id === urlProject)?.id)) ||
        loadLastProjectId() ||
        history[0]?.id ||
        serverList[0]?.id;

      if (pick) {
        const localEntry = getLocalHistoryEntry(pick);
        try {
          const full = await loadProject(pick);
          const serverPayload = (full.payload || full) as StoryProject;
          const serverUpdated = toEpochMs(full.updated_at) || serverPayload.updatedAt || 0;
          const localNewer =
            localEntry?.payload &&
            (localEntry.nodeCount || 0) > 0 &&
            localEntry.updatedAt > serverUpdated;
          if (localNewer && localEntry.payload) {
            applyProject(localEntry.payload, localEntry.id);
            setProjectUrl(localEntry.id);
            return;
          }
          applyProject(serverPayload, full.id);
          setProjectUrl(full.id);
          return;
        } catch {
          if (localEntry?.payload) {
            applyProject(localEntry.payload, localEntry.id);
            setProjectUrl(localEntry.id);
            return;
          }
          const lastSnapshot = loadLocal();
          if (lastSnapshot?.nodes?.length && (lastSnapshot.id === pick || loadLastProjectId() === pick)) {
            applyProject(lastSnapshot, lastSnapshot.id || pick);
            setProjectUrl(lastSnapshot.id || pick);
            return;
          }
          if (local?.nodes?.length && (local.id === pick || !local.id)) {
            applyProject(local, local.id || pick);
            setProjectUrl(local.id || pick);
            return;
          }
        }
      }

      if (local?.nodes?.length) {
        applyProject(local, local.id || null);
        setProjectUrl(local.id || null);
      } else {
        setWelcomeMode(true);
        setProjectsOpen(true);
        setStatus("Import a story or create a new one");
      }
    })();
  }, [applyProject, refreshList, setProjectUrl]);

  useEffect(() => {
    const onDragOver = (e: DragEvent) => {
      if ([...(e.dataTransfer?.types || [])].includes("Files")) e.preventDefault();
    };
    const onDrop = (e: DragEvent) => {
      const files = [...(e.dataTransfer?.files || [])].filter(
        (f) => f.type === "application/json" || f.name.endsWith(".json")
      );
      if (!files.length) return;
      e.preventDefault();
      void importProjectFiles(files);
    };
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [importProjectFiles]);

  const onConnect = useCallback(
    (c: Connection) => {
      pushUndo();
      setEdges((eds) =>
        addEdge(
          {
            ...c,
            id: uid("e"),
            className: `edge-${edgeType}`,
            label: edgeType,
            data: { edgeType },
            markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
          },
          eds
        )
      );
      setStatus(`Connected (${edgeType})`);
    },
    [edgeType, setEdges, pushUndo]
  );

  const onNodeDragStop = useCallback(() => {
    pushUndo();
    syncGraphFromFlow();
  }, [syncGraphFromFlow, pushUndo]);

  const switchView = useCallback(
    (next: ViewMode) => {
      if (view === "canvas" && next !== "canvas") {
        syncGraphFromFlow();
        void flushSave();
      }
      if (view === "board" && next !== "board") {
        void flushSave();
        setBoardFocusId(null);
      }
      if (next === "present") setPresentIndex(0);
      setView(next);
    },
    [view, syncGraphFromFlow, flushSave]
  );

  const presentableNodes = useMemo(
    () => graphNodes.filter((n) => n.type !== "frame"),
    [graphNodes]
  );

  const onSearchSelect = useCallback(
    (result: CardSearchResult) => {
      if (view !== "board") {
        setView("board");
      }
      setBoardFocusId(result.node.id);
      setScrollToCardId(result.node.id);
      setStatus(`Found ${result.label} · ${result.node.title || result.snippet.slice(0, 40)}`);
      window.setTimeout(() => setScrollToCardId(null), 600);
    },
    [view]
  );

  const onSearchQueryChange = useCallback((q: string) => {
    setCardSearchQuery(q);
  }, []);

  const addNode = useCallback(
    (partial: Partial<GraphNode> & { type: NodeKind }) => {
      pushUndo();
      const id = partial.id || uid("n");
      const node: GraphNode = {
        id,
        type: partial.type,
        x: partial.x ?? 180 + Math.random() * 80,
        y: partial.y ?? 140 + Math.random() * 80,
        title: partial.title || typeLabel(partial.type),
        body: partial.body || "",
        src: partial.src,
        sequenceIndex: partial.sequenceIndex ?? nextSequence(graphRef.current),
        provenance: partial.provenance,
        researchSessionId: partial.researchSessionId,
        width: partial.width,
        height: partial.height,
      };
      setGraphNodes((prev) => [...prev, node]);
      return id;
    },
    [pushUndo]
  );

  const addImage = useCallback(
    async (file: File, provenance: string) => {
      let src = await fileToDataUrl(file);
      if (projectId && src.length > 120_000) {
        try {
          const up = await uploadAsset(projectId, src, file.name);
          src = up.url;
        } catch {
          /* keep data url */
        }
      }
      addNode({
        type: "image",
        title: "IMAGE",
        src,
        provenance: `${provenance} · ${file.type} · ${Math.round(file.size / 1024)}kb`,
      });
    },
    [addNode, projectId]
  );

  const addImageSrc = useCallback(
    (src: string, provenance: string) => {
      addNode({
        type: "image",
        title: "IMAGE",
        src,
        provenance,
      });
    },
    [addNode]
  );

  const addVideo = useCallback(
    (file: File, provenance: string) => {
      if (file.size > MAX_VIDEO_BYTES) {
        setStatus(`Video too large (max ${Math.round(MAX_VIDEO_BYTES / 1024 / 1024)}MB)`);
        return;
      }
      const src = URL.createObjectURL(file);
      addNode({
        type: "video",
        title: "VIDEO",
        src,
        provenance: `${provenance} · ${file.type || "video"} · ${Math.round(file.size / 1024)}kb`,
      });
    },
    [addNode]
  );

  const ingestAssets = useCallback(
    async (assets: ClipboardAsset[], provenance: string) => {
      if (!assets.length) return;

      const selected =
        view === "board" && boardFocusId
          ? [boardFocusId]
          : selectedIdsRef.current;

      const images = assets.filter((a) => a.kind === "image" || a.kind === "imageSrc");
      const videos = assets.filter((a) => a.kind === "video");
      const texts = assets.filter((a) => a.kind === "text");

      if (selected.length === 1 && texts.length === 1 && images.length === 0 && videos.length === 0) {
        const target = graphRef.current.find((n) => n.id === selected[0]);
        if (target && view === "board") {
          pushUndo();
          updateGraphNode(selected[0], { body: texts[0].body });
          setStatus("Text updated");
          return;
        }
      }

      if (selected.length === 1 && images.length === 1 && videos.length === 0) {
        const target = graphRef.current.find((n) => n.id === selected[0]);
        if (
          target &&
          (target.type === "image" ||
            target.type === "text" ||
            target.type === "beat" ||
            target.type === "scene" ||
            target.type === "research" ||
            target.type === "prompt")
        ) {
          const img = images[0];
          if (img.kind === "image") await replaceMediaOnNode(selected[0], img.file, provenance);
          else await replaceNodeImageSrc(selected[0], img.src, provenance);
          for (const t of texts) {
            addNode({
              type: t.nodeType,
              title: typeLabel(t.nodeType),
              body: t.body,
              provenance,
            });
          }
          return;
        }
      }

      if (selected.length === 1 && videos.length === 1 && images.length === 0 && texts.length === 0) {
        const target = graphRef.current.find((n) => n.id === selected[0]);
        if (target?.type === "video") {
          replaceNodeVideo(selected[0], videos[0].file, provenance);
          return;
        }
      }

      for (const asset of assets) {
        if (asset.kind === "image") void addImage(asset.file, provenance);
        else if (asset.kind === "imageSrc") addImageSrc(asset.src, `${provenance} · html`);
        else if (asset.kind === "video") addVideo(asset.file, provenance);
        else if (asset.kind === "text") {
          addNode({
            type: asset.nodeType,
            title: typeLabel(asset.nodeType),
            body: asset.body,
            provenance,
          });
        }
      }
      setStatus(`Added ${assets.length} item${assets.length === 1 ? "" : "s"}`);
    },
    [addImage, addImageSrc, addVideo, addNode, replaceMediaOnNode, replaceNodeImageSrc, replaceNodeVideo, updateGraphNode, view, boardFocusId, pushUndo]
  );

  const onSelectionChange = useCallback((params: OnSelectionChangeParams) => {
    selectedIdsRef.current = params.nodes.map((n) => n.id);
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      // Never intercept typing / native undo inside inputs or contenteditable.
      if (isEditableTarget(e.target)) return;
      const key = e.key.toLowerCase();
      if (key === "z" && !e.shiftKey) {
        if (!undoStacksRef.current.canUndo()) return;
        e.preventDefault();
        performUndo();
      } else if (key === "y" || (key === "z" && e.shiftKey)) {
        if (!undoStacksRef.current.canRedo()) return;
        e.preventDefault();
        performRedo();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [performUndo, performRedo]);

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (view !== "canvas" && view !== "board") return;
      if (isEditableTarget(e.target)) return;
      const assets = parseClipboardData(e.clipboardData);
      if (!assets.length) return;
      e.preventDefault();
      ingestAssets(assets, "clipboard");
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [ingestAssets, view]);

  const onCanvasDragOver = useCallback((e: React.DragEvent) => {
    if (view !== "canvas") return;
    if ([...e.dataTransfer.types].some((t) => t === "Files")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  }, [view]);

  const onCanvasDrop = useCallback(
    (e: React.DragEvent) => {
      if (view !== "canvas") return;
      const assets = parseFileList(e.dataTransfer.files);
      if (!assets.length) return;
      e.preventDefault();
      ingestAssets(assets, "drop");
    },
    [ingestAssets, view]
  );

  const dropResearch = useCallback(
    async (q: string) => {
      const sessionMatch = q.trim().match(/^rp-[a-zA-Z0-9-]{4,128}$/);
      if (composerMode === "session" || sessionMatch) {
        const sid = sessionMatch ? q.trim() : q.trim();
        setStatus("Hydrating research…");
        try {
          const detail = await researchDetail(sid);
          const result = detail?.result || detail?.raw_report || "";
          const sources = (detail?.sources || [])
            .slice(0, 8)
            .map((s: any) => `- ${s.title || s.url || s}`)
            .join("\n");
          const excerpt = String(result).slice(0, 1200);
          addNode({
            type: "research",
            title: "RESEARCH CONTEXT",
            researchSessionId: sid,
            body: `Session: ${sid}\nTitle: ${detail?.title || ""}\nQuery: ${detail?.query || ""}\n\nClaims (edit):\n- Summarize findings below\n\nExcerpt:\n${excerpt}\n\nSources:\n${sources || "- (none)"}`,
          });
          setStatus("Research hydrated");
        } catch {
          addNode({
            type: "research",
            title: "RESEARCH CONTEXT",
            researchSessionId: sid,
            body: `Session: ${sid}\n\nClaims (edit):\n- Could not load report — edit manually.\n\nSources:\n- /api/research/report/${sid}`,
          });
          setStatus("Hydrate failed — stub node");
        }
        return;
      }

      let body = `Query: ${q}\n\nClaims (edit me):\n- …\n\nSources:\n- …`;
      try {
        setStatus("Researching library…");
        const lib = await researchLibrary();
        const hits = lib
          .filter((it) => {
            const hay = `${it.title || ""} ${it.query || ""}`.toLowerCase();
            return q
              .toLowerCase()
              .split(/\s+/)
              .some((w) => w.length > 2 && hay.includes(w));
          })
          .slice(0, 4);
        if (hits.length) {
          body = `Query: ${q}\n\nClaims (edit me):\n- Related Odysseus reports found — refine claims.\n\nSources:\n${hits
            .map((h) => `- ${h.title || h.id} (${h.id})`)
            .join("\n")}`;
        }
      } catch {
        /* stub */
      }
      addNode({ type: "research", title: "RESEARCH CONTEXT", body });
      setStatus("Research context ready");
    },
    [addNode, composerMode]
  );

  const openResearchMenu = useCallback(
    (nodeId: string, clientX: number, clientY: number) => {
      // Capture before menu mount / any blur from menu interaction.
      priorEditFocusRef.current = captureEditableFocus();
      let selected = [...selectedIdsRef.current];
      if (!selected.includes(nodeId)) {
        selected = [nodeId];
        selectedIdsRef.current = selected;
        setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeId })));
      }
      setResearchUi({ phase: "menu", x: clientX, y: clientY, nodeId, selectedIds: selected });
    },
    [setNodes]
  );

  const onCanvasNodeContextMenu: NodeMouseHandler = useCallback((e, node) => {
    e.preventDefault();
    openResearchMenu(node.id, e.clientX, e.clientY);
  }, [openResearchMenu]);

  const onBoardNodeContextMenu = useCallback(
    (nodeId: string, e: React.MouseEvent) => {
      openResearchMenu(nodeId, e.clientX, e.clientY);
    },
    [openResearchMenu]
  );

  const openResearchPrompt = useCallback((nodeId: string) => {
    const node = graphRef.current.find((n) => n.id === nodeId);
    if (!node) return;
    setResearchUi({ phase: "prompt", nodeId, query: queryFromNode(node) });
  }, []);

  const performAlign = useCallback(
    (selectedIds: string[], action: AlignAction) => {
      if (selectedIds.length < 2) return;
      pushUndo();
      const measuredById = new Map<string, { width: number; height: number }>();
      for (const fn of nodes) {
        if (!selectedIds.includes(fn.id)) continue;
        const measured = (fn as StoryFlowNode & { measured?: { width?: number; height?: number } })
          .measured;
        const styleW = fn.style?.width;
        const styleH = fn.style?.height;
        if (measured?.width && measured?.height) {
          measuredById.set(fn.id, { width: measured.width, height: measured.height });
        } else if (styleW != null && styleH != null) {
          measuredById.set(fn.id, { width: Number(styleW), height: Number(styleH) });
        }
      }
      const rects = rectsForIds(graphRef.current, selectedIds, measuredById);
      const positions = applyAlignAction(rects, action);
      setGraphNodes((prev) =>
        prev.map((n) => {
          const pos = positions[n.id];
          return pos ? { ...n, x: pos.x, y: pos.y } : n;
        })
      );
      setStatus("Aligned");
    },
    [nodes, pushUndo]
  );

  const runFirecrawlResearch = useCallback(
    async (sourceId: string, rawQuery: string) => {
      const q = rawQuery.trim();
      if (!q) return;
      const source = graphRef.current.find((n) => n.id === sourceId);
      if (!source) return;

      setResearchLoading(true);
      setStatus("Searching with Firecrawl…");
      try {
        const res = await storyCanvasResearch(q);
        pushUndo();
        const researchId = uid("n");
        const body = researchBodyFromHits(res.query, res.results, source.title || source.type);
        const node: GraphNode = {
          id: researchId,
          type: "research",
          x: source.x + 300,
          y: source.y + 48,
          title: "RESEARCH CONTEXT",
          body,
          sequenceIndex: nextSequence(graphRef.current),
          provenance: `firecrawl · ${res.result_count} hit${res.result_count === 1 ? "" : "s"}`,
        };
        const edgeId = uid("e");
        setGraphNodes((prev) => [...prev, node]);
        setEdges((eds) =>
          addEdge(
            {
              id: edgeId,
              source: sourceId,
              target: researchId,
              className: "edge-researchContext",
              label: "researchContext",
              data: { edgeType: "researchContext" as EdgeType },
              markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
            },
            eds
          )
        );
        setResearchUi(null);
        setStatus(`Research ready · ${res.result_count} source${res.result_count === 1 ? "" : "s"}`);
      } catch (err) {
        setStatus(friendlyResearchErrorMessage(err));
      } finally {
        setResearchLoading(false);
      }
    },
    [pushUndo, setEdges]
  );

  const onComposer = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    if (composerMode === "research" || composerMode === "session") await dropResearch(q);
    else if (composerMode === "prompt") addNode({ type: "prompt", title: "PROMPT", body: q });
    else if (composerMode === "beat") addNode({ type: "beat", title: "BEAT", body: q });
    else addNode({ type: "text", title: "TEXT", body: q });
    setQuery("");
  };

  const onExportOd = async () => {
    let id = projectId;
    if (!id) {
      await doSave();
      id = projectId;
    }
    // ensure saved id
    const payload = serialize();
    try {
      const res = await saveProject(id, title, payload);
      id = res.id;
      setProjectId(id);
      const out = await exportOd(id, { designMd: "default", handoff: true });
      const blob = new Blob([out.brief_md], { type: "text/markdown" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${title.replace(/\s+/g, "-").toLowerCase() || "story"}-od-brief.md`;
      a.click();
      setStatus(out.handoff_dir ? `Exported + handoff` : `Exported brief`);
    } catch (err) {
      setStatus("Export failed");
      console.warn(err);
    }
  };

  const edgeTypesMemo = useMemo(() => EDGE_TYPES, []);

  const embedded = typeof window !== "undefined" && window !== window.top;

  const toggleStoriesPanel = useCallback(() => {
    setStoriesPanelOpen((open) => {
      const next = !open;
      try {
        localStorage.setItem(STORIES_PANEL_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const setCanvasToolPersist = useCallback((tool: CanvasTool) => {
    setCanvasTool(tool);
    try {
      sessionStorage.setItem(CANVAS_TOOL_KEY, tool);
    } catch {
      /* ignore */
    }
  }, []);

  const isPanTool = canvasTool === "pan";

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (view !== "canvas") return;
      if (isEditableTarget(e.target)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const key = e.key.toLowerCase();
      if (key === "h") {
        e.preventDefault();
        setCanvasToolPersist("pan");
      } else if (key === "v") {
        e.preventDefault();
        setCanvasToolPersist("select");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [view, setCanvasToolPersist]);

  return (
    <div
      className={`sc-app${embedded ? " sc-embedded" : ""}${storiesPanelOpen ? " sc-stories-open" : ""}`}
    >
      {!embedded && (
      <header className="sc-topbar">
        <span className="brand">Story Canvas</span>
        <button type="button" className="primary" onClick={() => setProjectsOpen(true)}>
          Open…
        </button>
        <button type="button" onClick={() => startNewStory()}>
          New
        </button>
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
        <CardSearchBar
          nodes={graphNodes}
          onSelect={onSearchSelect}
          onQueryChange={onSearchQueryChange}
        />
        <div className="sc-tabs">
          {(["canvas", "outline", "board", "present"] as ViewMode[]).map((v) => (
            <button key={v} type="button" className={view === v ? "active" : ""} onClick={() => switchView(v)}>
              {v[0].toUpperCase() + v.slice(1)}
            </button>
          ))}
        </div>
        <button type="button" onClick={() => addNode({ type: "text", body: "" })}>
          + Text
        </button>
        <button type="button" onClick={() => addNode({ type: "beat", body: "" })}>
          + Beat
        </button>
        <button type="button" onClick={() => addNode({ type: "scene", body: "" })}>
          + Scene
        </button>
        <button
          type="button"
          onClick={() =>
            addNode({
              type: "frame",
              title: "FRAME",
              body: "Section",
              width: 480,
              height: 360,
              sequenceIndex: 0,
            })
          }
        >
          + Frame
        </button>
        <label className="btn" htmlFor="file-img">
          + Image
        </label>
        <input
          id="file-img"
          type="file"
          accept="image/*"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void addImage(f, `upload · ${f.name}`);
            e.target.value = "";
          }}
        />
        <button type="button" className="primary" onClick={() => applyProject(blankTemplate(), null)}>
          Blank
        </button>
        <button type="button" onClick={() => applyProject(guidedStoryTemplate(), null)}>
          Guided
        </button>
        <div className="spacer" />
        <button type="button" onClick={exportProjectJson}>
          Export JSON
        </button>
        <button type="button" onClick={() => void onExportOd()}>
          Export OD
        </button>
        <button
          type="button"
          disabled={copyingBrief}
          onClick={() => void copyAgentBrief()}
          title="Copy compact agent brief to clipboard (not full JSON)"
          aria-label="Copy agent brief to clipboard"
        >
          {copyingBrief ? (
            "Copying…"
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }}>
                <path
                  d="M3 2.5h7.5a1 1 0 0 1 1 1V5H12a1.5 1.5 0 0 0-1.5 1.5v6A1.5 1.5 0 0 0 12 14h-6A1.5 1.5 0 0 0 4.5 12.5v-6A1.5 1.5 0 0 0 6 5h.5V3.5a1 1 0 0 1 1-1ZM6 6v6h6V6H6Zm1.25-2.5V5h3.5V3.5H7.25Z"
                  fill="currentColor"
                />
              </svg>
              Agent brief
            </>
          )}
        </button>
        <button
          type="button"
          disabled={copying}
          onClick={() => void copyProjectJson()}
          title="Copy story JSON to clipboard"
          aria-label="Copy JSON to clipboard"
        >
          {copying ? (
            "Copying…"
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }}>
                <path
                  d="M5.5 2.5h6a1 1 0 0 1 1 1v8.5h-1.5V4H5.5V2.5ZM3 5.5h6.5a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1Z"
                  fill="currentColor"
                />
              </svg>
              Copy JSON
            </>
          )}
        </button>
        <button
          type="button"
          className="accent"
          disabled={saving}
          onClick={() => void handleManualSave()}
        >
          {saving
            ? "Saving…"
            : saveBtnFlash === "saved"
              ? "Saved ✓"
              : saveBtnFlash === "local"
                ? "Saved locally"
                : "Save"}
        </button>
        <span className="sc-status">{status}</span>
        <StoriesPanelToggle open={storiesPanelOpen} onClick={toggleStoriesPanel} />
      </header>
      )}

      <div className="sc-main">
        <div className="sc-canvas-wrap">
          {embedded && (
            <StoriesPanelToggle
              open={storiesPanelOpen}
              onClick={toggleStoriesPanel}
              className="sc-stories-toggle-embedded"
            />
          )}
          <div
            className="sc-canvas-layer"
            style={{ display: view === "canvas" ? "block" : "none" }}
            onDragOver={onCanvasDragOver}
            onDrop={onCanvasDrop}
          >
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeDragStop={onNodeDragStop}
              onSelectionChange={onSelectionChange}
              onNodeContextMenu={onCanvasNodeContextMenu}
              onInit={(rf) => {
                flowRef.current = rf;
                if (!canvasReadyRef.current && graphNodes.length) {
                  canvasReadyRef.current = true;
                  requestAnimationFrame(() => rf.fitView({ padding: 0.15 }));
                }
              }}
              nodeTypes={nodeTypes}
              connectionMode={ConnectionMode.Loose}
              proOptions={{ hideAttribution: true }}
              className={isPanTool ? "sc-flow-pan-tool" : "sc-flow-select-tool"}
              panOnDrag={isPanTool}
              panOnScroll
              panActivationKeyCode="Space"
              nodesDraggable={!isPanTool}
              nodesConnectable={!isPanTool}
              elementsSelectable={!isPanTool}
              selectionOnDrag={!isPanTool}
              selectionKeyCode={null}
              multiSelectionKeyCode="Shift"
              selectionMode={SelectionMode.Partial}
            >
              <Background gap={22} size={1} color="#cfc9bc" />
              <CanvasDock tool={canvasTool} onChange={setCanvasToolPersist} />
              <MiniMap pannable zoomable />
            </ReactFlow>
          </div>
          {view === "outline" && (
            <div className="sc-panel-view">
              <OutlineView nodes={graphNodes} />
            </div>
          )}
          {view === "board" && (
            <div className="sc-panel-view">
              <BoardView
                nodes={graphNodes}
                focusId={boardFocusId}
                onFocusNode={setBoardFocusId}
                onChangeNode={updateGraphNode}
                onBeginTextEdit={beginTextEdit}
                onEndTextEdit={endTextEdit}
                onReplaceMedia={(id, file) => void replaceMediaOnNode(id, file, "board")}
                onAnnotateImage={openImageAnnotator}
                onCopyAnnotationInstructions={(id) => void copyAnnotationInstructions(id)}
                onNodeContextMenu={onBoardNodeContextMenu}
                searchQuery={cardSearchQuery}
                scrollToId={scrollToCardId}
              />
            </div>
          )}
          {view === "present" && (
            <PresentView
              nodes={graphNodes}
              index={presentIndex}
              onPrev={() => setPresentIndex((i) => Math.max(0, i - 1))}
              onNext={() =>
                setPresentIndex((i) => Math.min(presentableNodes.length - 1, i + 1))
              }
              onExit={() => switchView("canvas")}
            />
          )}
        </div>

        <aside className="sc-side">
          <div className="sc-side-head">
            <h2>Your stories</h2>
            <button
              type="button"
              className="sc-side-close"
              onClick={toggleStoriesPanel}
              aria-label="Close stories panel"
            >
              ×
            </button>
          </div>
          <ProjectsSidebar
            rows={projectRows}
            onOpenPicker={() => setProjectsOpen(true)}
            onLoad={(id, source) => void loadProjectById(id, source)}
            onImportFiles={(files) => void importProjectFiles(files)}
          />
          <h2>Edge type</h2>
          <select value={edgeType} onChange={(e) => setEdgeType(e.target.value as EdgeType)}>
            {edgeTypesMemo.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
          <p>Board view: click image to select/preview · double-click to replace · Ctrl+V paste. Ctrl+Z undo · Ctrl+Shift+Z redo.</p>
          <h2>Open Design</h2>
          <p>
            Export OD packages a Markdown brief + graph JSON for DESIGN.md / deck / image workflows. Sibling clone:{" "}
            <code>../open-design</code> · <code>od mcp install cursor</code>
          </p>
        </aside>
      </div>

      <form className="sc-composer" onSubmit={onComposer}>
        <select value={composerMode} onChange={(e) => setComposerMode(e.target.value as any)}>
          <option value="text">Text</option>
          <option value="beat">Beat</option>
          <option value="research">Research → editable context</option>
          <option value="session">Research session id</option>
          <option value="prompt">Prompt</option>
        </select>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={
            composerMode === "session"
              ? "rp-… session id"
              : "Quick text, beat, or research query…"
          }
        />
        <button type="submit">Drop</button>
      </form>

      <ProjectsPanel
        open={projectsOpen}
        onClose={() => setProjectsOpen(false)}
        rows={projectRows}
        lastProjectId={loadLastProjectId()}
        loading={projectsLoading}
        welcomeMode={welcomeMode}
        onLoad={(id, source) => void loadProjectById(id, source)}
        onResumeLast={() => void resumeLastProject()}
        onNew={startNewStory}
        onRefresh={() => void refreshList()}
        onDelete={(id, source) => void deleteStory(id, source)}
        onBulkDelete={(items) => void bulkDeleteStories(items)}
        onImportFiles={(files) => void importProjectFiles(files)}
        importStatus={importStatus}
      />

      <NodeResearchMenu
        state={researchUi}
        loading={researchLoading}
        priorFocusRef={priorEditFocusRef}
        canAnnotateImage={
          researchUi?.phase === "menu"
            ? (() => {
                const node = graphNodes.find((n) => n.id === researchUi.nodeId);
                return !!node && node.type === "image" && hasRealMedia(node);
              })()
            : false
        }
        canCopyInstructions={
          researchUi?.phase === "menu"
            ? (() => {
                const node = graphNodes.find((n) => n.id === researchUi.nodeId);
                return !!node && nodeHasAnnotationInstructions(node);
              })()
            : false
        }
        onClose={() => setResearchUi(null)}
        onOpenPrompt={openResearchPrompt}
        onAnnotateImage={openImageAnnotator}
        onCopyInstructions={(nodeId) => void copyAnnotationInstructions(nodeId)}
        onQueryChange={(q) =>
          setResearchUi((prev) => (prev?.phase === "prompt" ? { ...prev, query: q } : prev))
        }
        onSubmit={(nodeId, q) => void runFirecrawlResearch(nodeId, q)}
        onAlign={performAlign}
      />

      {annotateTarget ? (
        <ImageAnnotator
          key={annotateTarget.nodeId}
          src={annotateTarget.src}
          initialAnnotations={annotateTarget.initialAnnotations}
          initialAnnotationNotes={annotateTarget.initialAnnotationNotes}
          onSave={(result) => void saveAnnotatedImage(annotateTarget.nodeId, result)}
          onCancel={() => setAnnotateTarget(null)}
        />
      ) : null}
    </div>
  );
}
