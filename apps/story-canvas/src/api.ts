import type { StoryProject } from "./domain";

export class ApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function parseApiErrorBody(text: string): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    const msg =
      (typeof parsed.error === "string" && parsed.error) ||
      (typeof parsed.detail === "string" && parsed.detail) ||
      (typeof parsed.message === "string" && parsed.message);
    return msg || null;
  } catch {
    if (trimmed.length <= 160 && !trimmed.startsWith("{") && !trimmed.startsWith("[")) {
      return trimmed;
    }
    return null;
  }
}

function isNetworkError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return /failed to fetch|networkerror|network error|load failed|fetch failed/i.test(err.message);
}

function isAuthMessage(msg: string): boolean {
  return /not authenticated|invalid api token|unauthorized/i.test(msg);
}

/** Map Firecrawl research failures to plain-English status copy. */
export function friendlyResearchErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const detail = parseApiErrorBody(err.body) || err.message;
    if (err.status === 503) {
      if (/not configured|api key/i.test(detail)) {
        return detail;
      }
      return "Firecrawl is not configured on the server — add FIRECRAWL_API_KEY to .env and restart Odysseus.";
    }
    if (err.status === 401 || isAuthMessage(detail)) {
      return "Sign in to Odysseus to run Firecrawl research.";
    }
    if (err.status === 502) {
      if (/no results/i.test(detail)) {
        return "Firecrawl returned no results — try a different query.";
      }
      if (detail && !detail.startsWith("{")) {
        return detail.replace(/^Firecrawl search failed:\s*/i, "Firecrawl error: ");
      }
      return "Firecrawl search failed — check server logs or try again.";
    }
    if (detail && !detail.startsWith("{")) {
      return detail.slice(0, 200);
    }
  }

  if (isNetworkError(err)) {
    return "Couldn't reach the server — is Odysseus running?";
  }

  if (err instanceof Error) {
    const msg = err.message.replace(/^Error:\s*/i, "").trim();
    const parsed = parseApiErrorBody(msg);
    if (parsed) return parsed.slice(0, 200);
    if (msg.length <= 160 && !msg.startsWith("{")) return msg;
  }

  return "Research failed — try again or check Odysseus settings.";
}

/** Map save/API failures to plain-English status copy (no raw JSON). */
export function friendlySaveErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const detail = parseApiErrorBody(err.body) || err.message;
    if (err.status === 401 || isAuthMessage(detail)) {
      return "You're not signed in — saved to this browser only. Sign in to Odysseus to sync to the server.";
    }
    if (err.status === 403) {
      return "You don't have permission to save this story — saved to this browser only.";
    }
    if (err.status >= 500) {
      return "The server had a problem — saved to this browser only.";
    }
    if (detail && !detail.startsWith("{")) {
      return `${detail} — saved to this browser only.`;
    }
    return "Couldn't save to the server — saved to this browser only.";
  }

  if (isNetworkError(err)) {
    return "Couldn't reach the server — saved to this browser only.";
  }

  if (err instanceof Error) {
    const msg = err.message.replace(/^Error:\s*/i, "").trim();
    if (isAuthMessage(msg)) {
      return "You're not signed in — saved to this browser only. Sign in to Odysseus to sync to the server.";
    }
    if (isNetworkError(err)) {
      return "Couldn't reach the server — saved to this browser only.";
    }
    const parsed = parseApiErrorBody(msg);
    if (parsed) {
      if (isAuthMessage(parsed)) {
        return "You're not signed in — saved to this browser only. Sign in to Odysseus to sync to the server.";
      }
      return `${parsed} — saved to this browser only.`;
    }
    if (msg.startsWith("{") || msg.startsWith("[")) {
      return "Couldn't save to the server — saved to this browser only.";
    }
    if (msg.length <= 120) {
      return `${msg} — saved to this browser only.`;
    }
  }

  return "Couldn't save to the server — saved to this browser only.";
}

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new ApiError(text || res.statusText, res.status, text);
  }
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}

export interface ProjectSummary {
  id: string;
  title: string;
  node_count?: number;
  updated_at?: number;
}

export async function listProjects(): Promise<ProjectSummary[]> {
  const data = await req<{ projects: ProjectSummary[] }>("/api/story-canvas/projects");
  return data.projects || [];
}

export async function loadProject(
  id: string
): Promise<{ id: string; title: string; payload: StoryProject; updated_at?: number; created_at?: number }> {
  return req(`/api/story-canvas/projects/${id}`);
}

export async function saveProject(
  projectId: string | null | undefined,
  title: string,
  payload: StoryProject
): Promise<{ id: string }> {
  if (!projectId) {
    return req("/api/story-canvas/projects", {
      method: "POST",
      body: JSON.stringify({ title, payload }),
    });
  }
  await req(`/api/story-canvas/projects/${projectId}`, {
    method: "PUT",
    body: JSON.stringify({ title, payload }),
  });
  return { id: projectId };
}

export async function exportOd(
  projectId: string,
  opts: { nodeIds?: string[]; designMd?: string; handoff?: boolean } = {}
): Promise<{ brief_path: string; brief_md: string; handoff_dir?: string | null }> {
  return req(`/api/story-canvas/projects/${projectId}/export-od`, {
    method: "POST",
    body: JSON.stringify(opts),
  });
}

export async function uploadAsset(projectId: string, dataUrl: string, filename?: string): Promise<{ url: string }> {
  return req(`/api/story-canvas/projects/${projectId}/assets`, {
    method: "POST",
    body: JSON.stringify({ data_url: dataUrl, filename }),
  });
}

export async function researchLibrary(): Promise<Array<{ id: string; title?: string; query?: string }>> {
  const data = await req<any>("/api/research/library");
  const list = data?.research || data?.items || data?.sessions || data || [];
  return Array.isArray(list) ? list : [];
}

export async function researchDetail(sessionId: string): Promise<any> {
  return req(`/api/research/detail/${encodeURIComponent(sessionId)}`);
}

export interface FirecrawlResearchResult {
  query: string;
  results: Array<{ title?: string; url?: string; snippet?: string; age?: string }>;
  result_count: number;
  provider: string;
}

export async function storyCanvasResearch(
  query: string,
  count = 8
): Promise<FirecrawlResearchResult> {
  return req("/api/story-canvas/research", {
    method: "POST",
    body: JSON.stringify({ query: query.trim(), count }),
  });
}

const LAST_KEY = "story-canvas:last";
const LAST_ID_KEY = "story-canvas:lastProjectId";
const HISTORY_KEY = "story-canvas:history";
const MAX_HISTORY = 30;
/** Above this size, history stores metadata only (full payload stays in last snapshot). */
const HISTORY_PAYLOAD_MAX_BYTES = 512_000;

export interface LocalHistoryEntry {
  id: string;
  title: string;
  updatedAt: number;
  nodeCount: number;
  /** Omitted for large projects to avoid localStorage quota errors. */
  payload?: StoryProject;
}

function estimateJsonBytes(obj: unknown): number {
  try {
    return new Blob([JSON.stringify(obj)]).size;
  } catch {
    return Number.POSITIVE_INFINITY;
  }
}

function safeLocalStorageSet(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch (err) {
    console.warn(`localStorage set failed for ${key}:`, err);
    return false;
  }
}

function writeHistory(history: LocalHistoryEntry[]): boolean {
  if (safeLocalStorageSet(HISTORY_KEY, JSON.stringify(history))) return true;
  const metadataOnly = history.map(({ id, title, updatedAt, nodeCount }) => ({
    id,
    title,
    updatedAt,
    nodeCount,
  }));
  return safeLocalStorageSet(HISTORY_KEY, JSON.stringify(metadataOnly));
}

export function loadLocalHistory(): LocalHistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? (JSON.parse(raw) as LocalHistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function getLocalHistoryEntry(id: string): LocalHistoryEntry | null {
  return loadLocalHistory().find((h) => h.id === id) || null;
}

export function removeLocalHistory(id: string) {
  const history = loadLocalHistory().filter((h) => h.id !== id);
  writeHistory(history);
  const lastId = loadLastProjectId();
  if (lastId === id) {
    localStorage.removeItem(LAST_ID_KEY);
    localStorage.removeItem(LAST_KEY);
  }
}

export function removeLocalHistoryBulk(ids: string[]) {
  if (!ids.length) return;
  const drop = new Set(ids);
  const history = loadLocalHistory().filter((h) => !drop.has(h.id));
  writeHistory(history);
  const lastId = loadLastProjectId();
  if (lastId && drop.has(lastId)) {
    localStorage.removeItem(LAST_ID_KEY);
    localStorage.removeItem(LAST_KEY);
  }
}

function buildHistoryEntry(
  payload: StoryProject,
  opts: { forceMetadataOnly?: boolean } = {}
): LocalHistoryEntry {
  const id = payload.id || `local-${payload.updatedAt || Date.now()}`;
  const stamped: StoryProject = { ...payload, id };
  const base: LocalHistoryEntry = {
    id,
    title: stamped.title || "Untitled story",
    updatedAt: stamped.updatedAt || Date.now(),
    nodeCount: stamped.nodes?.length || 0,
  };
  if (opts.forceMetadataOnly || estimateJsonBytes(stamped) > HISTORY_PAYLOAD_MAX_BYTES) {
    return base;
  }
  return { ...base, payload: stamped };
}

function pushLocalHistory(
  payload: StoryProject,
  opts: { forceMetadataOnly?: boolean } = {}
): StoryProject {
  const id = payload.id || `local-${payload.updatedAt || Date.now()}`;
  const stamped: StoryProject = { ...payload, id };
  const entry = buildHistoryEntry(stamped, opts);
  let history = loadLocalHistory().filter((h) => h.id !== id);
  history.unshift(entry);
  if (history.length > MAX_HISTORY) history = history.slice(0, MAX_HISTORY);
  writeHistory(history);
  return stamped;
}

/** Upsert history metadata without touching the last-open snapshot (for server preload). */
export function upsertHistoryMetadata(payload: StoryProject) {
  pushLocalHistory(payload, { forceMetadataOnly: true });
}

export function persistLocal(payload: StoryProject) {
  const stamped = pushLocalHistory(payload);
  safeLocalStorageSet(LAST_KEY, JSON.stringify(stamped));
  if (stamped.id) safeLocalStorageSet(LAST_ID_KEY, stamped.id);
}

/** True when the user has no saved stories in browser or on server. */
export function hasSavedStories(
  history: LocalHistoryEntry[],
  serverProjects: ProjectSummary[]
): boolean {
  if (history.length > 0 || serverProjects.length > 0) return true;
  if (loadLastProjectId()) return true;
  const local = loadLocal();
  return Boolean(local?.nodes?.length);
}

export function loadLocal(): StoryProject | null {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    return raw ? (JSON.parse(raw) as StoryProject) : null;
  } catch {
    return null;
  }
}

export async function deleteProject(id: string): Promise<void> {
  await req(`/api/story-canvas/projects/${id}`, { method: "DELETE" });
}

export function loadLastProjectId(): string | null {
  return localStorage.getItem(LAST_ID_KEY);
}

/** Server uses seconds; browser uses ms — normalize for comparisons. */
export function toEpochMs(ts?: number): number {
  if (!ts) return 0;
  return ts < 1e12 ? ts * 1000 : ts;
}

export function normalizeImportedProject(raw: unknown): StoryProject {
  if (!raw || typeof raw !== "object") throw new Error("Invalid story file");
  const doc = raw as Record<string, unknown>;
  const inner =
    doc.payload && typeof doc.payload === "object"
      ? (doc.payload as Record<string, unknown>)
      : doc;
  const nodes = Array.isArray(inner.nodes) ? (inner.nodes as StoryProject["nodes"]) : [];
  const edges = Array.isArray(inner.edges) ? (inner.edges as StoryProject["edges"]) : [];
  const updatedAt = toEpochMs(
    (typeof inner.updatedAt === "number" ? inner.updatedAt : undefined) ||
      (typeof doc.updated_at === "number" ? doc.updated_at : undefined)
  ) || Date.now();
  const id =
    (typeof doc.id === "string" && doc.id) ||
    (typeof inner.id === "string" && inner.id) ||
    `import-${updatedAt.toString(36)}`;
  const title =
    (typeof doc.title === "string" && doc.title) ||
    (typeof inner.title === "string" && inner.title) ||
    "Imported story";
  return {
    id,
    title,
    nodes,
    edges,
    template: typeof inner.template === "string" ? inner.template : null,
    updatedAt,
  };
}

export async function readProjectFile(file: File): Promise<StoryProject> {
  const text = await file.text();
  const project = normalizeImportedProject(JSON.parse(text));
  return inlineProjectMedia(project);
}

/** Server-stored media paths from uploadAsset (or legacy exports). */
const STORY_ASSET_URL_RE = /^\/api\/story-canvas\/projects\/[^/]+\/assets\/[^/?#]+$/;

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

/** Resolve blob:, server asset, or same-origin media URLs to embedded data URLs. */
export async function inlineMediaSrc(src: string): Promise<string> {
  if (!src || src.startsWith("data:")) return src;
  const fetchable =
    src.startsWith("blob:") || STORY_ASSET_URL_RE.test(src) || src.startsWith("/api/story-canvas/");
  if (!fetchable) return src;
  try {
    const res = await fetch(src, { credentials: "same-origin" });
    if (!res.ok) return src;
    return await blobToDataUrl(await res.blob());
  } catch {
    return src;
  }
}

/** Embed remote/blob media in node src fields so .story.json is portable. */
export async function inlineProjectMedia(project: StoryProject): Promise<StoryProject> {
  const nodes = await Promise.all(
    (project.nodes || []).map(async (n) => {
      if (!n.src) return n;
      const inlined = await inlineMediaSrc(n.src);
      return inlined === n.src ? n : { ...n, src: inlined };
    })
  );
  return { ...project, nodes };
}

/** Add/import a project into browser history (optional fresh id to avoid overwrite). */
export function importLocalProject(project: StoryProject, opts: { freshId?: boolean } = {}): StoryProject {
  const stamped: StoryProject = {
    ...project,
    id: opts.freshId ? `import-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}` : project.id,
    updatedAt: Date.now(),
  };
  try {
    persistLocal(stamped);
  } catch (err) {
    console.warn("Import succeeded but local history write failed:", err);
    safeLocalStorageSet(LAST_KEY, JSON.stringify(stamped));
    if (stamped.id) safeLocalStorageSet(LAST_ID_KEY, stamped.id);
  }
  return stamped;
}

export function downloadProjectJson(project: StoryProject) {
  const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${(project.title || "story").replace(/[^\w.-]+/g, "-").toLowerCase()}.story.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function portableProjectJsonString(project: StoryProject): Promise<string> {
  const portable = await inlineProjectMedia(project);
  return JSON.stringify(portable, null, 2);
}

export async function downloadPortableProjectJson(project: StoryProject) {
  const portable = await inlineProjectMedia(project);
  downloadProjectJson(portable);
}

/** Pre-load browser history from legacy last snapshot + all server saves. */
export async function preloadLocalCreations(): Promise<number> {
  let count = 0;
  const local = loadLocal();
  if (local?.nodes?.length && loadLocalHistory().length === 0) {
    persistLocal(local);
    count++;
  }
  try {
    const list = await listProjects();
    for (const summary of list) {
      try {
        const full = await loadProject(summary.id);
        const payload = normalizeImportedProject(full.payload || full);
        const existing = getLocalHistoryEntry(summary.id);
        const serverUpdated = toEpochMs(summary.updated_at || payload.updatedAt);
        if (!existing || serverUpdated > existing.updatedAt) {
          upsertHistoryMetadata({
            ...payload,
            id: summary.id,
            title: full.title || payload.title,
            updatedAt: serverUpdated || Date.now(),
          });
          count++;
        }
      } catch {
        /* skip unreadable project */
      }
    }
  } catch {
    /* offline — browser history only */
  }
  return count;
}
