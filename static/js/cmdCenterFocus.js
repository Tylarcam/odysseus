/**
 * Cmd Center editable-focus helpers.
 * Stubbed after the source file was wiped — keeps cmdCenter.js importable.
 */

let _saved = null;

export function captureCmdEditableFocus(root = document) {
  const el = root.activeElement;
  if (!el) {
    _saved = null;
    return null;
  }
  const tag = (el.tagName || '').toLowerCase();
  const isEditable =
    tag === 'input' ||
    tag === 'textarea' ||
    el.isContentEditable === true;
  if (!isEditable) {
    _saved = null;
    return null;
  }
  _saved = {
    el,
    selectionStart: typeof el.selectionStart === 'number' ? el.selectionStart : null,
    selectionEnd: typeof el.selectionEnd === 'number' ? el.selectionEnd : null,
  };
  return _saved;
}

export function cmdEditableOwnsFocus(root = document) {
  const el = root.activeElement;
  if (!el) return false;
  const tag = (el.tagName || '').toLowerCase();
  return tag === 'input' || tag === 'textarea' || el.isContentEditable === true;
}

export function restoreCmdEditableFocus() {
  if (!_saved?.el) return false;
  try {
    _saved.el.focus?.();
    if (
      typeof _saved.selectionStart === 'number' &&
      typeof _saved.selectionEnd === 'number' &&
      typeof _saved.el.setSelectionRange === 'function'
    ) {
      _saved.el.setSelectionRange(_saved.selectionStart, _saved.selectionEnd);
    }
    return true;
  } catch {
    return false;
  } finally {
    _saved = null;
  }
}

export default {
  captureCmdEditableFocus,
  cmdEditableOwnsFocus,
  restoreCmdEditableFocus,
};
