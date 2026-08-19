## ADDED Requirements

### Requirement: Every domain declares a question, a primary verb, and an agent speech policy

Each domain SHALL declare a stated question it answers, exactly one primary verb, and an agent speech
policy describing what the agent volunteers when the domain becomes active. These declarations SHALL live
alongside the domain's layout definition so a domain cannot be added without them.

The initial declarations are:

| Domain | Question | Verb |
|---|---|---|
| CORE | What is on fire right now? | TRIAGE |
| MEM | What do I already know about this? | RECALL |
| PROD | What is the next move? | COMMIT |
| COMMS | Who is waiting on me? | REPLY |
| AGENCY | What did the agents produce? | REVIEW |
| RELAY | What is stuck between systems? | UNBLOCK |
| MYCELIA | What did the swarm learn? | HARVEST |

#### Scenario: Each domain exposes its question and verb

- **WHEN** any domain is active
- **THEN** its declared question and primary verb SHALL be available to both the rendering layer and the
  agent

#### Scenario: A domain without declarations is rejected

- **WHEN** a domain is defined without a question, a verb, or a speech policy
- **THEN** it SHALL be treated as an incomplete definition rather than rendered with defaults

### Requirement: The declared question is visible on the surface

The active domain's question SHALL be presented on the surface, so the operator can see what the domain
is for without prior knowledge.

#### Scenario: Switching domains changes the visible question

- **WHEN** the operator switches from CORE to RELAY
- **THEN** the visible question SHALL change from CORE's question to RELAY's question

### Requirement: Entering a domain changes what the agent volunteers

When a domain becomes active, the agent's behavior SHALL be governed by that domain's speech policy, so
that switching domains changes the agent's default subject rather than only which panels render.

#### Scenario: RELAY volunteers the broken transfer

- **WHEN** the RELAY domain becomes active and a failed handoff exists
- **THEN** the agent's volunteered subject SHALL be that broken transfer and its blast radius

#### Scenario: PROD volunteers one task and its justification

- **WHEN** the PROD domain becomes active
- **THEN** the agent SHALL volunteer a single recommended task together with why it outranks the others

#### Scenario: Domain switch changes the volunteered subject

- **WHEN** the operator switches from PROD to COMMS
- **THEN** the agent's volunteered subject SHALL change from a recommended task to who is awaiting a
  reply

### Requirement: The primary action offered matches the domain verb

The single primary action presented for the active domain SHALL correspond to that domain's declared
verb. Competing primary actions SHALL NOT be presented for the same domain.

#### Scenario: RELAY offers unblock as its primary action

- **WHEN** the RELAY domain is active and an actionable stuck handoff exists
- **THEN** the primary action presented SHALL correspond to unblocking it

#### Scenario: Only one primary action is presented

- **WHEN** several actions are available in the active domain
- **THEN** exactly one SHALL be presented as primary and the remainder SHALL be presented without
  primary emphasis

### Requirement: A domain with nothing requiring action says so and yields its space

When no item in a domain satisfies the attention-layer test, the domain SHALL present a single statement
to that effect rather than rendering panels of zero-valued counters.

#### Scenario: Empty review queue collapses

- **WHEN** the AGENCY domain has no results awaiting review
- **THEN** it SHALL present a single statement that nothing awaits review, rather than panels reporting
  zero ready and zero in review

#### Scenario: Quiet domain is indicated before it is opened

- **WHEN** a domain has no items in the attention layer
- **THEN** its navigation indicator SHALL reflect that, so the operator can tell without opening it
