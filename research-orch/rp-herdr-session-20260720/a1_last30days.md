## A1 Recency Digest

Window: ~2026-06-20 to 2026-07-20. Method: WebSearch/WebFetch + `gh` on `ogulcancelik/herdr` (last30days engine not usable: no `~/.config/last30days/.env`).

### Key signals (bullets with dates if known)

- **Product model (docs, current):** Herdr is a background session server + terminal clients. Local path: `herdr` auto-starts/attaches the default session; `ctrl+b q` detaches; `herdr` reattaches with live processes. Named sessions: `herdr session attach <name>` / `herdr --session <name>`. Remote: either `ssh …` then `herdr` (tmux-style), or Unix/macOS thin client `herdr --remote <host>` / `herdr --remote <host> --session <name>`. Direct attach: `herdr agent attach <name>`, `herdr terminal attach <id>` (Unix; unsupported on Windows beta). Escape hatch: `herdr --no-session`. Sources: [how-to-work](https://herdr.dev/docs/how-to-work/), [persistence-remote](https://herdr.dev/docs/persistence-remote/), [cli-reference](https://herdr.dev/docs/cli-reference/).

- **After restart ≠ after detach (docs):** Detach keeps processes alive. Full server stop/restart restores layout/cwd/focus but **not** arbitrary processes unless native agent session restore (`claude --resume`, `codex resume`, etc.) or optional pane history. Live handoff (`herdr update --handoff`, `herdr --remote … --handoff`) is opt-in and Unix-oriented; Windows beta has no live handoff. Source: [session-state](https://herdr.dev/docs/session-state/).

- **Windows beta gap (docs + issues, July 2025–Jul 2026):** Native Windows supports local persistent sessions (ConPTY) but **not** `herdr --remote` or direct terminal attach. Documented workaround: `ssh you@server` then `herdr`. Users must restart sessions after Windows updates (no live handoff). Feature request [#1042](https://github.com/ogulcancelik/herdr/issues/1042) (2026-07-05, closed as tracking) asks for native Windows `--remote`. [#1544](https://github.com/ogulcancelik/herdr/issues/1544) (2026-07-17): SSH + `herdr` on Windows ConPTY rendered UI but dropped keyboard/mouse input (closed same day; still a real attach-path friction report). Docs: [windows-beta](https://herdr.dev/docs/windows-beta/).

- **Remote-attach friction (closed/open in window):** Repeated SSH password prompts [#888](https://github.com/ogulcancelik/herdr/issues/888) (2026-06-30, fixed via connection reuse). Opaque SSH auth errors [#1034](https://github.com/ogulcancelik/herdr/issues/1034) (2026-07-05). High-latency handshake EAGAIN [#753](https://github.com/ogulcancelik/herdr/issues/753) (2026-06-22). Open: remote not detecting installed binary on non-POSIX login shells (xonsh) [#1201](https://github.com/ogulcancelik/herdr/issues/1201) (2026-07-08) - forces SSH-first attach. Changelog also cites TOTP/keyboard-interactive gaps [#1050](https://github.com/ogulcancelik/herdr/issues/1050) and remote binary discovery for Homebrew/mise/Nix.

- **Viral / community pulse (late June – mid July 2026):** Repo hit GitHub Trending; Shareuhack guide (fetched ~2026-07-06) cites ~12.2k stars and HN [#48714802](https://news.ycombinator.com/item?id=48714802). Latest stable **v0.7.4** (2026-07-15); preview builds through **2026-07-17**. Tecmint / Shareuhack tutorials center on detach/reattach and SSH remote workflows. HN users emphasize SSH + Tailscale reattach and local+remote agent herds in one UI; questions remain about multi-SSH-agent topologies vs named sessions.

- **Hiring / org signals (thin for Herdr-the-product):** No clear public “Herdr is hiring” posting found in-window. Stronger signals are **adoption**: AWS Labs CLI Agent Orchestrator documents Herdr as an experimental backend ([cao herdr.md via repo README](https://github.com/awslabs/cli-agent-orchestrator)); Instagram/roundup posts (e.g. ~2026-07-17) list `ogulcancelik/herdr` beside Codex/Claude tooling. LinkedIn “we’re hiring” hits for similarly named Istanbul founders appear tied to **Exposure AI**, not Herdr - treat as non-signal for Herdr org hiring.

### Quotes / posts worth knowing

- HN (SSH reattach as the win): “because it's backed by a persistent process, I can ssh into the machine, with tailscale, run *herdr* and see all active sessions…” - [HN #48714802](https://news.ycombinator.com/item?id=48714802).

- HN (remote sandbox attach without vendor lock-in): “herdr lets me easily connect to remote agent sessions, see their status in the sidebar and fluidly switch back to work on my local machine from one interface.” - same thread.

- HN (topology confusion): “does it support a setup where each agent can be in a different SSH session? … unclear if it can add remote agents” / reply pointing at named sessions on [persistence-remote](https://herdr.dev/docs/persistence-remote/).

- GitHub [#1042](https://github.com/ogulcancelik/herdr/issues/1042): “The experience is noticeably worse than `herdr --remote` on Linux/macOS… no one-command attach from Windows.”

- GitHub [#1201](https://github.com/ogulcancelik/herdr/issues/1201): “I ssh into remote, type `herdr`, and everything works… use `herdr --remote` and it tells me herdr is not installed… cant use herdr --remote feature at all, have to ssh in first, which prevents me from using the best feature of herdr.”

- GitHub [#1544](https://github.com/ogulcancelik/herdr/issues/1544): “`herdr --remote <target>` is not usable here — it returns `remote mode is not supported on Windows yet` — so SSH + `herdr` is the attach path… UI renders… but no keyboard or mouse input.”

- Official pitch (herdr.dev / README): “detach, agents keep running — reattach from any terminal, or over ssh. sessions survive restarts” / `ctrl+b q` then `herdr`.

### Implications for the research question

**How people connect today**

1. **Local reattach:** `herdr` (default) or `herdr session attach <name>` / `herdr --session <name>` after `ctrl+b q`.
2. **Named sessions:** Independent servers via session CLI; remote named: `herdr --remote <host> --session <name>`.
3. **Remote:** Prefer `herdr --remote` on Linux/macOS (thin client + clipboard bridge); fallback/phone/Windows: SSH then `herdr`.
4. **After restart:** Re-run `herdr` / session attach; expect layout restore + agent `--resume` where integrations are current - not full process continuity unless handoff succeeded.
5. **Direct attach:** `herdr agent attach` / `herdr terminal attach` for one pane (not Windows beta).

**Recent friction that matters for interviews / product questions**

- Windows users are on a **second-class attach path** (no `--remote`, no direct attach, update requires session restart; SSH+ConPTY input bugs reported).
- `--remote` discovery/auth (shell PATH, password reuse, 2FA, latency) still causes “works after `ssh` but `--remote` fails” - the exact UX gap users call “best feature.”
- Mental model: **detach vs server restart** is under-communicated in viral posts; people may expect tmux-like survival across reboot/update without understanding snapshot vs handoff vs agent resume.
- Community narrative is strong on SSH reattach and agent status; weaker on multi-host agent fleets and Windows remote parity.

### Sources (url list)

- https://herdr.dev/
- https://herdr.dev/docs/how-to-work/
- https://herdr.dev/docs/persistence-remote/
- https://herdr.dev/docs/session-state/
- https://herdr.dev/docs/windows-beta/
- https://herdr.dev/docs/install/
- https://herdr.dev/docs/cli-reference/
- https://github.com/ogulcancelik/herdr
- https://github.com/ogulcancelik/herdr/blob/master/CHANGELOG.md
- https://github.com/ogulcancelik/herdr/issues/1042
- https://github.com/ogulcancelik/herdr/issues/1201
- https://github.com/ogulcancelik/herdr/issues/1544
- https://github.com/ogulcancelik/herdr/issues/888
- https://github.com/ogulcancelik/herdr/issues/1034
- https://github.com/ogulcancelik/herdr/issues/753
- https://github.com/ogulcancelik/herdr/issues/1050
- https://news.ycombinator.com/item?id=48714802
- https://www.shareuhack.com/en/posts/herdr-terminal-agent-multiplexer-guide-2026
- https://www.tecmint.com/herdr-run-ai-coding-agents-in-linux-terminal/
- https://github.com/awslabs/cli-agent-orchestrator
- https://www.ai.joaoqueiros.com/blog/github-trending-ai-design-office-agents-job-search-july-2026
