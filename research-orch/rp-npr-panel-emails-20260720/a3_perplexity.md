## A3 Perplexity Digest

**Engine:** `perplexity_agent_direct` (Odysseus route fell back to direct; raw in `a3_perplexity_raw.json`). Cross-checked with Firecrawl RocketReach scrape (92.3% flast pattern).

### Findings (numbered, cited)

1. **No verified cleartext personal emails** for Greta Pittenger, Nicolette Khan, or Kriti Singh appear on NPR.org people pages, LinkedIn public HTML, or GitHub (A2 scrapes + Perplexity report).
2. **Dominant NPR work-email pattern** is `[first_initial][last]@npr.org` (~78–92% depending on directory vendor). RocketReach corporate page (scraped): **92.3%**. Clay/older guides agree on flast. User-known: `braynor@npr.org`.
3. **Pattern-inferred candidates:** `gpittenger@npr.org`, `nkhan@npr.org`, `ksingh@npr.org`. All **unverified**.
4. **Kriti Singh** has higher collision risk (`Singh` is common); LinkedIn `kritisinghh` / GitHub `kritisgh` are the reliable identity anchors.
5. **Show aliases** (`TheSundayStory@npr.org`, etc.) are wrong targets for panel thank-yous.
6. **Alternate send path:** LinkedIn messages; or ask Ben Raynor (`braynor@npr.org`) to forward if direct mail bounces.

### Contact sheet

| Person | Email or path | Confidence | Source |
|--------|---------------|------------|--------|
| Greta Pittenger | `gpittenger@npr.org` | likely-pattern | RocketReach format + name; NPR people page (no mailto) |
| Nicolette Khan | `nkhan@npr.org` | likely-pattern | Same |
| Kriti Singh | `ksingh@npr.org` | likely-pattern | Same; collision risk |
| Kriti Singh | LinkedIn InMail | verified path | linkedin.com/in/kritisinghh |
| Greta / Nicolette | LinkedIn InMail | verified path | linkedin profiles |
| Ben Raynor (forward) | `braynor@npr.org` | verified | Odysseus recruiting correspondence |

### Contradictions / uncertainty

- Directory vendors disagree slightly on exact % for flast (78% vs 92%); directionally the same pattern.
- Paywalled RocketReach person pages claim to have emails but do not prove the string publicly.
- Personal site kritisingh.xyz listed on GitHub but DNS failed at scrape time.

### Implications (how Tylar should send thank-yous)

1. Send the three approved drafts to the pattern addresses above.
2. If bounce on any (especially Kriti), resend via LinkedIn with the same short body.
3. Optional: BCC or parallel note to Ben Raynor only if a bounce happens and timeline is tight — not required for first attempt.
4. Do **not** use show inboxes or the KY Limestone Title Greta email.

### Sources

- https://rocketreach.co/npr-email-format_b5c60063f42e0c56
- https://www.theawl.com/2010/11/how-to-email-npr/
- https://www.npr.org/people/g-s1-111855/greta-pittenger
- https://www.linkedin.com/in/gretapittenger
- https://www.linkedin.com/in/nicolette-khan-889393109
- https://www.linkedin.com/in/kritisinghh
- https://github.com/kritisgh
- a3_perplexity_raw.json (Perplexity agent report)
