/**
 * FormFlow completion → handoff prompt generation.
 */

const APP_META = {
  MeritFirst: { docs: 'doc:3c0057ae', approval: 'note:ac66af3b', channel: 'Handshake' },
  Prelim: { docs: 'doc:2a5d262d', approval: 'note:aac4cfed', channel: 'Prelim / Handshake' },
  'Smoosh AI': { docs: 'doc:3d6f6566', approval: 'note:e170d040', channel: 'Handshake → Janice Nam' },
  'mond inc.': { docs: 'doc:bc219dfe', approval: 'note:c35b8388', channel: 'Handshake' },
  Artera: { docs: 'doc:d3a11641', approval: 'note:d4cc53fe', channel: 'Handshake / site' },
  Monid: { docs: 'doc:2cfa899e', approval: 'tracker item 4', channel: 'Founders Inc' },
};

function companyFromAnswer(answer) {
  if (!answer) return null;
  const s = String(answer);
  for (const name of Object.keys(APP_META)) {
    if (s.includes(name.split(' ')[0]) || s.includes(name)) return name;
  }
  return s.split('—')[0].trim();
}

function pickMeta(answer) {
  const co = companyFromAnswer(answer);
  return APP_META[co] || { docs: 'see job tracker 619e4419', approval: 'see APPROVE notes', channel: 'Handshake' };
}

/**
 * @typedef {Object} HandoffOption
 * @property {string} id
 * @property {string} title
 * @property {'human'|'cursor'|'odysseus'|'claude'} target
 * @property {string} body
 * @property {string} [goal]
 * @property {string[]} [nextSteps]
 */

/**
 * @param {{ flowId?: string, questions: object[], answers: object }} session
 * @returns {HandoffOption[]}
 */
export function buildHandoffOptions(session) {
  const { flowId, questions, answers } = session;
  if (flowId === 'gate-breaker') {
    return buildGateBreakerHandoffs(answers);
  }
  return buildGenericHandoffs(questions, answers);
}

function buildGateBreakerHandoffs(answers) {
  const out = [];
  const meta1 = pickMeta(answers.app1);
  const meta2 = pickMeta(answers.app2);
  const app1Co = companyFromAnswer(answers.app1);
  const app2Co = companyFromAnswer(answers.app2);

  const ctx = [
    `Time budget: ${answers.timeBudget || '—'}`,
    `Blocker: ${answers.mainBlocker || '—'}`,
    `Gate ack: ${answers.gateAcknowledged || '—'}`,
    `App #1: ${answers.app1 || '—'}`,
    `App #2: ${answers.app2 || '—'}`,
    `Commit: ${answers.commitWindow || '—'}`,
  ];

  if (answers.app1Action?.includes('Agent reviews') && app1Co) {
    out.push({
      id: 'review-app1',
      title: `Review ${app1Co} package`,
      target: 'cursor',
      goal: `Review ${app1Co} application package before human submit`,
      nextSteps: [
        `Read ${meta1.approval} and ${meta1.docs}`,
        'Flag placeholders or wrong company names',
        'Output READY or FIX LIST (max 3 bullets)',
        `Human submits via ${meta1.channel} — do NOT send`,
      ],
      body:
        `Review ${app1Co} package before I submit.\n\n` +
        `Read approval note ${meta1.approval} and docs ${meta1.docs}.\n` +
        `Flag placeholders, stale dates, wrong company. Output READY or FIX LIST.\n` +
        `Do NOT submit — I send via ${meta1.channel}.`,
    });
  }

  if (answers.app1Action?.includes('re-tailor') && app1Co) {
    out.push({
      id: 'retailor-app1',
      title: `Re-tailor ${app1Co}`,
      target: 'cursor',
      goal: `Re-tailor ${app1Co} cover letter`,
      nextSteps: ['Re-read JD from pipeline', 'Update CL with 2 JD keywords', 'Title APPROVE note clearly'],
      body:
        `Re-tailor ${app1Co} package. Existing: ${meta1.docs}.\n` +
        `Save to doc library. Human submits tomorrow via ${meta1.channel}.`,
    });
  }

  if (answers.app2Action?.includes('Agent reviews') && app2Co && app2Co !== app1Co) {
    out.push({
      id: 'review-app2',
      title: `Review ${app2Co} package`,
      target: 'cursor',
      goal: `Review ${app2Co} package`,
      body: `Same review protocol. Docs: ${meta2.docs}. Approval: ${meta2.approval}. READY or FIX LIST only.`,
    });
  }

  if (answers.hygieneDelegate?.startsWith('Cursor agent')) {
    out.push({
      id: 'hygiene-full',
      title: 'Swarm hygiene pass',
      target: 'cursor',
      goal: 'Clear hygiene blocking job gate clarity',
      nextSteps: [
        'Archive duplicate tracker f7d018e1 (canonical 619e4419)',
        'Title APPROVE notes ff47832c, 1fbc6bfb, aac4cfed, ac66af3b',
        'Append Top 3 to blackboard doc 31a4b230',
      ],
      body:
        'Swarm hygiene pass:\n' +
        '1. Archive note f7d018e1 (canonical 619e4419)\n' +
        '2. Title untitled APPROVE notes (ff47832c, 1fbc6bfb, aac4cfed, ac66af3b)\n' +
        '3. Append today Top 3 to canonical blackboard doc 31a4b230\n' +
        'Use Odysseus API. Confirm each action.',
    });
  } else if (answers.hygieneDelegate?.includes('title 4')) {
    out.push({
      id: 'hygiene-titles',
      title: 'Title 4 APPROVE notes',
      target: 'cursor',
      goal: 'Title untitled Swarm APPROVE notes',
      body:
        'Title notes ff47832c, 1fbc6bfb, aac4cfed, ac66af3b as [Swarm · APPROVE] send: {company} → {channel}.',
    });
  } else if (answers.hygieneDelegate?.includes('Culler')) {
    out.push({
      id: 'hygiene-culler',
      title: 'Culler blackboard append',
      target: 'odysseus',
      goal: 'Log gate breaker session on canonical blackboard',
      body:
        `Append to blackboard 31a4b230:\n` +
        `### ${new Date().toISOString().slice(0, 10)} · Tylar (gate breaker)\n` +
        `- SENSED: Apps picked ${answers.app1 || '—'}, ${answers.app2 || '—'}\n` +
        `- DID: Commit window ${answers.commitWindow || 'TBD'}\n` +
        `- SIGNAL -> Herald: update Fruit Ledger on submit.`,
    });
  }

  if (answers.inboxDelegate?.includes('Cursor')) {
    out.push({
      id: 'inbox-scout',
      title: 'Scout inbox triage',
      target: 'cursor',
      goal: 'Execute Scout checklist note 45a8f2df',
      body:
        'Run Scout inbox triage:\n' +
        '1. GitHub OAuth — CodeRabbit repo scope review\n' +
        '2. Reply James Lin Handshake DM\n' +
        '3. Stage General Translation + Integrated Biosciences if fit ≥3',
    });
  } else if (answers.inboxDelegate?.includes('Scout scheduled')) {
    out.push({
      id: 'inbox-task',
      title: 'Trigger Scout task',
      target: 'odysseus',
      goal: 'Run swarm-t-scout inbox triage',
      body: 'Trigger Scout (swarm-t-scout) now. Append to canonical blackboard 31a4b230.',
    });
  }

  if (answers.morningaiDelegate?.includes('follow-up-email')) {
    out.push({
      id: 'morningai',
      title: 'MorningAI follow-up draft',
      target: 'cursor',
      goal: 'Draft MorningAI follow-up (18d stale)',
      body: 'Use follow-up-email skill. Phone screen ~Jun 22. Draft in note 0463767b. Draft only — I approve send.',
    });
  }

  if (answers.pipelineDelegate?.includes('Trigger Daily')) {
    out.push({
      id: 'pipeline-run',
      title: 'Run job pipeline evaluate',
      target: 'odysseus',
      goal: 'Evaluate normalized job_records',
      body: 'Run Daily Job Pipeline Execution once. Report ready_to_apply records.',
    });
  } else if (answers.pipelineDelegate?.includes('debug')) {
    out.push({
      id: 'pipeline-debug',
      title: 'Debug pipeline evaluate',
      target: 'cursor',
      goal: 'Fix job pipeline evaluate stall',
      body: '14/15 job_records normalized, null match_score. Check run_job_pipeline_once.py and daily task logs.',
    });
  }

  if (app1Co && answers.app1 && !String(answers.app1).includes('None')) {
    const when = answers.commitWindow || 'TBD';
    if (!when.includes('Agent prep only')) {
      out.unshift({
        id: 'human-app1',
        title: `YOU — Submit ${app1Co}`,
        target: 'human',
        goal: `Submit ${app1Co} application`,
        nextSteps: [
          `WHEN: ${when}`,
          `CHANNEL: ${meta1.channel}`,
          `DOCS: ${meta1.docs}`,
          `CHECK: ${meta1.approval}`,
          'AFTER: mark applied in /api/jobs + tracker 619e4419 + Fruit Ledger',
        ],
        body:
          `HUMAN GATE — ${app1Co}\n` +
          `WHEN: ${when}\n` +
          `WHERE: ${meta1.channel}\n` +
          `DOCS: ${meta1.docs}\n` +
          `CHECK: ${meta1.approval}\n` +
          `AFTER SUBMIT: update job tracker 619e4419 + Fruit Ledger.`,
      });
    }
  }

  if (app2Co && answers.app2 && answers.app2Action && !String(answers.app2Action).includes('Skip')) {
    if (app2Co !== app1Co) {
      out.splice(1, 0, {
        id: 'human-app2',
        title: `YOU — Submit ${app2Co} (app #2)`,
        target: 'human',
        goal: `Second submit — clear sporulation gate`,
        body: `Submit ${app2Co} same session if possible. Channel: ${meta2.channel}. Docs: ${meta2.docs}.`,
      });
    }
  }

  if (!out.length) {
    out.push({
      id: 'generic-summary',
      title: 'Session summary',
      target: 'odysseus',
      goal: 'Gate breaker session — no delegations selected',
      body: ctx.join('\n'),
    });
  }

  return out;
}

function buildGenericHandoffs(questions, answers) {
  const summary = questions
    .map((q, i) => {
      const a = answers[q.id];
      const display = Array.isArray(a) ? a.join(', ') : (a != null ? String(a) : '(skipped)');
      return `Q${i + 1}. ${q.label}\nA: ${display}`;
    })
    .join('\n\n');

  return [
    {
      id: 'generic-cursor',
      title: 'Continue in Cursor',
      target: 'cursor',
      goal: 'Execute decisions from FormFlow session',
      nextSteps: ['Read Q&A below', 'Execute human actions first', 'Delegate agent tasks second'],
      body: `FormFlow session complete.\n\n${summary}\n\nExecute human-gate items first. Draft-only for outbound.`,
    },
    {
      id: 'generic-odysseus',
      title: 'Save to Odysseus agent',
      target: 'odysseus',
      goal: 'File FormFlow decisions',
      body: summary,
    },
    {
      id: 'generic-note',
      title: 'Copy answers',
      target: 'human',
      goal: 'Manual follow-up',
      body: summary,
    },
  ];
}

export function handoffTargetLabel(target) {
  const map = { human: 'YOU', cursor: 'Cursor', odysseus: 'Odysseus', claude: 'Claude' };
  return map[target] || target;
}
