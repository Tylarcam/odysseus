/**
 * Built-in FormFlow decision flows — one question at a time, handoffs on complete.
 */

export const GATE_BREAKER_FLOW = {
  id: 'gate-breaker',
  title: 'Gate Breaker',
  subtitle: 'Break the sporulation gate — decide apps, delegate the rest',
  phases: [
    { id: 'orient', label: '1 · Orient' },
    { id: 'acknowledge', label: '2 · Acknowledge' },
    { id: 'decide', label: '3 · Decide apps' },
    { id: 'delegate', label: '4 · Delegate' },
    { id: 'commit', label: '5 · Commit' },
  ],
  questions: [
    {
      id: 'timeBudget',
      type: 'choice',
      phase: 'orient',
      label: 'How much focused time do you have for the job gate today?',
      hint: '15 min = one submit. 60 min = two submits + delegate hygiene.',
      required: true,
      options: [
        '15 minutes — submit 1 package only',
        '30 minutes — submit 1 + quick inbox',
        '1 hour — submit 2 + delegate rest',
        '2+ hours — full gate break + hygiene',
      ],
    },
    {
      id: 'mainBlocker',
      type: 'choice',
      phase: 'orient',
      label: 'What is actually stopping you from submitting?',
      required: true,
      options: [
        'Decision fatigue — too many leads',
        'Package doubt — want review first',
        'Platform friction — Handshake annoyance',
        'Other work won — building ate the day',
        'Low energy — need minimum action',
      ],
    },
    {
      id: 'gateAcknowledged',
      type: 'choice',
      phase: 'acknowledge',
      label: 'Confirm: zero applications sent since Jul 3 despite 6+ ready packages?',
      hint: 'Breaking the gate = YOU click submit. Agents cannot.',
      required: true,
      options: [
        'Yes — this is urgent',
        "Yes — I'll submit tonight",
        'I submitted some manually — reconcile tracker',
        'Defer gate to later this week',
      ],
    },
    {
      id: 'app1',
      type: 'choice',
      phase: 'decide',
      label: 'Pick application #1 (highest priority send):',
      required: true,
      showIf: { field: 'gateAcknowledged', notIncludes: 'Defer' },
      options: [
        'MeritFirst — AI Engineer (5/5, 17d stale)',
        'Prelim — SWE Product (5/5, 9d stale)',
        'Smoosh AI — CTO (5/5, recruiter DM)',
        'mond inc. — Founding Eng (4/5)',
        'Artera — Automation Eng (5/5)',
        'Monid — Founding Eng (4/5)',
        'None tonight — defer gate',
      ],
    },
    {
      id: 'app2',
      type: 'choice',
      phase: 'decide',
      label: 'Pick application #2 (second send to clear sporulation gate):',
      required: true,
      showIf: { field: 'app1', notIncludes: 'None', andNotField: 'timeBudget', andNotIncludes: '15 minutes' },
      options: [
        'MeritFirst — AI Engineer (5/5, 17d stale)',
        'Prelim — SWE Product (5/5, 9d stale)',
        'Smoosh AI — CTO (5/5, recruiter DM)',
        'mond inc. — Founding Eng (4/5)',
        'Artera — Automation Eng (5/5)',
        'Monid — Founding Eng (4/5)',
      ],
    },
    {
      id: 'app1Action',
      type: 'choice',
      phase: 'decide',
      label: 'What happens with app #1 package?',
      required: true,
      showIf: { field: 'app1', notIncludes: 'None' },
      options: [
        'I submit myself — package is good enough',
        'I review 5 min then submit',
        'Agent reviews first — I submit after',
        'Agent re-tailors — I submit tomorrow',
        'Skip this app',
      ],
    },
    {
      id: 'app2Action',
      type: 'choice',
      phase: 'decide',
      label: 'What happens with app #2 package?',
      required: true,
      showIf: { field: 'app2', answered: true, notSameAs: 'app1' },
      options: [
        'I submit myself — package is good enough',
        'I review 5 min then submit',
        'Agent reviews first — I submit after',
        'Skip second app tonight',
      ],
    },
    {
      id: 'hygieneDelegate',
      type: 'choice',
      phase: 'delegate',
      label: 'Delegate hygiene blocking clarity?',
      hint: 'Dup tracker f7d018e1, 4 untitled APPROVE notes.',
      required: true,
      options: [
        'Cursor agent — full hygiene pass',
        'Cursor — title 4 APPROVE notes only',
        'Odysseus Culler — append blackboard',
        "I'll do manually later",
        'Skip — not blocking sends',
      ],
    },
    {
      id: 'inboxDelegate',
      type: 'choice',
      phase: 'delegate',
      label: 'Delegate inbox triage (8 unread)?',
      required: true,
      options: [
        'Odysseus Scout scheduled task',
        'Cursor — run Scout checklist now',
        "I'll handle security only (GitHub OAuth)",
        'Skip inbox today',
      ],
    },
    {
      id: 'morningaiDelegate',
      type: 'choice',
      phase: 'delegate',
      label: 'Delegate MorningAI follow-up (18d stale)?',
      required: true,
      options: [
        'Cursor follow-up-email skill',
        'Odysseus agent — draft only',
        "I'll send follow-up myself tonight",
        'Defer to Monday',
      ],
    },
    {
      id: 'pipelineDelegate',
      type: 'choice',
      phase: 'delegate',
      label: 'Delegate pipeline evaluate (14/15 stuck at normalized)?',
      required: true,
      options: [
        'Trigger Daily Job Pipeline task now',
        "Cursor — debug why evaluate didn't run",
        "Skip — doesn't block manual submit",
      ],
    },
    {
      id: 'commitWindow',
      type: 'choice',
      phase: 'commit',
      label: 'When do you personally click Submit on app #1?',
      hint: 'Only your click counts as fruit.',
      required: true,
      showIf: { field: 'app1', notIncludes: 'None' },
      options: [
        'Next 30 minutes',
        'Tonight before bed',
        'Tomorrow morning',
        'This week',
        'Agent prep only — no send today',
      ],
    },
  ],
};

export const BUILTIN_FLOWS = [GATE_BREAKER_FLOW];

export function getBuiltinFlow(id) {
  return BUILTIN_FLOWS.find((f) => f.id === id) || null;
}

/** Evaluate showIf against current answers. */
export function questionVisible(q, answers, allQuestions) {
  const cond = q.showIf;
  if (!cond) return true;

  const val = answers[cond.field];
  const str = val != null ? String(val) : '';

  if (cond.notIncludes && str.includes(cond.notIncludes)) return false;
  if (cond.includes && !str.includes(cond.includes)) return false;
  if (cond.answered === true && !str) return false;

  if (cond.andNotField) {
    const other = answers[cond.andNotField];
    const otherStr = other != null ? String(other) : '';
    if (cond.andNotIncludes && otherStr.includes(cond.andNotIncludes)) return false;
  }

  if (cond.notSameAs) {
    const other = answers[cond.notSameAs];
    if (other != null && val != null && String(other) === String(val)) return false;
  }

  return true;
}

export function visibleQuestions(flowOrQuestions, answers) {
  const list = Array.isArray(flowOrQuestions) ? flowOrQuestions : flowOrQuestions?.questions || [];
  return list.filter((q) => questionVisible(q, answers, list));
}
