# Research brief — Interview prep / Herdr session connect

| Field | Value |
|-------|-------|
| Topic / question | Prep for using **Herdr** (terminal multiplexer for coding agents): how to **connect / attach / resume a session** locally, remotely, and after restart |
| Audience / use | interview prep (coach pack) + practical howto for Tylar's agent stack |
| Category | `interview_prep` |
| Session id | `rp-herdr-session-20260720` |
| Owner | `tylarcam` |
| Interview datetime | n/a (self-coach pack from handoff notes) |
| Join link | n/a |
| JD path / URL | https://herdr.dev/docs/persistence-remote/ · https://herdr.dev/docs/session-state/ · https://herdr.dev/docs/quick-start/ |
| Resume / STARs | Multi-agent terminal chaos (Claude/Codex/Cursor); Odysseus handoff relay; Windows 10 agent host |

## Interviewers (authority / "hosts" for this pack)

| Name | Title / team | Focus to research |
|------|--------------|-------------------|
| Herdr Docs | Official product docs | Persist, detach/reattach, named sessions, remote, native agent restore |
| Herdr Community / GitHub | OSS maintainers + users | Last-30-day friction on attach/remote/Windows |
| Coding-agent integrations | Claude / Codex / Cursor / OpenCode etc. | Which agents resume via `herdr` after server restart |

## Must-answer questions

1. What is Herdr and what problem does session attach solve for multi-agent terminal work?
2. How do you connect to a session in each mode: default reattach, named session, SSH / `--remote`, direct agent/terminal attach?
3. What survives detach vs server restart vs update `--handoff` (layout, processes, agent conversation)?
4. How does native agent session restore work, and which agents/versions support resume?
5. What Windows-beta limits matter for this host (direct attach, remote from Windows)?
6. What are the sharp pitfalls / claims to avoid when coaching someone to "just reconnect"?

## Authority URLs (A2 priority)

- https://herdr.dev/
- https://herdr.dev/docs/quick-start/
- https://herdr.dev/docs/persistence-remote/
- https://herdr.dev/docs/session-state/
- https://herdr.dev/docs/how-to-work/
- https://herdr.dev/docs/cli-reference/
- https://herdr.dev/docs/windows-beta/
- https://herdr.dev/docs/agents/
- Local mirror: `C:\Users\tylar\.agents\skills\herdr\website\src\content\docs\` (session-state.mdx, persistence-remote.mdx, quick-start.mdx)
- Chase AI / community transcript: `C:\Users\tylar\code\odysseus\data\handoff-inbox\cursor\chase-ai-nek8ydl0vlk-transcript.txt`

## Recency keywords (A1)

Herdr, herdr.dev, herdr session attach, herdr --remote, terminal multiplexer coding agents, Claude Code Codex multiplexer, Windows Herdr beta

## Synthesis angle (A3)

Reconcile official session-connect docs with last-30-day user friction (especially Windows + remote). Produce a coachable playbook: when to run bare `herdr`, when `herdr session attach <name>`, when `herdr --remote`, when direct `agent/terminal attach`, and what NOT to expect after `herdr server stop`.
