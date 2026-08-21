import { useEffect, useMemo, useRef, useState } from "react";
import type { LocalHistoryEntry } from "../api";
import { toEpochMs, type ProjectSummary } from "../api";

export type ProjectSource = "server" | "local";

export interface ProjectRow {
  id: string;
  title: string;
  updatedAt: number;
  nodeCount: number;
  source: ProjectSource;
  isCurrent?: boolean;
}

function formatWhen(ts?: number): string {
  if (!ts) return "Unknown date";
  const d = new Date(ts);
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  if (sameDay) return `Today · ${time}`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) + ` · ${time}`;
}

export function mergeProjectRows(
  server: ProjectSummary[],
  local: LocalHistoryEntry[],
  currentId: string | null
): ProjectRow[] {
  const map = new Map<string, ProjectRow>();

  for (const p of server) {
    map.set(p.id, {
      id: p.id,
      title: p.title || "Untitled story",
      updatedAt: toEpochMs(p.updated_at),
      nodeCount: p.node_count || 0,
      source: "server",
      isCurrent: p.id === currentId,
    });
  }

  for (const entry of local) {
    const existing = map.get(entry.id);
    const localUpdated = entry.updatedAt || 0;
    if (!existing || localUpdated > existing.updatedAt) {
      map.set(entry.id, {
        id: entry.id,
        title: entry.title || "Untitled story",
        updatedAt: localUpdated,
        nodeCount: entry.nodeCount || entry.payload?.nodes?.length || 0,
        source: existing ? "server" : "local",
        isCurrent: entry.id === currentId,
      });
    } else if (existing) {
      existing.isCurrent = entry.id === currentId;
    }
  }

  return [...map.values()].sort((a, b) => b.updatedAt - a.updatedAt);
}

interface ProjectsPanelProps {
  open: boolean;
  onClose: () => void;
  rows: ProjectRow[];
  lastProjectId: string | null;
  loading?: boolean;
  welcomeMode?: boolean;
  onLoad: (id: string, source: ProjectSource) => void;
  onResumeLast: () => void;
  onNew: () => void;
  onRefresh: () => void;
  onDelete: (id: string, source: ProjectSource) => void;
  onBulkDelete: (items: Array<{ id: string; source: ProjectSource }>) => void;
  onImportFiles: (files: FileList | File[]) => void;
  importStatus?: string | null;
}

export function ProjectsPanel({
  open,
  onClose,
  rows,
  lastProjectId,
  loading,
  welcomeMode,
  onLoad,
  onResumeLast,
  onNew,
  onRefresh,
  onDelete,
  onBulkDelete,
  onImportFiles,
  importStatus,
}: ProjectsPanelProps) {
  const [query, setQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const importInputRef = useRef<HTMLInputElement>(null);
  const welcomeImportRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) => r.title.toLowerCase().includes(q) || r.id.toLowerCase().includes(q)
    );
  }, [rows, query]);

  useEffect(() => {
    if (!open) setSelectedIds(new Set());
  }, [open]);

  useEffect(() => {
    setSelectedIds((prev) => {
      const valid = new Set(rows.map((r) => r.id));
      const next = new Set([...prev].filter((id) => valid.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [rows]);

  const allFilteredSelected =
    filtered.length > 0 && filtered.every((r) => selectedIds.has(r.id));

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allFilteredSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const r of filtered) next.delete(r.id);
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const r of filtered) next.add(r.id);
        return next;
      });
    }
  };

  const handleBulkDelete = () => {
    const items = rows
      .filter((r) => selectedIds.has(r.id))
      .map((r) => ({ id: r.id, source: r.source }));
    if (!items.length) return;
    onBulkDelete(items);
    setSelectedIds(new Set());
  };

  if (!open) return null;

  const lastRow = lastProjectId ? rows.find((r) => r.id === lastProjectId) : rows[0];
  const selectionCount = selectedIds.size;

  return (
    <div className="sc-projects-backdrop" role="presentation" onClick={onClose}>
      <div
        className="sc-projects-modal"
        role="dialog"
        aria-label={welcomeMode ? "Welcome" : "Open story"}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sc-projects-head">
          <div>
            <h2>{welcomeMode ? "Welcome to Story Canvas" : "Open story"}</h2>
            <p>
              {welcomeMode
                ? "Import an existing `.story.json` file or start a new blank canvas."
                : "Browse saved stories, import `.story.json` files, or resume your last session."}
            </p>
          </div>
          <button type="button" className="sc-projects-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {welcomeMode && (
          <div className="sc-projects-welcome">
            <button type="button" className="primary" onClick={() => welcomeImportRef.current?.click()}>
              Import JSON…
            </button>
            <button type="button" onClick={onNew}>
              New story
            </button>
            <input
              ref={welcomeImportRef}
              type="file"
              accept=".json,.story.json,application/json"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files?.length) onImportFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>
        )}

        <div className="sc-projects-toolbar">
          <input
            type="search"
            placeholder="Search by title or id…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus={!welcomeMode}
          />
          <button type="button" onClick={onRefresh} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          <button type="button" onClick={() => importInputRef.current?.click()}>
            Import JSON…
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".json,.story.json,application/json"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files?.length) onImportFiles(e.target.files);
              e.target.value = "";
            }}
          />
          {!welcomeMode && (
            <button type="button" className="primary" onClick={onNew}>
              New story
            </button>
          )}
          {selectionCount > 0 && (
            <button type="button" className="sc-projects-bulk-delete" onClick={handleBulkDelete}>
              Delete {selectionCount} selected
            </button>
          )}
        </div>

        {importStatus && <p className="sc-projects-import-status">{importStatus}</p>}

        {!welcomeMode && lastRow && (
          <button type="button" className="sc-projects-resume" onClick={onResumeLast}>
            <span className="label">Resume last</span>
            <strong>{lastRow.title}</strong>
            <span className="meta">
              {formatWhen(lastRow.updatedAt)} · {lastRow.nodeCount} nodes
            </span>
          </button>
        )}

        {filtered.length > 0 && (
          <div className="sc-projects-list-head">
            <label className="sc-projects-select-all">
              <input
                type="checkbox"
                checked={allFilteredSelected}
                onChange={toggleSelectAll}
                aria-label="Select all visible stories"
              />
              <span>Select all</span>
            </label>
            {selectionCount > 0 && (
              <span className="sc-projects-selection-count">{selectionCount} selected</span>
            )}
          </div>
        )}

        <ul className="sc-projects-list">
          {filtered.length === 0 && (
            <li className="sc-projects-empty">
              {rows.length === 0
                ? welcomeMode
                  ? "No saved stories yet — import a file or create a new story above."
                  : "No saved stories yet. Your work autosaves here after you add nodes."
                : "No matches for that search."}
            </li>
          )}
          {filtered.map((row) => (
            <li key={row.id} className={row.isCurrent ? "active" : ""}>
              <label className="sc-projects-check" aria-label={`Select ${row.title}`}>
                <input
                  type="checkbox"
                  checked={selectedIds.has(row.id)}
                  onChange={() => toggleSelect(row.id)}
                  onClick={(e) => e.stopPropagation()}
                />
              </label>
              <button type="button" className="sc-projects-row" onClick={() => onLoad(row.id, row.source)}>
                <span className="sc-projects-row-main">
                  <strong>{row.title}</strong>
                  <span className="meta">
                    {formatWhen(row.updatedAt)} · {row.nodeCount} nodes
                  </span>
                </span>
                <span className="sc-projects-badges">
                  {row.isCurrent && <span className="badge current">Current</span>}
                  <span className={`badge ${row.source}`}>
                    {row.source === "server" ? "Saved" : "Browser"}
                  </span>
                </span>
              </button>
              <button
                type="button"
                className="sc-projects-delete"
                title="Delete"
                aria-label={`Delete ${row.title}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(row.id, row.source);
                }}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

interface ProjectsSidebarProps {
  rows: ProjectRow[];
  onOpenPicker: () => void;
  onLoad: (id: string, source: ProjectSource) => void;
  onImportFiles: (files: FileList | File[]) => void;
}

export function ProjectsSidebar({ rows, onOpenPicker, onLoad, onImportFiles }: ProjectsSidebarProps) {
  const recent = rows.slice(0, 5);
  const importInputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <div className="sc-side-actions sc-side-actions-row">
        <button type="button" className="primary" onClick={onOpenPicker}>
          Open story…
        </button>
        <button type="button" onClick={() => importInputRef.current?.click()}>
          Import…
        </button>
        <input
          ref={importInputRef}
          type="file"
          accept=".json,.story.json,application/json"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files?.length) onImportFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      <ul>
        {recent.length === 0 && <li className="sc-projects-empty-inline">No saved stories yet</li>}
        {recent.map((row) => (
          <li
            key={row.id}
            className={row.isCurrent ? "active" : ""}
            onClick={() => onLoad(row.id, row.source)}
          >
            <span className="sc-side-title">{row.title}</span>
            <span className="sc-side-meta">
              {formatWhen(row.updatedAt)} · {row.nodeCount} nodes
            </span>
          </li>
        ))}
      </ul>
      {rows.length > 5 && (
        <button type="button" className="sc-side-link" onClick={onOpenPicker}>
          See all {rows.length} stories…
        </button>
      )}
    </>
  );
}
