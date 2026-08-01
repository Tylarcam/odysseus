## ADDED Requirements

### Requirement: Priority queue items show their lineage chain
`_build_priority_queue()` SHALL attach the immediate `related_to` parent (per `cmd-center-lineage`) to each item it ranks, so the operator can see what produced a given directive-worthy item without leaving CORE.

#### Scenario: Handoff shows the job that spawned it
- **WHEN** a handoff in the priority queue was materialized from a job
- **THEN** its queue row SHALL include `related_to: [{kind: "job", id: <job id>}]`

### Requirement: Globe graph draws real cross-object edges, not only branch stars
`build_globe_graph()` SHALL add an edge between two non-branch nodes whenever a lineage edge (per `cmd-center-lineage`) exists connecting the objects those nodes represent, in addition to the existing branch→node edges.

#### Scenario: Note and its promoted task are linked on the globe
- **WHEN** the globe graph includes both a note node and a task node connected by a lineage edge
- **THEN** the graph SHALL render an edge directly between those two nodes, not only each node's separate edge to its branch

### Requirement: Stalled-chain items get a distinct urgency tier
When any item in a lineage chain is flagged stalled (per `cmd-center-stalled-item-detection`), CORE's priority queue SHALL surface that chain with urgency at least equal to the highest-urgency source in the existing urgency table, so a stalled dependency is never masked by the chain's terminal item looking fine on its own.

#### Scenario: Stalled job blocks a chain that looks otherwise fine
- **WHEN** a job feeding a not-yet-due handoff has been stalled in `needs_review` past its SLA
- **THEN** the priority queue SHALL surface the stalled job at its escalated urgency, independent of the handoff's own due state
