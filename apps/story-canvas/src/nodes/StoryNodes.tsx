import { memo, useCallback, useEffect, useRef, useState } from "react";
import { Handle, NodeResizer, Position, type NodeProps, type Node } from "@xyflow/react";
import type { NodeKind } from "../domain";
import { isResizableNodeKind } from "../nodeSizing";
import { MediaPreview } from "../components/MediaPreview";
import { hasRealMedia } from "../mediaHelpers";
import { useSyncedDraft } from "../useSyncedDraft";

export type StoryNodeData = {
  kind: NodeKind;
  title: string;
  body: string;
  src?: string | null;
  sequenceIndex: number;
  provenance?: string | null;
  researchSessionId?: string | null;
  onChange?: (patch: Partial<StoryNodeData>) => void;
  onDelete?: () => void;
  onBeginTextEdit?: () => void;
  onEndTextEdit?: () => void;
  onReplaceMedia?: (file: File) => void;
  onAnnotateImage?: () => void;
  onCopyAnnotationInstructions?: () => void;
  onMediaFocus?: (additive?: boolean) => void;
  onResizeEnd?: () => void;
};

export type StoryFlowNode = Node<StoryNodeData, "story">;

function StoryNodeComponent({ data, selected }: NodeProps<StoryFlowNode>) {
  const mediaInputRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const hadBodyFocusRef = useRef(false);
  const caretRef = useRef<{ start: number; end: number } | null>(null);
  const blurTimerRef = useRef<number | null>(null);
  const clickTimerRef = useRef<number | null>(null);
  const [mediaSelected, setMediaSelected] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const realMedia = hasRealMedia({ type: data.kind, src: data.src });

  const commitBody = useCallback(
    (body: string) => {
      data.onChange?.({ body });
    },
    [data]
  );
  const { draft: bodyDraft, setDraftValue: setBodyDraft, flush: flushBody } = useSyncedDraft(
    data.body || "",
    commitBody,
    300
  );

  const onBody = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const el = e.target;
      caretRef.current = { start: el.selectionStart, end: el.selectionEnd };
      setBodyDraft(el.value);
    },
    [setBodyDraft]
  );
  const onSeq = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) =>
      data.onChange?.({ sequenceIndex: Number(e.target.value) || 0 }),
    [data]
  );
  const onMediaFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) data.onReplaceMedia?.(file);
      e.target.value = "";
    },
    [data]
  );
  const pickMedia = useCallback(() => {
    mediaInputRef.current?.click();
  }, []);

  useEffect(() => {
    if (!selected) {
      flushBody();
      hadBodyFocusRef.current = false;
      if (blurTimerRef.current != null) {
        window.clearTimeout(blurTimerRef.current);
        blurTimerRef.current = null;
      }
      setMediaSelected(false);
      setPreviewOpen(false);
    }
  }, [selected, flushBody]);

  // Restore focus/caret after parent churn (status, seq, RF sync) when we still intend to edit.
  useEffect(() => {
    if (!hadBodyFocusRef.current || !bodyRef.current) return;
    if (document.activeElement === bodyRef.current) return;
    const el = bodyRef.current;
    el.focus({ preventScroll: true });
    const caret = caretRef.current;
    const start = caret?.start ?? el.value.length;
    const end = caret?.end ?? start;
    try {
      el.setSelectionRange(start, end);
    } catch {
      /* ignore */
    }
  }, [data.body, data.sequenceIndex, selected, bodyDraft]);

  useEffect(() => {
    return () => {
      if (clickTimerRef.current) window.clearTimeout(clickTimerRef.current);
      if (blurTimerRef.current != null) window.clearTimeout(blurTimerRef.current);
    };
  }, []);

  const handleMediaClick = useCallback(
    (e: React.MouseEvent) => {
      if (data.kind !== "image" && data.kind !== "video") return;
      e.stopPropagation();
      data.onMediaFocus?.(e.shiftKey);

      if (!realMedia) {
        if (mediaSelected) pickMedia();
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
    [data.kind, realMedia, mediaSelected, pickMedia, data]
  );

  const handleMediaDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      if (data.kind !== "image" && data.kind !== "video") return;
      e.stopPropagation();
      if (clickTimerRef.current) {
        window.clearTimeout(clickTimerRef.current);
        clickTimerRef.current = null;
      }
      if (realMedia) {
        setPreviewOpen(false);
        pickMedia();
      }
    },
    [data.kind, realMedia, pickMedia]
  );

  const mediaClass = [
    "sc-media-wrap",
    mediaSelected && !realMedia ? "empty-selected" : "",
    mediaSelected && realMedia ? "image-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const isFrame = data.kind === "frame";
  const resizable = isResizableNodeKind(data.kind);
  const mediaAccept = data.kind === "video" ? "video/*" : "image/*";

  return (
    <div
      className={`sc-node kind-${data.kind}${selected ? " selected" : ""}${isFrame ? " frame" : ""}${resizable ? " resizable" : ""}`}
    >
      {resizable ? (
        <NodeResizer
          isVisible={selected}
          minWidth={isFrame ? 320 : 180}
          minHeight={isFrame ? 240 : 96}
          maxWidth={isFrame ? 960 : 640}
          maxHeight={isFrame ? 720 : 480}
          onResizeEnd={() => data.onResizeEnd?.()}
        />
      ) : null}
      <Handle type="target" position={Position.Left} className="sc-port" />
      <div className="sc-node-head">
        <span>{data.title || data.kind.toUpperCase()}</span>
        <button type="button" className="sc-del" onClick={() => data.onDelete?.()} title="Delete">
          ×
        </button>
      </div>
      <div className="sc-node-body">
        {data.kind === "image" ? (
          <>
            <button
              type="button"
              className={mediaClass}
              onClick={handleMediaClick}
              onDoubleClick={handleMediaDoubleClick}
              title={
                realMedia
                  ? "Click to preview · double-click to replace"
                  : "Click to select · paste or double-click to browse"
              }
            >
              <img src={data.src || ""} alt={data.title} draggable={false} />
              {selected || mediaSelected ? (
                <span className="sc-replace-hint">
                  {realMedia
                    ? "Preview · double-click to replace"
                    : mediaSelected
                      ? "Paste or click again to browse"
                      : "Click to select placement"}
                </span>
              ) : null}
            </button>
            {previewOpen && realMedia && data.src ? (
              <MediaPreview
                src={data.src}
                kind="image"
                onClose={() => setPreviewOpen(false)}
                onCopyInstructions={data.onCopyAnnotationInstructions}
                onAnnotate={
                  data.onAnnotateImage
                    ? () => {
                        setPreviewOpen(false);
                        data.onAnnotateImage?.();
                      }
                    : undefined
                }
              />
            ) : null}
            <input
              ref={mediaInputRef}
              type="file"
              accept={mediaAccept}
              hidden
              onChange={onMediaFile}
            />
            <div className="sc-meta">
              {data.provenance || "image"}
              {data.onCopyAnnotationInstructions ? (
                <>
                  {" · "}
                  <button
                    type="button"
                    className="sc-inline-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      data.onCopyAnnotationInstructions?.();
                    }}
                  >
                    Copy instructions
                  </button>
                </>
              ) : null}
            </div>
          </>
        ) : data.kind === "video" ? (
          <>
            <button
              type="button"
              className={mediaClass}
              onClick={handleMediaClick}
              onDoubleClick={handleMediaDoubleClick}
              title={
                realMedia
                  ? "Click to preview · double-click to replace"
                  : "Click to select · paste or double-click to browse"
              }
            >
              <video src={data.src || ""} controls playsInline preload="metadata" />
              {selected || mediaSelected ? (
                <span className="sc-replace-hint">
                  {realMedia
                    ? "Preview · double-click to replace"
                    : mediaSelected
                      ? "Paste or click again to browse"
                      : "Click to select placement"}
                </span>
              ) : null}
            </button>
            {previewOpen && realMedia && data.src ? (
              <MediaPreview src={data.src} kind="video" onClose={() => setPreviewOpen(false)} />
            ) : null}
            <input
              ref={mediaInputRef}
              type="file"
              accept={mediaAccept}
              hidden
              onChange={onMediaFile}
            />
            <div className="sc-meta">{data.provenance || "video"}</div>
          </>
        ) : (
          <>
            <textarea
              ref={bodyRef}
              className="nodrag nopan nowheel"
              value={bodyDraft}
              onChange={onBody}
              onSelect={(e) => {
                const el = e.currentTarget;
                caretRef.current = { start: el.selectionStart, end: el.selectionEnd };
              }}
              onFocus={() => {
                if (blurTimerRef.current != null) {
                  window.clearTimeout(blurTimerRef.current);
                  blurTimerRef.current = null;
                }
                hadBodyFocusRef.current = true;
                data.onBeginTextEdit?.();
              }}
              onBlur={() => {
                flushBody();
                // Defer clear: RF remounts / parent sync can fire blur before focus restore.
                if (blurTimerRef.current != null) window.clearTimeout(blurTimerRef.current);
                blurTimerRef.current = window.setTimeout(() => {
                  blurTimerRef.current = null;
                  if (document.activeElement === bodyRef.current) return;
                  hadBodyFocusRef.current = false;
                  data.onEndTextEdit?.();
                }, 0);
              }}
              rows={isFrame ? 2 : 5}
              style={resizable ? { height: "100%" } : undefined}
            />
            {data.kind === "research" && (
              <div className="sc-meta">
                editable context
                {data.researchSessionId ? ` · ${data.researchSessionId}` : ""}
              </div>
            )}
          </>
        )}
        <label className="sc-seq">
          seq
          <input type="number" value={data.sequenceIndex ?? 0} onChange={onSeq} />
        </label>
      </div>
      <Handle type="source" position={Position.Right} className="sc-port" />
    </div>
  );
}

export const StoryNode = memo(StoryNodeComponent);

export const nodeTypes = { story: StoryNode };
