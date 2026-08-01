## ADDED Requirements

### Requirement: cmd-center payload includes a content hash
`build_cmd_center` SHALL compute and include a `payload_hash` field derived deterministically from the response content, excluding fields that change on every call regardless of underlying data (`synced_at`) and excluding `globe_graph` (covered separately below).

#### Scenario: Identical underlying data produces identical hash
- **WHEN** `build_cmd_center` is called twice in immediate succession with unchanged notes/docs/tasks/handoffs/jobs/sessions
- **THEN** the two calls' `payload_hash` values SHALL be equal

#### Scenario: A data change produces a different hash
- **WHEN** a note's `due_date` changes between two calls to `build_cmd_center`
- **THEN** the two calls' `payload_hash` values SHALL differ

### Requirement: GET /api/home/cmd-center short-circuits unchanged polls
The `GET /api/home/cmd-center` route SHALL accept an optional `since_hash` query parameter. When the freshly computed `payload_hash` matches `since_hash`, the route SHALL return a minimal response `{"unchanged": true, "synced_at": <current timestamp>, "payload_hash": <hash>}` instead of the full payload.

#### Scenario: Matching hash returns the minimal unchanged response
- **WHEN** a client polls with `since_hash` equal to the current data's computed hash
- **THEN** the response body is the minimal `unchanged` shape, not the full cmd-center payload

#### Scenario: Non-matching or missing hash returns the full payload
- **WHEN** a client polls with `since_hash` omitted, or with a value that does not match the current hash
- **THEN** the response body is the full cmd-center payload as before, including a fresh `payload_hash`

#### Scenario: A query error is never reported as unchanged
- **WHEN** any underlying data query raises an exception during a poll with `since_hash` set
- **THEN** the route SHALL propagate the error through the existing error-handling path and SHALL NOT return `{"unchanged": true}`

### Requirement: Live poller applies the short-circuit and avoids a full re-render on unchanged
`cmdCenterLive.js`'s `fetchData` SHALL send the last-received `payload_hash` as `since_hash` on each poll. When the response is `{"unchanged": true}`, the parent's `applyUpdate` SHALL update only the sync-label timestamp and SHALL NOT re-render panels.

#### Scenario: Unchanged poll updates only the sync label
- **WHEN** a scheduled poll receives `{"unchanged": true, "synced_at": ...}`
- **THEN** the sync label reflects the new `synced_at` and no panel content is re-rendered

#### Scenario: Changed poll re-renders normally
- **WHEN** a scheduled poll receives a full payload with a new `payload_hash`
- **THEN** the parent applies the update and re-renders as it does today, and stores the new `payload_hash` for the next poll's `since_hash`

### Requirement: Globe graph is excluded from the default poll cadence
`GET /api/home/cmd-center` SHALL accept an optional `include_globe` query parameter (default `false` on polled requests, `true` on the initial open fetch). When `false`, the response SHALL omit `globe_graph` entirely rather than recomputing it, and `build_cmd_center` SHALL skip calling `fetch_mempalace_globe_graph()`/`build_globe_graph()` in that case.

#### Scenario: Default poll omits globe_graph and skips its computation
- **WHEN** `cmdCenterLive.js` issues its default 30s poll without requesting the globe view
- **THEN** the request includes `include_globe=false` (or omits it, defaulting to false), the response has no `globe_graph` key, and the MemPalace fetch is not made for that request

#### Scenario: Opening the vault or viewing the globe still fetches it
- **WHEN** the vault performs its initial open fetch, or the operator switches to a view that renders the globe
- **THEN** the request includes `include_globe=true` and the response contains a freshly computed `globe_graph`

#### Scenario: Frontend retains the last-known globe_graph between includes
- **WHEN** a poll response omits `globe_graph` because `include_globe` was false
- **THEN** the frontend SHALL keep rendering the previously fetched `globe_graph` rather than clearing it
