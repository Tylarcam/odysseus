/** Capture / restore editable caret across context-menu open → dismiss. */

export type EditableFocusSnap = {
  el: HTMLInputElement | HTMLTextAreaElement;
  start: number | null;
  end: number | null;
};

export function captureEditableFocus(): EditableFocusSnap | null {
  const active = document.activeElement;
  if (!(active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement)) {
    return null;
  }
  return {
    el: active,
    start: typeof active.selectionStart === "number" ? active.selectionStart : null,
    end: typeof active.selectionEnd === "number" ? active.selectionEnd : null,
  };
}

export function restoreEditableFocus(snap: EditableFocusSnap | null): void {
  if (!snap?.el?.isConnected) return;
  requestAnimationFrame(() => {
    if (!snap.el.isConnected) return;
    try {
      snap.el.focus({ preventScroll: true });
      if (snap.start != null && typeof snap.el.setSelectionRange === "function") {
        const end = snap.end != null ? snap.end : snap.start;
        snap.el.setSelectionRange(snap.start, end);
      }
    } catch {
      /* ignore focus failures (detached / hidden) */
    }
  });
}
