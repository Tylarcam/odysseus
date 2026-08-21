import { useCallback, useEffect, useRef, useState } from "react";
import { nodeHasAnnotationInstructions } from "../annotationInstructions";
import type { GraphNode } from "../domain";
import { orderedNodes, placeholderSvg } from "../domain";
import { classifyFile } from "../clipboardAssets";
import { matchCardIds, searchCards } from "../cardSearch";
import { MediaPreview } from "../components/MediaPreview";
import { hasRealMedia } from "../mediaHelpers";

export type BoardNodePatch = Partial<Pick<GraphNode, "body" | "title" | "sequenceIndex">>;

export function OutlineView({ nodes }: { nodes: GraphNode[] }) {
  const ordered = orderedNodes(nodes).filter((n) => n.type !== "frame");
  return (
    <ol className="sc-outline">
      {ordered.map((n) => (
        <li key={n.id}>
          <span className="otype">{n.type}</span>
          {(n.body || n.title || "(empty)").slice(0, 200)}
        </li>
      ))}
    </ol>
  );
}

function BoardCard({
  node,
  index,
  focused,
  matched,
  cardRef,
  onFocus,
  onChangeNode,
  onBeginTextEdit,
  onEndTextEdit,
  onReplaceMedia,
  onAnnotateImage,
  onCopyAnnotationInstructions,
  onContextMenu,
}: {
  node: GraphNode;
  index: number;
  focused: boolean;
  matched?: boolean;
  cardRef?: (el: HTMLDivElement | null) => void;
  onFocus: () => void;
  onChangeNode: (id: string, patch: BoardNodePatch) => void;
  onBeginTextEdit: (id: string) => void;
  onEndTextEdit: () => void;
  onReplaceMedia: (id: string, file: File) => void;
  onAnnotateImage?: (id: string) => void;
  onCopyAnnotationInstructions?: (id: string) => void;
  onContextMenu?: (id: string, e: React.MouseEvent) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const hadBodyFocusRef = useRef(false);
  const clickTimerRef = useRef<number | null>(null);
  const [mediaSelected, setMediaSelected] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const isMedia = node.type === "image" || node.type === "video";
  const realMedia = hasRealMedia(node);

  const pickFile = useCallback(() => {
    fileRef.current?.click();
  }, []);

  const onFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) onReplaceMedia(node.id, file);
      e.target.value = "";
      setMediaSelected(false);
    },
    [node.id, onReplaceMedia]
  );

  useEffect(() => {
    if (!focused) {
      hadBodyFocusRef.current = false;
      setMediaSelected(false);
      setPreviewOpen(false);
    }
  }, [focused]);

  useEffect(() => {
    if (!hadBodyFocusRef.current || !bodyRef.current) return;
    if (document.activeElement === bodyRef.current) return;
    const el = bodyRef.current;
    el.focus({ preventScroll: true });
    const end = el.value.length;
    try {
      el.setSelectionRange(end, end);
    } catch {
      /* ignore */
    }
  }, [node.body, focused]);

  useEffect(() => {
    return () => {
      if (clickTimerRef.current) window.clearTimeout(clickTimerRef.current);
    };
  }, []);

  const handleMediaClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onFocus();

      if (!realMedia) {
        if (mediaSelected) pickFile();
        else setMediaSelected(true);
        return;
      }

      if (clickTimerRef.current) window.clearTimeout(clickTimerRef.current);
      clickTimerRef.current = window.setTimeout(() => {
        clickTimerRef.current = null;
        setMediaSelected(true);
        setPreviewOpen(true);
      }, 250);
    },
    [realMedia, mediaSelected, onFocus, pickFile]
  );

  const handleMediaDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (clickTimerRef.current) {
        window.clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      if (realMedia) {
        setPreviewOpen(false);
        pickFile();
      }
    },
    [realMedia, pickFile]
  );

  const mediaClass = [
    "sc-board-media",
    mediaSelected && !realMedia ? "empty-selected" : "",
    mediaSelected && realMedia ? "image-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const mediaSrc =
    isMedia && node.src ? node.src : placeholderSvg(node.type, 40 + index * 18);

  const mediaHint = !realMedia
    ? mediaSelected
      ? "Click again to browse · Ctrl+V to paste"
      : "Click to select · then paste or browse"
    : mediaSelected
      ? "Double-click to replace"
      : "Click to preview · double-click to replace";

  const canCopyInstructions =
    node.type === "image" && nodeHasAnnotationInstructions(node) && !!onCopyAnnotationInstructions;

  return (
    <div
      ref={cardRef}
      className={`sc-frame-card${focused ? " focused" : ""}${matched ? " matched" : ""}`}
      onClick={onFocus}
      onContextMenu={(e) => {
        if (!onContextMenu) return;
        e.preventDefault();
        onContextMenu(node.id, e);
      }}
      onKeyDown={(e) => e.key === "Enter" && onFocus()}
      role="button"
      tabIndex={0}
    >
      <div className="num">
        #{node.sequenceIndex || index + 1} · {node.type}
      </div>

      {node.type === "video" && realMedia ? (
        <button
          type="button"
          className={mediaClass}
          onClick={handleMediaClick}
          onDoubleClick={handleMediaDoubleClick}
          title="Click to preview · double-click to replace video"
        >
          <video src={node.src!} controls playsInline preload="metadata" />
          <span className="sc-board-media-hint">{mediaHint}</span>
        </button>
      ) : (
        <button
          type="button"
          className={mediaClass}
          onClick={handleMediaClick}
          onDoubleClick={handleMediaDoubleClick}
          title={realMedia ? "Click to preview · double-click to replace" : "Click to select · paste or browse"}
        >
          <img src={mediaSrc} alt="" draggable={false} />
          <span className="sc-board-media-hint">{mediaHint}</span>
        </button>
      )}

      {previewOpen && realMedia && node.src ? (
        <MediaPreview
          src={node.src}
          kind={node.type === "video" ? "video" : "image"}
          onClose={() => setPreviewOpen(false)}
          onCopyInstructions={
            canCopyInstructions
              ? () => onCopyAnnotationInstructions!(node.id)
              : undefined
          }
          onAnnotate={
            node.type === "image" && onAnnotateImage
              ? () => {
                  setPreviewOpen(false);
                  onAnnotateImage(node.id);
                }
              : undefined
          }
        />
      ) : null}

      <input
        ref={fileRef}
        type="file"
        accept={node.type === "video" ? "video/*" : "image/*"}
        hidden
        onChange={onFile}
      />

      <textarea
        ref={bodyRef}
        className="sc-board-cap"
        value={node.body || ""}
        placeholder={node.title || "Edit text…"}
        rows={4}
        onClick={(e) => e.stopPropagation()}
        onFocus={() => {
          hadBodyFocusRef.current = true;
          onBeginTextEdit(node.id);
        }}
        onBlur={() => {
          hadBodyFocusRef.current = false;
          onEndTextEdit();
        }}
        onChange={(e) => onChangeNode(node.id, { body: e.target.value })}
      />
    </div>
  );
}

export function BoardView({
  nodes,
  focusId,
  onFocusNode,
  onChangeNode,
  onBeginTextEdit,
  onEndTextEdit,
  onReplaceMedia,
  onAnnotateImage,
  onCopyAnnotationInstructions,
  onNodeContextMenu,
  searchQuery = "",
  scrollToId = null,
}: {
  nodes: GraphNode[];
  focusId: string | null;
  onFocusNode: (id: string | null) => void;
  onChangeNode: (id: string, patch: BoardNodePatch) => void;
  onBeginTextEdit: (id: string) => void;
  onEndTextEdit: () => void;
  onReplaceMedia: (id: string, file: File) => void;
  onAnnotateImage?: (id: string) => void;
  onCopyAnnotationInstructions?: (id: string) => void;
  onNodeContextMenu?: (id: string, e: React.MouseEvent) => void;
  searchQuery?: string;
  scrollToId?: string | null;
}) {
  const cardRefs = useRef(new Map<string, HTMLDivElement>());
  const ordered = orderedNodes(nodes).filter((n) => n.type !== "frame");
  const q = searchQuery.trim();
  const matchIds = q ? matchCardIds(nodes, q) : null;
  const filtering = q.length > 0;
  const display = filtering
    ? searchCards(nodes, q, 999).map((r) => r.node)
    : ordered;

  useEffect(() => {
    if (!scrollToId) return;
    const el = cardRefs.current.get(scrollToId);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [scrollToId, display.length]);

  const handleReplace = useCallback(
    (id: string, file: File) => {
      const node = nodes.find((n) => n.id === id);
      if (!node) return;
      const kind = classifyFile(file);
      if (node.type === "video" && kind !== "video") return;
      if ((node.type === "image" || !node.src) && kind === "video" && node.type !== "video") {
        /* allow image file on text nodes via parent handler */
      }
      onReplaceMedia(id, file);
    },
    [nodes, onReplaceMedia]
  );

  return (
    <div className="sc-board">
      <p className="sc-board-hint">
        {filtering
          ? `Showing ${display.length} match${display.length === 1 ? "" : "es"} for “${q}”`
          : "Click a card to focus · click image area to select/preview · double-click or second click to browse"}
      </p>
      {display.map((n, i) => {
        const ordIndex = ordered.findIndex((x) => x.id === n.id);
        const matched = matchIds ? matchIds.has(n.id) : undefined;
        return (
          <BoardCard
            key={n.id}
            node={n}
            index={ordIndex >= 0 ? ordIndex : i}
            focused={focusId === n.id}
            matched={matched}
            cardRef={(el) => {
              if (el) cardRefs.current.set(n.id, el);
              else cardRefs.current.delete(n.id);
            }}
            onFocus={() => onFocusNode(n.id)}
            onChangeNode={onChangeNode}
            onBeginTextEdit={onBeginTextEdit}
            onEndTextEdit={onEndTextEdit}
            onReplaceMedia={handleReplace}
            onAnnotateImage={onAnnotateImage}
            onCopyAnnotationInstructions={onCopyAnnotationInstructions}
            onContextMenu={onNodeContextMenu}
          />
        );
      })}
    </div>
  );
}

export function PresentView({
  nodes,
  index,
  onPrev,
  onNext,
  onExit,
}: {
  nodes: GraphNode[];
  index: number;
  onPrev: () => void;
  onNext: () => void;
  onExit: () => void;
}) {
  const ordered = orderedNodes(nodes).filter((n) => n.type !== "frame");
  const n = ordered[Math.max(0, Math.min(index, ordered.length - 1))];
  return (
    <div className="sc-present">
      <div className="slide">
        {n?.type === "image" && n.src ? <img src={n.src} alt="" /> : null}
        {n?.type === "video" && n.src ? (
          <video src={n.src} controls playsInline preload="metadata" />
        ) : null}
        <div className="slide-text">{n ? n.body || n.title : "No beats yet"}</div>
      </div>
      <div className="nav">
        <button type="button" onClick={onPrev}>
          Prev
        </button>
        <span>
          {ordered.length ? index + 1 : 0} / {ordered.length}
        </span>
        <button type="button" onClick={onNext}>
          Next
        </button>
        <button type="button" onClick={onExit}>
          Exit
        </button>
        <button type="button" onClick={() => window.print()}>
          Print / PDF
        </button>
      </div>
    </div>
  );
}
