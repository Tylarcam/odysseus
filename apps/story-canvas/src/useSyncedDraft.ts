import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Local draft for a controlled parent string.
 * Typing updates local state immediately; commits debounce (and flush on blur/unmount).
 * Parent updates are ignored while dirty so they cannot clobber the caret mid-keystroke.
 */
export function useSyncedDraft(
  externalValue: string,
  onCommit: (value: string) => void,
  debounceMs = 300
) {
  const [draft, setDraft] = useState(externalValue);
  const draftRef = useRef(draft);
  const dirtyRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const onCommitRef = useRef(onCommit);

  draftRef.current = draft;
  onCommitRef.current = onCommit;

  useEffect(() => {
    if (dirtyRef.current) return;
    setDraft(externalValue);
  }, [externalValue]);

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const commitNow = useCallback(
    (value: string) => {
      clearTimer();
      dirtyRef.current = false;
      onCommitRef.current(value);
    },
    [clearTimer]
  );

  const flush = useCallback(() => {
    if (!dirtyRef.current) {
      clearTimer();
      return;
    }
    commitNow(draftRef.current);
  }, [clearTimer, commitNow]);

  const setDraftValue = useCallback(
    (value: string) => {
      dirtyRef.current = true;
      setDraft(value);
      clearTimer();
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        commitNow(value);
      }, debounceMs);
    },
    [clearTimer, commitNow, debounceMs]
  );

  useEffect(() => {
    return () => {
      clearTimer();
      if (dirtyRef.current) {
        onCommitRef.current(draftRef.current);
      }
    };
  }, [clearTimer]);

  return { draft, setDraftValue, flush, isDirty: () => dirtyRef.current };
}
