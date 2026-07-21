## A3 Perplexity Digest

**Engine:** `perplexity_agent_direct` (Odysseus `POST /api/research/start` → 403 scope; direct Perplexity Agent `pro-search`)  
**Topic:** Herdr session-connect playbook (interview_prep coach pack)  
**Raw:** `a3_perplexity_raw.json`

### Findings (numbered, cited)

1. **Bare `herdr` = default local attach.** From a project directory, `herdr` starts or attaches to the default background session automatically (no socket management). Detach with `ctrl+b q`; panes/agents keep running; re-run `herdr` to reattach. Use this for day-to-day local work. ([How to work with Herdr](https://herdr.dev/docs/how-to-work/); [CLI reference](https://herdr.dev/docs/cli-reference/))

2. **`herdr session attach <name>` (or `herdr --session <name>`) = independent session servers.** Named sessions get their own panes, tabs, workspaces, sockets, and runtime state while sharing global config. Prefer when you need isolation (`work` vs `side-project`) rather than one crowded default session. Manage with `herdr session list|stop|delete`. Remotely: `herdr --remote workbox --session agents`. ([Persistence and remote access](https://herdr.dev/docs/persistence-remote/); [CLI reference](https://herdr.dev/docs/cli-reference/))

3. **Two remote paths — do not conflate them.** (a) SSH then run `herdr` on the host: tmux-style; ideal for phone/tablet SSH clients; no local clipboard-image bridge. (b) `herdr --remote <host|ssh://…>`: local thin client over SSH; can bridge local image clipboard; defaults to local keybindings (`--remote-keybindings server` to use remote). Community guides (Tecmint) correctly echo `--remote` for VPS workflows. ([How to work](https://herdr.dev/docs/how-to-work/); [Persistence](https://herdr.dev/docs/persistence-remote/); [Tecmint](https://www.tecmint.com/herdr-run-ai-coding-agents-in-linux-terminal/))

4. **Direct `agent` / `terminal` attach = one pane, not the full TUI.** `herdr agent attach <target>` and `herdr terminal attach <terminal_id>` stream one server-owned terminal into your current terminal; detach with `ctrl+b q`; only one writable owner (`--takeover` to steal). Use for focused interaction or bridges; use `terminal session observe|control` for JSON frame bridges. Full workspace UI remains `herdr` / `session attach`. ([Persistence](https://herdr.dev/docs/persistence-remote/); [CLI reference](https://herdr.dev/docs/cli-reference/))

5. **Survival matrix (official) — what NOT to expect after `herdr server stop`.**

| Case | Processes keep running | Layout returns | Recent screen | Agent conversation |
| --- | --- | --- | --- | --- |
| Detach / reattach | Yes | Yes | Live terminal | Yes (process never stopped) |
| Server stop → later start | **No** | Yes (snapshot shape) | Only if pane history on | Only via native agent resume |
| Update / remote without `--handoff` | May stop/restart | Yes after restart | History-dependent | Native resume only |
| Update / remote with `--handoff` | Best-effort keep-alive | Yes | Live if handoff works | Yes if processes kept |

After `herdr server stop`: do **not** expect shells, servers, tests, or arbitrary processes to still be running. Expect restored workspace/tab/pane/cwd layout; agent chat resume only if native restore applies; screen scrollback only if `[experimental] pane_history = true`. Live handoff is a different path (keep processes across server *replacement*), not what stop does. ([Session state and restore](https://herdr.dev/docs/session-state/); [Persistence](https://herdr.dev/docs/persistence-remote/))

6. **Native agent resume is default, not magic for every pane.** `[session] resume_agents_on_restore = true` by default. Herdr restarts eligible agent panes using integration-reported session refs after a client attaches (size/theme). Minimum integration versions include Claude Code `6` (`claude --resume`), Codex `5` (`codex resume`), Cursor Agent CLI `1` (`cursor-agent --resume`), Copilot CLI `2`, OpenCode `5`, Hermes `2`, etc. Check with `herdr integration status`; reinstall outdated integrations. Unsupported/stale refs → plain shell in saved cwd; when native resume applies, it wins over pane-history replay. ([Session state](https://herdr.dev/docs/session-state/); [CHANGELOG](https://github.com/ogulcancelik/herdr/blob/master/CHANGELOG.md); feature origin [#233](https://github.com/ogulcancelik/herdr/issues/233))

7. **Windows beta hard limits for connect modes.** Local persistent sessions/ConPTY panes are beta; **unsupported:** `herdr --remote` from the Windows binary, direct terminal attach, live server handoff, remote clipboard image bridge. From Windows, remote work = `ssh you@server` then `herdr` on the Unix host. After Windows updates, restart sessions (no Unix live handoff). Live cwd after PowerShell `cd` is partial; prefer integrations/OSC7. ([Windows beta](https://herdr.dev/docs/preview/windows-beta/))

8. **Public discussion adds trust caveats on top of the docs.** Resume landed in v0.6.3 (#233) and is now default; users still report stale/wrong session refs after `/clear`/rotation (#619) or when an agent exit was never observed across `server stop` (#943)—resume can relaunch the wrong agent. Windows users report ConPTY freezes on agent exit / pane close (#860). Treat resume as best-effort and verify with `herdr agent get` / integration status after restarts. (GitHub issues above; CHANGELOG notes session-identity fixes in later releases)

### Contradictions / uncertainty

- **Perplexity vs docs on “handoff”:** Some secondary writeups blur “second client attach” with live handoff. Official docs: handoff is opt-in `--handoff` on `herdr update` / `herdr --remote` to transfer live panes to a *new server binary*; plain remote attach uses normal restart/stop. ([Session state](https://herdr.dev/docs/session-state/))
- **`session attach` vs `--session`:** Both attach named sessions; `session attach` is the explicit subcommand; `--session` is a launch flag (also used with `--remote`). Same concept, different CLI surface. ([CLI reference](https://herdr.dev/docs/cli-reference/))
- **Resume reliability:** Docs say default-on + integration version gates; issues #619/#943 show identity can lag reality—public trust is lower than marketing “agents come back.”
- **Windows “no second client” claims:** Unsupported features are documented; freeze/kick anecdotes (#860) are beta bugs, not a documented multi-client policy.
- Unverified secondary claim: a dedicated `herdr integration reset` as the stale-ID fix—prefer closing the pane / updating integrations / checking `agent get` until docs document a reset command.

### Implications

- Interview / coach framing: teach **detach ≠ stop**; stop kills processes; only layout + optional native resume return.
- Default playbook: local → bare `herdr`; parallel projects → named sessions; laptop→server with clipboard → `herdr --remote` (Unix/macOS client); phone → SSH then `herdr`; one-pane focus → `agent|terminal attach` (Unix).
- On Windows: never promise `--remote` or direct attach; coach SSH-to-Linux then `herdr`.
- After stop/reboot demos: run `herdr integration status` and expect some panes to be shells if session refs are missing/stale.
- Prefer detach over `server stop` whenever agents or long-running jobs must stay alive.

### Sources

- https://herdr.dev/docs/how-to-work/
- https://herdr.dev/docs/persistence-remote/
- https://herdr.dev/docs/session-state/
- https://herdr.dev/docs/cli-reference/
- https://herdr.dev/docs/preview/windows-beta/
- https://github.com/ogulcancelik/herdr/blob/master/CHANGELOG.md
- https://github.com/ogulcancelik/herdr/issues/233
- https://github.com/ogulcancelik/herdr/issues/619
- https://github.com/ogulcancelik/herdr/issues/943
- https://github.com/ogulcancelik/herdr/issues/860
- https://www.tecmint.com/herdr-run-ai-coding-agents-in-linux-terminal/
- Perplexity Agent `pro-search` raw: `a3_perplexity_raw.json`
