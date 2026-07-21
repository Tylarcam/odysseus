# Interview Prep — Herdr Session Connect

**When:** n/a (self-coach pack from Odysseus handoff)
**Join:** n/a
**Hosts:** Herdr Docs · Community/GitHub · Agent integrations

## Odysseus Research Library

| Field | Value |
|-------|-------|
| Session ID | `rp-herdr-session-20260720` |
| Report URL | http://localhost:7000/api/research/report/rp-herdr-session-20260720 |
| Audio | Coach script — click **Listen** |
| Orch | `C:\Users\tylar\code\odysseus\research-orch\rp-herdr-session-20260720` |

## Talking points (top 5)

1. Detach (`ctrl+b q`) keeps agents alive; `herdr server stop` does not.
2. Default reattach is bare `herdr`; named isolation is `herdr session attach <name>`.
3. Two remotes: SSH-then-`herdr` vs Unix/macOS `herdr --remote` (clipboard bridge).
4. After restart: layout restores; agent chat only via native resume + current integrations (`herdr integration status`).
5. On Windows beta: no `--remote` / direct attach — SSH to a Unix host and run `herdr` there.
