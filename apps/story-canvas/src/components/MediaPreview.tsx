import { useEffect } from "react";

export function MediaPreview({
  src,
  kind,
  onClose,
  onAnnotate,
  onCopyInstructions,
}: {
  src: string;
  kind: "image" | "video";
  onClose: () => void;
  onAnnotate?: () => void;
  onCopyInstructions?: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="sc-media-preview"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={kind === "video" ? "Video preview" : "Image preview"}
    >
      <div className="sc-media-preview-inner" onClick={(e) => e.stopPropagation()}>
        {kind === "video" ? (
          <video src={src} controls autoPlay playsInline />
        ) : (
          <img src={src} alt="" draggable={false} />
        )}
        {kind === "image" && (onAnnotate || onCopyInstructions) ? (
          <div className="sc-media-preview-actions">
            {onCopyInstructions ? (
              <button
                type="button"
                className="sc-media-preview-action"
                onClick={(e) => {
                  e.stopPropagation();
                  onCopyInstructions();
                }}
              >
                Copy instructions
              </button>
            ) : null}
            {onAnnotate ? (
              <button
                type="button"
                className="sc-media-preview-action primary"
                onClick={(e) => {
                  e.stopPropagation();
                  onAnnotate();
                }}
              >
                Annotate
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      <p className="sc-media-preview-hint">
        {kind === "image" && (onAnnotate || onCopyInstructions)
          ? `${onCopyInstructions ? "Copy instructions · " : ""}${onAnnotate ? "Annotate · " : ""}Esc or click outside to close`
          : "Esc or click outside to close"}
      </p>
    </div>
  );
}
