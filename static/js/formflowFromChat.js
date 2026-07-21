/**
 * Send chat message text to FormFlow — structured JSON or plain question lists.
 */
import uiModule from './ui.js';

export const FORMFLOW_BTN_ICON = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/><path d="M7 6h.01"/><path d="M12 6h5"/></svg>';

/** Prefer fenced JSON/code when the message wraps structured question data. */
export function extractFormFlowSourceText(raw) {
  const text = (raw || '').trim();
  if (!text) return '';
  const fenced = text.match(/```(?:json)?\s*\n([\s\S]*?)```/i);
  if (fenced) return fenced[1].trim();
  return text;
}

function _stripCodeFences(text) {
  const trimmed = (text || '').trim();
  const fenced = trimmed.match(/```(?:json)?\s*\n?([\s\S]*?)```/i);
  if (fenced) return fenced[1].trim();
  return trimmed.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/i, '').trim();
}

function _coerceQuestionArray(parsed) {
  if (Array.isArray(parsed) && parsed.length) return parsed;
  if (parsed?.questions && Array.isArray(parsed.questions) && parsed.questions.length) {
    return parsed.questions;
  }
  return null;
}

/** Parse a model JSON response into FormFlow question objects, or null. */
export function parseFormFlowModelJson(raw) {
  const text = _stripCodeFences(raw);
  if (!text) return null;

  const tryParse = (candidate) => {
    try {
      return _coerceQuestionArray(JSON.parse(candidate));
    } catch {
      return null;
    }
  };

  let questions = tryParse(text);
  if (questions) return questions;

  const arrayStart = text.indexOf('[');
  const arrayEnd = text.lastIndexOf(']');
  if (arrayStart >= 0 && arrayEnd > arrayStart) {
    questions = tryParse(text.slice(arrayStart, arrayEnd + 1));
    if (questions) return questions;
  }

  const objectStart = text.indexOf('{');
  const objectEnd = text.lastIndexOf('}');
  if (objectStart >= 0 && objectEnd > objectStart) {
    questions = tryParse(text.slice(objectStart, objectEnd + 1));
    if (questions) return questions;
  }

  return null;
}

/** Parse FormFlow question objects from chat text, or null for plain text. */
export function parseQuestionsFromText(raw) {
  const text = extractFormFlowSourceText(raw);
  if (!text) return null;

  if (text.startsWith('[') || text.startsWith('{')) {
    const parsed = parseFormFlowModelJson(text);
    if (parsed) return parsed;
  }

  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const items = lines.filter((l) => /^\d+[.)]\s+/.test(l) || /^[-*•]\s+/.test(l));
  if (items.length >= 2) {
    return items.map((l, i) => ({
      id: `q${i + 1}`,
      type: 'textarea',
      label: l.replace(/^\d+[.)]\s+/, '').replace(/^[-*•]\s+/, '').trim(),
      required: true,
      options: [],
      scaleMin: null,
      scaleMax: null,
      wordLimit: null,
      charLimit: null,
      placeholder: '',
    }));
  }

  return null;
}

/**
 * Open FormFlow with message content — structured questions load directly;
 * otherwise text is pasted and parsed via the FormFlow API.
 * @param {string} raw
 */
export async function sendMessageToFormFlow(raw) {
  const text = extractFormFlowSourceText(raw);
  if (!text) {
    uiModule?.showToast?.('Nothing to send');
    return false;
  }

  const mod = await import('./formflow.js');
  const questions = parseQuestionsFromText(raw);
  if (questions?.length) {
    const ok = mod.openWithQuestions(questions);
    if (ok) uiModule?.showToast?.(`Loaded ${questions.length} question${questions.length === 1 ? '' : 's'} in FormFlow`);
    else uiModule?.showToast?.('Could not load questions');
    return ok;
  }

  await mod.openWithText(text);
  uiModule?.showToast?.('Sent to FormFlow');
  return true;
}
