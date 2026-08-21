import type { NodeKind } from "./domain";

export const MAX_VIDEO_BYTES = 100 * 1024 * 1024;

export type ClipboardAsset =
  | { kind: "image"; file: File }
  | { kind: "imageSrc"; src: string }
  | { kind: "video"; file: File }
  | { kind: "text"; body: string; nodeType: NodeKind };

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return !!target.closest('input, textarea, select, [contenteditable="true"]');
}

export function isUrlOnly(text: string): boolean {
  const t = text.trim();
  return /^https?:\/\/\S+$/i.test(t);
}

export function inferTextNodeType(text: string): NodeKind {
  if (isUrlOnly(text)) return "research";
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length >= 2 && (lines.some((l) => /^[-*•]\s/.test(l)) || lines.length >= 3)) {
    return "beat";
  }
  return "text";
}

export function researchBodyFromUrl(url: string): string {
  return `Query: ${url}\n\nClaims (edit me):\n- …\n\nSources:\n- ${url}`;
}

export function extractFromHtml(html: string): { text: string; imageSrcs: string[] } {
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const imageSrcs = [...doc.querySelectorAll("img")]
      .map((img) => img.getAttribute("src") || "")
      .filter((src) => src.length > 0);
    const text = (doc.body.textContent || "").replace(/\u00a0/g, " ").trim();
    return { text, imageSrcs };
  } catch {
    return { text: "", imageSrcs: [] };
  }
}

export function classifyFile(file: File): "image" | "video" | null {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("video/")) return "video";
  const name = file.name.toLowerCase();
  if (/\.(jpe?g|png|gif|webp|svg|bmp|avif)$/.test(name)) return "image";
  if (/\.(mp4|webm|mov|avi|mkv|m4v|ogv)$/.test(name)) return "video";
  return null;
}

export function extractExcalidrawImages(text: string): string[] {
  if (!text.trim().startsWith("{")) return [];
  try {
    const doc = JSON.parse(text) as {
      type?: string;
      elements?: Array<{ type?: string; fileId?: string }>;
      files?: Record<string, { mimeType?: string; dataURL?: string }>;
    };
    if (doc.type !== "excalidraw/clipboard" && doc.type !== "excalidraw") return [];
    const urls: string[] = [];
    const files = doc.files || {};
    for (const el of doc.elements || []) {
      if (el.type !== "image" || !el.fileId) continue;
      const dataUrl = files[el.fileId]?.dataURL;
      if (dataUrl?.startsWith("data:")) urls.push(dataUrl);
    }
    if (!urls.length) {
      for (const f of Object.values(files)) {
        if (f.dataURL?.startsWith("data:")) urls.push(f.dataURL);
      }
    }
    return urls;
  } catch {
    return [];
  }
}

export function isStructuredClipboardJson(text: string): boolean {
  const t = text.trim();
  if (!t.startsWith("{")) return false;
  return t.includes("excalidraw/clipboard") || t.includes('"elements"');
}

export function parseClipboardData(data: DataTransfer | null): ClipboardAsset[] {
  if (!data) return [];

  const assets: ClipboardAsset[] = [];
  const items = [...data.items];
  const imageFiles: File[] = [];
  const videoFiles: File[] = [];
  let plainText = data.getData("text/plain")?.trim() || "";
  const html = data.getData("text/html");

  for (const item of items) {
    if (item.kind !== "file") continue;
    const file = item.getAsFile();
    if (!file) continue;
    const kind = classifyFile(file);
    if (kind === "image") imageFiles.push(file);
    else if (kind === "video") videoFiles.push(file);
  }

  const excalidrawImages = plainText ? extractExcalidrawImages(plainText) : [];
  for (const src of excalidrawImages) {
    assets.push({ kind: "imageSrc", src });
  }

  if (html && imageFiles.length === 0 && excalidrawImages.length === 0) {
    const { text, imageSrcs } = extractFromHtml(html);
    for (const src of imageSrcs) {
      if (src.startsWith("data:") || src.startsWith("blob:") || src.startsWith("http")) {
        assets.push({ kind: "imageSrc", src });
      }
    }
    if (!plainText && text) plainText = text;
  }

  for (const file of imageFiles) assets.push({ kind: "image", file });
  for (const file of videoFiles) assets.push({ kind: "video", file });

  if (plainText && !excalidrawImages.length && !isStructuredClipboardJson(plainText)) {
    const nodeType = inferTextNodeType(plainText);
    const body = nodeType === "research" ? researchBodyFromUrl(plainText) : plainText;
    assets.push({ kind: "text", body, nodeType });
  }

  return assets;
}

export function parseFileList(files: FileList | File[]): ClipboardAsset[] {
  const assets: ClipboardAsset[] = [];
  for (const file of [...files]) {
    const kind = classifyFile(file);
    if (kind === "image") assets.push({ kind: "image", file });
    else if (kind === "video") assets.push({ kind: "video", file });
  }
  return assets;
}
