import { useCallback, useEffect, useLayoutEffect, useRef, type MutableRefObject } from "react";
import type { AlignAction } from "./alignNodes";
import { restoreEditableFocus, type EditableFocusSnap } from "./editableFocus";

export type ResearchMenuState =
  | { phase: "menu"; x: number; y: number; nodeId: string; selectedIds: string[] }
  | { phase: "prompt"; nodeId: string; query: string }
  | null;

function IconSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="7" cy="7" r="4.25" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M10.2 10.2 14 14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function IconAlignRows() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

function IconAlignTop() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M2 3h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="4" y="5" width="8" height="7" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function IconAlignMiddleH() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M2 8h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="4" y="3" width="8" height="10" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function IconAlignBottom() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M2 13h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="4" y="2" width="8" height="7" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function IconAlignLeft() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M3 2v12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="5" y="4" width="7" height="8" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function IconAlignMiddleV() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M8 2v12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="3" y="4" width="10" height="8" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function IconAlignRight() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M13 2v12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="4" y="4" width="7" height="8" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function IconDistributeH() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <rect x="2" y="5" width="3" height="6" rx="0.75" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <rect x="6.5" y="5" width="3" height="6" rx="0.75" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <rect x="11" y="5" width="3" height="6" rx="0.75" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <path d="M5 8h1.5M9.5 8H11" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

function IconDistributeV() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <rect x="5" y="2" width="6" height="3" rx="0.75" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <rect x="5" y="6.5" width="6" height="3" rx="0.75" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <rect x="5" y="11" width="6" height="3" rx="0.75" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <path d="M8 5v1.5M8 9.5V11" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

function IconAnnotate() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M3 13h2.5L13 5.5 10.5 3 3 10.5V13Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <path d="M9 4 12 7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function IconCopyInstructions() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M5.5 2.5h6a1 1 0 0 1 1 1v8.5h-1.5V4H5.5V2.5ZM3 5.5h6.5a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function NodeResearchMenu({
  state,
  loading,
  priorFocusRef,
  canAnnotateImage,
  canCopyInstructions,
  onClose,
  onOpenPrompt,
  onAnnotateImage,
  onCopyInstructions,
  onQueryChange,
  onSubmit,
  onAlign,
}: {
  state: ResearchMenuState;
  loading: boolean;
  /** Snap taken when the context menu opened; restored when UI fully dismisses. */
  priorFocusRef?: MutableRefObject<EditableFocusSnap | null>;
  canAnnotateImage?: boolean;
  canCopyInstructions?: boolean;
  onClose: () => void;
  onOpenPrompt: (nodeId: string) => void;
  onAnnotateImage?: (nodeId: string) => void;
  onCopyInstructions?: (nodeId: string) => void;
  onQueryChange: (query: string) => void;
  onSubmit: (nodeId: string, query: string) => void;
  onAlign: (selectedIds: string[], action: AlignAction) => void;
}) {
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const wasOpenRef = useRef(false);

  const dismiss = useCallback(() => {
    onClose();
  }, [onClose]);

  // Restore caret when the research UI fully closes (menu or prompt → null).
  // Keep the snap across menu → prompt so Cancel still returns to the editor.
  useLayoutEffect(() => {
    if (state) {
      wasOpenRef.current = true;
      return;
    }
    if (!wasOpenRef.current) return;
    wasOpenRef.current = false;
    const snap = priorFocusRef?.current ?? null;
    if (priorFocusRef) priorFocusRef.current = null;
    restoreEditableFocus(snap);
  }, [state, priorFocusRef]);

  useEffect(() => {
    if (state?.phase !== "menu") return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      dismiss();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [state, dismiss]);

  useEffect(() => {
    if (state?.phase === "prompt") inputRef.current?.focus();
  }, [state]);

  const onPromptKey = useCallback(
    (e: React.KeyboardEvent, nodeId: string, query: string) => {
      if (e.key === "Enter" && !loading) {
        e.preventDefault();
        onSubmit(nodeId, query);
      }
      if (e.key === "Escape") dismiss();
    },
    [loading, dismiss, onSubmit]
  );

  const runAlign = useCallback(
    (action: AlignAction) => {
      if (state?.phase !== "menu") return;
      onAlign(state.selectedIds, action);
      dismiss();
    },
    [state, onAlign, dismiss]
  );

  if (!state) return null;

  if (state.phase === "menu") {
    const canAlign = state.selectedIds.length >= 2;

    return (
      <div
        ref={menuRef}
        className="sc-ctx-menu"
        style={{ left: state.x, top: state.y }}
        role="menu"
      >
        <button
          type="button"
          role="menuitem"
          className="sc-ctx-menu-item"
          onClick={() => onOpenPrompt(state.nodeId)}
        >
          <IconSearch />
          <span>Firecrawl</span>
        </button>

        {canAnnotateImage && onAnnotateImage ? (
          <button
            type="button"
            role="menuitem"
            className="sc-ctx-menu-item"
            onClick={() => {
              onAnnotateImage(state.nodeId);
              dismiss();
            }}
          >
            <IconAnnotate />
            <span>Annotate image</span>
          </button>
        ) : null}

        {canCopyInstructions && onCopyInstructions ? (
          <button
            type="button"
            role="menuitem"
            className="sc-ctx-menu-item"
            onClick={() => {
              void onCopyInstructions(state.nodeId);
              dismiss();
            }}
          >
            <IconCopyInstructions />
            <span>Copy instructions</span>
          </button>
        ) : null}

        <div
          className={`sc-ctx-menu-item sc-ctx-submenu-trigger${canAlign ? "" : " disabled"}`}
          role="none"
        >
          <span className="sc-ctx-menu-item-label">
            <IconAlignRows />
            <span>Align</span>
            <span className="sc-ctx-chevron" aria-hidden="true">
              ›
            </span>
          </span>
          <div className="sc-ctx-submenu" role="menu" aria-label="Align nodes">
            <div className="sc-ctx-align-row">
              <button
                type="button"
                className="sc-ctx-icon-btn"
                title="Align top"
                aria-label="Align top"
                disabled={!canAlign}
                onClick={() => runAlign({ kind: "align-h", mode: "top" })}
              >
                <IconAlignTop />
              </button>
              <button
                type="button"
                className="sc-ctx-icon-btn"
                title="Align vertical center"
                aria-label="Align vertical center"
                disabled={!canAlign}
                onClick={() => runAlign({ kind: "align-h", mode: "center" })}
              >
                <IconAlignMiddleH />
              </button>
              <button
                type="button"
                className="sc-ctx-icon-btn"
                title="Align bottom"
                aria-label="Align bottom"
                disabled={!canAlign}
                onClick={() => runAlign({ kind: "align-h", mode: "bottom" })}
              >
                <IconAlignBottom />
              </button>
            </div>
            <div className="sc-ctx-align-row">
              <button
                type="button"
                className="sc-ctx-icon-btn"
                title="Align left"
                aria-label="Align left"
                disabled={!canAlign}
                onClick={() => runAlign({ kind: "align-v", mode: "left" })}
              >
                <IconAlignLeft />
              </button>
              <button
                type="button"
                className="sc-ctx-icon-btn"
                title="Align horizontal center"
                aria-label="Align horizontal center"
                disabled={!canAlign}
                onClick={() => runAlign({ kind: "align-v", mode: "center" })}
              >
                <IconAlignMiddleV />
              </button>
              <button
                type="button"
                className="sc-ctx-icon-btn"
                title="Align right"
                aria-label="Align right"
                disabled={!canAlign}
                onClick={() => runAlign({ kind: "align-v", mode: "right" })}
              >
                <IconAlignRight />
              </button>
            </div>
            <div className="sc-ctx-align-row sc-ctx-align-row-distribute">
              <button
                type="button"
                className="sc-ctx-icon-btn"
                title="Distribute horizontal spacing"
                aria-label="Distribute horizontal spacing"
                disabled={!canAlign}
                onClick={() => runAlign({ kind: "distribute", axis: "horizontal" })}
              >
                <IconDistributeH />
              </button>
              <button
                type="button"
                className="sc-ctx-icon-btn"
                title="Distribute vertical spacing"
                aria-label="Distribute vertical spacing"
                disabled={!canAlign}
                onClick={() => runAlign({ kind: "distribute", axis: "vertical" })}
              >
                <IconDistributeV />
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="sc-research-backdrop" onMouseDown={dismiss}>
      <div
        className="sc-research-dialog"
        role="dialog"
        aria-labelledby="sc-research-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h3 id="sc-research-title">Firecrawl search</h3>
        <p>Edit the query before searching. Results become a linked research node.</p>
        <input
          ref={inputRef}
          type="text"
          value={state.query}
          disabled={loading}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => onPromptKey(e, state.nodeId, state.query)}
          placeholder="Search query…"
        />
        <div className="sc-research-actions">
          <button type="button" onClick={dismiss} disabled={loading}>
            Cancel
          </button>
          <button
            type="button"
            className="primary"
            disabled={loading || !state.query.trim()}
            onClick={() => onSubmit(state.nodeId, state.query)}
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </div>
      </div>
    </div>
  );
}
