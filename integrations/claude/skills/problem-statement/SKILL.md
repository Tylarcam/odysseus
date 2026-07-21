---
name: problem-statement
description: >-
  Draft ultra-concise problem statements (default 100 characters) from bugs,
  integration failures, or feature gaps. Use when the user asks for a problem
  statement, one-liner for a ticket, issue summary, handoff headline, or
  "describe the problem in N chars".
---

# Concise Problem Statement

Produce **one sentence** problem statements with a strict character budget. Optimized for tickets, handoffs, PR descriptions, and agent briefs.

## When to use

| User says | Action |
|-----------|--------|
| "problem statement" | Draft at default 100 chars |
| "problem statement (N chars)" | Use N as hard max |
| "one-liner for this bug" | Same workflow |
| "summarize what's broken" | Same, symptom-first |

## Workflow

1. **Gather facts** (from conversation, logs, code, or user):
   - System/feature affected
   - Observable failure (error text, wrong behavior)
   - User impact
   - Optional: known gap (missing retry, timeout, sync, config)

2. **Do not** lead with solutions unless the user asked for "problem + fix". Prefer **symptom + impact** or **symptom + missing capability**.

3. **Draft 1 recommended** statement at or under the char limit.

4. **Draft 2 alternates** with different emphasis (user impact vs technical root vs scope).

5. **Count characters** including spaces and punctuation. Report count for each option.

6. **Validate**:
   - [ ] Single sentence (no semicolon chains unless user allows)
   - [ ] Under char limit
   - [ ] Names the system/feature
   - [ ] States what's wrong or missing
   - [ ] No vague words ("issues", "problems") without specifics

## Formula (pick one)

**Failure-led:** `[System] [feature] fails with [symptom]; [impact or missing capability].`

**Gap-led:** `[System] lacks [capability]; [symptom or user consequence].`

**Misconfig-led:** `[Wrong path] runs instead of [intended path]; [symptom].`

## Output format

```markdown
**Recommended (N chars):**
`<statement>`

**Alternates:**
- `<statement>` (N)
- `<statement>` (N)
```

If over limit, trim in this order: adjectives → parentheticals → "needs X and Y" → shorten product name.

## Defaults

| Setting | Default |
|---------|---------|
| Char limit | 100 |
| Voice | Active, present tense |
| Punctuation | One period at end; no quotes in the statement unless error text |

## Examples

**Input:** Perplexity research in Odysseus fails with "server disconnected"; CLI retry works; panel has no retry, 300s timeout, engine not synced with settings.

**Recommended (100 chars):**
`Odysseus Perplexity research drops with server disconnected errors; needs retry and longer timeouts.`

**Alternates:**
- `Perplexity Agent jobs in Odysseus fail mid-request; no auto-retry, 300s cap, panel engine out of sync.` (97)
- `Deep Research + Perplexity: API disconnects abort runs; users can't tell if chat or Agent ran.` (88)

---

**Input:** User set Perplexity in Admin Settings but panel still used local LLM + DuckDuckGo; report empty.

**Recommended (99 chars):**
`Deep Research ignores Admin Perplexity setting when panel engine is Standard; runs local LLM instead.`

## Anti-patterns

- ❌ "There are some issues with the integration" (no specifics)
- ❌ 200-char paragraph when limit is 100
- ❌ Solution-only: "Add retry logic" (not a problem statement)
- ❌ Multiple problems in one sentence unless user allows a compound statement
