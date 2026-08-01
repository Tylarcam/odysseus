## ADDED Requirements

### Requirement: Notes cluster into visible threads instead of a flat list
`build_notes_preview()` (or its successor) SHALL group notes that share a lineage edge or shared tag/topic into a single thread entry, so MEM presents clusters rather than one row per note.

#### Scenario: Two notes sharing a lineage edge appear as one thread
- **WHEN** a note was promoted into a task (lineage edge `relation="promoted"`) and both still exist
- **THEN** MEM's notes rail SHALL present them as one thread entry showing both, not two unrelated rows

### Requirement: Orphaned threads are detected and surfaced for disposition
The system SHALL generalize the existing stale-brief heuristic (`_is_stale_brief`) into an orphaned-thread detector: any note (or thread) with open checklist items untouched for longer than the configured threshold SHALL be flagged for an explicit reap/close/promote-to-task decision.

#### Scenario: Old checklist note surfaces for disposition
- **WHEN** a note with open checklist items has not been updated for longer than the orphaned-thread threshold
- **THEN** MEM SHALL surface it in a distinct "needs disposition" grouping with actions to close, reap, or promote it to a task

### Requirement: Mem focus is a synthesized brief, not static copy
`mem_focus` SHALL replace its current static copy with a generated summary reflecting current thread/cluster state (counts of active threads, orphaned threads, and stale items) recomputed on each `build_cmd_center()` call.

#### Scenario: Mem focus reflects current orphaned count
- **WHEN** three notes are currently flagged as orphaned threads
- **THEN** `mem_focus` SHALL state that count rather than generic unconditional copy
