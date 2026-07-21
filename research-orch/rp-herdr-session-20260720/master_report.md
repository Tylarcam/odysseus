# Herdr — Session connect interview prep

**Question:** How do you connect to a Herdr session (local reattach, named sessions, remote, direct attach) and what survives detach vs server stop/restart?
**Engines:** A1 last30days · A2 Firecrawl/WebFetch · A3 Perplexity
**Date:** 2026-07-20
**Interviewers / hosts:** Herdr Docs · Community/GitHub · Agent integrations (Claude/Codex/Cursor/OpenCode)

---

## Coach briefing (read first)

Show up knowing **detach ≠ stop**. Detach (`ctrl+b q`) keeps agents alive; `herdr server stop` kills pane processes and only restores layout (+ optional native agent `--resume`). Lead with the default path: run `herdr` from the project dir to attach the background session — no socket babysitting ([quick-start](https://herdr.dev/docs/quick-start/)). Cite three facts: (1) named sessions via `herdr session attach <name>` are independent servers ([persistence-remote](https://herdr.dev/docs/persistence-remote/)); (2) two remote paths — SSH-then-`herdr` vs Unix/macOS `herdr --remote` thin client ([how-to-work](https://herdr.dev/docs/how-to-work/)); (3) Windows beta cannot use `--remote` or direct terminal attach — SSH into a Unix host and run `herdr` there ([windows-beta](https://herdr.dev/docs/windows-beta/)). STAR to lead: multi-agent terminal chaos → Herdr as the single reattach surface. Risk to avoid: claiming “sessions survive restarts” without distinguishing snapshot layout vs live processes vs `--handoff`.

---

## Org / program

Herdr ([herdr.dev](https://herdr.dev/)) is an agent-aware terminal multiplexer: background server owns PTYs; clients attach/detach. Stable on Linux/macOS; native Windows is ConPTY preview beta. No account/telemetry. Positioned between tmux/Zellij (persistence, weak agent semantics) and desktop agent apps (agent-aware, often machine-bound). Recent pulse: GitHub trending, HN [#48714802](https://news.ycombinator.com/item?id=48714802), stable **v0.7.4** (2026-07-15). AWS Labs CLI Agent Orchestrator lists Herdr as an experimental backend. No clear public “Herdr is hiring” signal in-window — this pack is product/howto coaching, not org interview dossiers.

---

## Interviewer dossiers

### Herdr Docs — official product narrative
- **Owns / cares about:** Correct mental model for connect modes and restore matrix
- **Likely questions:** Which command for which topology? What survives stop?
- **Evidence to cite:** Restore table on [session-state](https://herdr.dev/docs/session-state/); connect playbook on [persistence-remote](https://herdr.dev/docs/persistence-remote/)
- **STAR to lead:** “I treat detach as pause and stop as kill — then verify integrations after restore”

### Herdr Community / GitHub — friction host
- **Owns / cares about:** Windows parity, `--remote` discovery/auth, resume trust
- **Likely questions:** Why does `--remote` fail when SSH+`herdr` works? Can Windows do one-command attach?
- **Evidence:** [#1042](https://github.com/ogulcancelik/herdr/issues/1042) Windows `--remote` tracking; [#1201](https://github.com/ogulcancelik/herdr/issues/1201) PATH/shell discovery; [#1544](https://github.com/ogulcancelik/herdr/issues/1544) SSH+ConPTY input drop; [#888](https://github.com/ogulcancelik/herdr/issues/888) SSH password reuse
- **STAR to lead:** Diagnose attach failures with plain `ssh` first, then choose SSH-then-herdr vs `--remote`

### Coding-agent integrations — resume host
- **Owns / cares about:** Native session restore after Herdr server restart
- **Likely questions:** Will Claude/Codex come back after reboot?
- **Evidence:** Default-on resume; Claude Code integration ≥`6` → `claude --resume`; Codex ≥`5` → `codex resume`; Cursor Agent CLI ≥`1` → `cursor-agent --resume`; check `herdr integration status` ([session-state](https://herdr.dev/docs/session-state/))
- **STAR to lead:** “After stop/restart I run integration status and expect stale refs to become shells — not magic”

---

## STAR × interviewer matrix

| STAR | Best for | Hook line |
|------|----------|-----------|
| Multi-agent terminal herd (Claude + Codex + Cursor) | Docs / Community | “One reattach command instead of six forgotten windows” |
| Detach overnight, reattach morning | Docs | “`ctrl+b q` kept the processes; stop would have killed them” |
| Remote from laptop / phone via SSH | Community | “Phone SSH → `herdr` is the supported path; Windows can’t `--remote` yet” |
| Post-restart resume verification | Integrations | “Layout came back; I confirmed agent session ids before trusting chat” |

---

## Likely questions + talking points

### From them
1. How do I reconnect after closing the terminal? → `herdr` (default) or `herdr session attach <name>`.
2. How do I work on a remote box? → Prefer `herdr --remote` on Unix/macOS; from Windows or phone: `ssh` then `herdr`.
3. Do agents survive a reboot / `server stop`? → Processes no; layout yes; conversation only via native resume + current integrations.
4. What’s direct attach for? → One pane (`agent attach` / `terminal attach`), Unix-only on Windows beta.
5. What’s `--handoff`? → Experimental live transfer to a *new* server binary — not the same as stop/start.

### Ask them (or ask yourself as coach)
1. Which session name should be canonical for Odysseus vs job-ops work?
2. Are my Herdr integrations at the min versions for Claude/Codex/Cursor resume?
3. For this Windows host, which remote Linux box is the `--remote`/SSH target of record?

---

## Risks, gaps, open questions

- Viral posts under-explain **detach vs server restart** — easy to overclaim survival.
- Native resume can relaunch the wrong session if refs are stale ([#619](https://github.com/ogulcancelik/herdr/issues/619), [#943](https://github.com/ogulcancelik/herdr/issues/943)).
- Windows: no `--remote`, no direct attach, no live handoff; SSH+ConPTY input bugs reported ([#1544](https://github.com/ogulcancelik/herdr/issues/1544)).
- Handoff Notes had no company/role/JD/interviewers — pack framed as self-coach product prep for “how to connect to a session.”
- No named Herdr maintainers on marketing pages for traditional interviewer dossiers.

---

## Session connect playbook (commands)

| Mode | Command | When |
|------|---------|------|
| Default local | `herdr` | Day-to-day attach/reattach |
| Named session | `herdr session attach work` / `herdr --session work` | Isolated projects |
| Detach | `ctrl+b q` | Keep processes alive |
| Stop | `herdr server stop` / `herdr session stop <name>` | Kill panes |
| SSH remote | `ssh host` → `herdr` | Windows, phone, simplest remote |
| Thin remote | `herdr --remote workbox` [--session agents] | Unix/macOS client + clipboard bridge |
| Direct | `herdr agent attach <name>` / `herdr terminal attach <id>` | One pane (not Windows beta) |
| Escape | `herdr --no-session` | No server/client split |

---

## Appendix — research legs

### A1 Recency

See `a1_last30days.md` (GitHub issues #1042/#1201/#1544, HN #48714802, v0.7.4).

### A2 Authority

See `a2_firecrawl.md` (official restore matrix, connect playbook, Windows unsupported table).

### A3 Perplexity

See `a3_perplexity.md` (engine `perplexity_agent_direct`; playbook + resume caveats).
