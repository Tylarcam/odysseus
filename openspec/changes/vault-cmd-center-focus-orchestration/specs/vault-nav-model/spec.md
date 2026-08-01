## ADDED Requirements

### Requirement: One top-level view model shared by desktop and mobile
V.A.U.L.T. SHALL present the same four top-level views — `HUD`, `Queue`, `Commands`, `Wire` — as the canonical navigation on both desktop and mobile breakpoints. Desktop SHALL NOT present a separate, structurally different top-level tab set (the prior 7-tab `TAB_LAYOUT` domain row) as an alternative to these four views.

#### Scenario: Desktop and mobile land on the same default view
- **WHEN** the vault opens with no saved view preference
- **THEN** both desktop and mobile default to the `HUD` view

#### Scenario: Switching views uses the same control vocabulary on both breakpoints
- **WHEN** an operator switches from `HUD` to `Wire`
- **THEN** the same `view` state (`hud`|`queue`|`commands`|`wire`) drives the rendered panel set on both desktop and mobile

### Requirement: Domain filter is a secondary lens on HUD, not a competing nav axis
On desktop, the seven domain labels (CORE, MEM, PROD, COMMS, AGENCY, RELAY, MYCELIA) SHALL be presented as a filter strip within the `HUD` view that narrows which panels/rows are shown, rather than as top-level tabs that each mount an independently composed layout.

#### Scenario: Domain filter narrows HUD content without changing the view
- **WHEN** an operator on desktop selects the `RELAY` domain filter while in `HUD`
- **THEN** the `view` remains `hud` and only RELAY-relevant panels/rows are shown within it

#### Scenario: CORE filter shows the full unfiltered HUD
- **WHEN** the domain filter is `CORE` (the default)
- **THEN** `HUD` shows the full cross-domain panel set as it does today

### Requirement: View and domain-filter preference persist under one storage key
The frontend SHALL persist the current `{ view, domainFilter }` state under a single `localStorage` key (`odysseus-cmd-view`), replacing the prior separate/implicit persistence for domain tab vs. mobile tab state.

#### Scenario: Preference survives reload
- **WHEN** an operator selects `Queue` + `AGENCY` filter and reloads the page
- **THEN** the vault reopens on `Queue` with the `AGENCY` filter applied

### Requirement: Legacy domain-tab preference migrates forward once
On first load after this change, if the old `odysseus-cmd-domain-tab` key exists and the new `odysseus-cmd-view` key does not, the frontend SHALL read the old key's value and use it to seed `domainFilter` in the new key, then leave the old key in place (read-only, unused thereafter).

#### Scenario: Existing RELAY preference carries forward
- **WHEN** an operator previously had `odysseus-cmd-domain-tab` set to `RELAY` and opens the vault after this change ships
- **THEN** the vault's `HUD` view opens with the `RELAY` domain filter applied, without the operator having to reselect it
