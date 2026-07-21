# A2 Authority Digest

Firecrawl: unavailable (no MCP tools matched). Sources: WebFetch of herdr.dev + local MDX mirrors under `~/.agents/skills/herdr/website/src/content/docs/` and `SKILL.md`.

### Org / product

Herdr (herdr.dev) is an agent-aware terminal multiplexer: a binary, not an Electron app. Background server owns real PTYs; clients attach/detach. Stable on Linux/macOS; native Windows is preview beta (ConPTY). No account, no telemetry. Positioned between tmux/Zellij (persistence, no agent semantics) and desktop agent apps (agent-aware, machine-bound). Integrations add richer state + native session resume for many coding agents (Claude Code, Codex, Cursor Agent CLI, OpenCode, Pi, etc.).

### People

No named maintainers/org people on scraped marketing/docs pages. Community walkthroughs cited on homepage: Jilles, DevOps Toolbox, Better Stack. Local skill path: `C:\Users\tylar\.agents\skills\herdr\`. Transcript excerpt (chase-ai): community video framing Herdr as multi-agent multiplexer for Claude/Codex/OpenCode with organization + detach survival.

### Session connect playbook (commands)

**Local (full UI)**
- `herdr` — start or attach default background session
- `herdr --session work` or `herdr session attach work` — named session
- Detach: `ctrl+b q` (or close terminal); reattach: `herdr` again
- Stop everything: `herdr server stop` / `herdr session stop <name>`

**SSH then herdr (tmux-style remote)**
```
ssh you@server
herdr
```
Server + panes run on remote. Phone SSH clients use this path. No local desktop clipboard bridge beyond normal text paste.

**Thin client remote (Unix/macOS local binary)**
```
herdr --remote workbox
herdr --remote ssh://you@server:2222
herdr --remote workbox --session agents
herdr --remote workbox --remote-keybindings server   # use remote keybinds
herdr --remote workbox --handoff                     # experimental live handoff
```
Local Herdr is thin client over SSH; can auto-install matching remote binary; bridges local image clipboard. Default keybindings = local snapshot at attach time.

**Direct attach (one terminal, not full UI) — Unix-only in Windows beta**
```
herdr agent attach reviewer
herdr agent attach reviewer --takeover
herdr terminal attach term_abc123 [--takeover]
herdr terminal session observe w1:p1 --cols 120 --rows 40
herdr terminal session control w1:p1 --takeover --cols 120 --rows 40
```
Detach: `ctrl+b q`. Literal prefix: `ctrl+b ctrl+b`.

**Escape hatch:** `herdr --no-session` (no server/client split).

**Inside Herdr (skill):** require `HERDR_ENV=1`; control via `herdr pane|workspace|tab|agent|session|wait` JSON CLI — do not run bare `herdr` for discovery (it attaches TUI).

### Policies / docs (restore matrix)

| Case | Processes keep running | Layout returns | Recent screen | Agent conversation |
| --- | --- | --- | --- | --- |
| Detach / reattach | Yes | Yes | Yes (live terminal) | Yes (process never stopped) |
| Server restart | No | Yes (snapshot: workspaces/tabs/panes/cwd/layout/focus) | Only if `[experimental] pane_history = true` | Only via native agent session restore |
| Update without `--handoff` | Compatible servers may keep running; else restart | Yes after restart | Pane history only | Native restore only |
| Update / remote with `--handoff` | Best effort; panes transfer to new server | Yes | Yes if handoff succeeds | Yes if processes kept alive |

Notes:
- Snapshot restore ≠ live processes; non-restorable panes become new shells in saved cwd.
- Pane history off by default (secrets in `session-history.json`); treat session dir like terminal history.
- Native agent restore: default on (`[session] resume_agents_on_restore = false` to disable). Needs official integration-reported session refs + min integration versions. After client attaches (size/theme), Herdr resumes eligible agent panes across workspaces without per-pane focus. Bad/stale refs → plain shell. When native restore applies, pane history is skipped for that pane.
- Live handoff: experimental, opt-in (`herdr update --handoff`, `herdr --remote … --handoff`). Not for Homebrew/mise/Nix `herdr update`. Distinct from snapshot/history/native resume.

**Native resume commands (integration mins):** Pi `2` `pi --session`; OMP `3` `omp --resume=`; Claude Code `6` `claude --resume`; Codex `5` `codex resume`; Cursor Agent CLI `1` `cursor-agent --resume`; Copilot `2` `copilot --resume=`; Devin `2`; Droid `2`; Kimi `3` `kimi --session`; Qoder `2`; OpenCode `5` `opencode --session`; Kilo `1`; Hermes `2`; MastraCode `1` `mastracode --thread`. Check: `herdr integration status`.

**Windows beta attach/remote limits**
- Supported: local persistent sessions, ConPTY panes, WT/PowerShell attach, agents/integrations, pane screen history (beta).
- Unsupported: direct terminal attach; `herdr --remote` from Windows binary; live server handoff; Unix FD handoff; remote clipboard image bridge.
- Remote from Windows: `ssh you@server` then `herdr` on the host (not native `--remote`).
- After Windows update: restart sessions; live handoff is Unix-only.

### Source excerpts (short quotes + URLs)

> "Herdr launches or attaches to your default background session. … If you detach, agents keep running." — https://herdr.dev/docs/quick-start/

> "Detach the client with `ctrl+b q`; panes and agents keep running. Reattach by running `herdr` again." — https://herdr.dev/docs/persistence-remote/

> "Native Windows `herdr --remote` is not part of the Windows beta. From Windows, SSH into the server and run `herdr` there." — https://herdr.dev/docs/persistence-remote/ / https://herdr.dev/docs/windows-beta/

> "Direct terminal attach is Unix-only in the Windows beta." — https://herdr.dev/docs/persistence-remote/

> "Herdr only resumes panes that reported a native session reference through a current official Herdr integration." — https://herdr.dev/docs/session-state/

> "Live handoff is experimental and opt-in … Plain `herdr update` and plain `herdr --remote workbox` use the normal restart/stop flow by default." — https://herdr.dev/docs/session-state/

> "Use `ssh you@server` then `herdr` when you want Herdr to behave like tmux … Use `herdr --remote <target>` when you want a local thin client … including local clipboard image paste bridging." — https://herdr.dev/docs/how-to-work/

> "Live server handoff | unsupported" (Windows beta table) — https://herdr.dev/docs/windows-beta/

Local mirrors confirmed identical restore matrix / Windows unsupported table: `session-state.mdx`, `persistence-remote.mdx`, `windows-beta.mdx`, `quick-start.mdx`. Skill: control only when `HERDR_ENV=1` — `C:\Users\tylar\.agents\skills\herdr\SKILL.md`.
