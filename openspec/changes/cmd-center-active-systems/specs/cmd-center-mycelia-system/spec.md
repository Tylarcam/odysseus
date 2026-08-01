## ADDED Requirements

### Requirement: Swarm tasks are identified by an explicit registry, not ID-prefix convention
The system SHALL maintain an explicit registry (real metadata: task id, display name, doc references) for swarm tasks, replacing the `swarm-`-ID-prefix and hardcoded-title-substring matching currently used to detect swarm activity and populate `mycelia_commands`.

#### Scenario: A new swarm task is added without relying on naming convention
- **WHEN** a new swarm task is registered with metadata (not merely an ID starting with `swarm-`)
- **THEN** MYCELIA SHALL recognize it as a swarm task and it SHALL be eligible to appear in `agent_activity`/`mycelia_commands` without any string-prefix matching

#### Scenario: A non-swarm task with a coincidental name is not misclassified
- **WHEN** a task's ID or title happens to contain "swarm"-like substrings but is not in the registry
- **THEN** the system SHALL NOT classify it as swarm activity

### Requirement: MemPalace graph representation reflects actual content signal where feasible
The system SHALL replace the CLI-`status`-based drawer-count bridge with the richest content signal actually callable from the backend process (e.g. `mempalace search`), given that the MCP-only graph tools (`kg_query`/`traverse`/`graph_stats`/`find_tunnels`) are not callable in-process from a plain Python backend today. Full graph-tool parity is explicitly deferred pending a queryable interface MemPalace exposes outside the MCP protocol (see design.md Open Questions).

#### Scenario: Graph stats reflect real content signal, not decorative counts
- **WHEN** `mycelia_stats` renders MemPalace-derived node/edge information
- **THEN** it SHALL be derived from an actual queryable MemPalace signal (not solely wing/room/drawer counts from `status` text-parsing), to the extent the backend can call one directly

#### Scenario: Full graph traversal remains unavailable
- **WHEN** no queryable, non-MCP MemPalace interface exists at implementation time
- **THEN** the system SHALL NOT claim to provide `kg_query`/`traverse`-equivalent graph traversal in MYCELIA, and SHALL leave this explicitly as a follow-on rather than a false success

> **Phase 8 status:** Deferred. Documented in `design.md` § Deferred (Phase 8 decision) and `services/mempalace/bridge.py` module docstring. Backend uses `mempalace search` (+ `status` fallback) only — no MCP graph-tool shim.
