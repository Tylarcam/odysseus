## A2 Authority Digest

Firecrawl scrape/search used 2026-07-20. LinkedIn pages are profile shells (no email in public HTML).

### Org / email patterns at NPR

- **Primary (RocketReach corp page):** `[first_initial][last]@npr.org` — **92.3%** (ex. `jdoe@npr.org`).
- Other formats: `[first][last]`, `[last]`, `[last][first_initial]`, etc. (each ≤3%).
- **User-confirmed instance:** `braynor@npr.org` (Ben Raynor / recruiting).
- Historical journalism guidance (The Awl / MetaFilter era) also describes `FLast@npr.org`.
- Public show inboxes (`TheSundayStory@npr.org`, `shortwave@npr.org`) appear in transcripts; not personal staff mail.

Source: https://rocketreach.co/npr-email-format_b5c60063f42e0c56

### Greta Pittenger

- NPR people page: https://www.npr.org/people/g-s1-111855/greta-pittenger — stories archive; **no mailto / email**.
- LinkedIn: https://www.linkedin.com/in/gretapittenger — RAD at NPR; **no email in scrape**.
- X: https://x.com/regreters — bio only.
- UW iSchool alumni note confirms prior NPR RAD placement (older).
- **Do not use** Limestone Title email (different person in Louisville, KY).

**Best public guess:** `gpittenger@npr.org` (pattern-inference only).

### Nicolette Khan

- LinkedIn: https://www.linkedin.com/in/nicolette-khan-889393109 — RAD at NPR.
- Frequent NPR byline / fact-check credits (Books We Love, Sunday Story, Short Wave, etc.).
- RocketReach person page exists but free view does not print address.
- Transcripts point listeners to show emails, not hers.

**Best public guess:** `nkhan@npr.org` (pattern-inference only).

### Kriti Singh

- LinkedIn: https://www.linkedin.com/in/kritisinghh — AI Labs @ NPR.
- GitHub: https://github.com/kritisgh — “AI Labs @npr”, org NPR, DC; lists `www.kritisingh.xyz` (DNS failed on scrape 2026-07-20; no email on GitHub profile).
- NPR story credit Jun 2026: “NPR's Kriti Singh contributed reporting…”.
- RocketReach person page exists; address not in free snippet.
- Name collision risk on `ksingh@npr.org` is material.

**Best public guess:** `ksingh@npr.org` (pattern-inference) + LinkedIn message backup. Personal site unscrapable at time of run.

### Source excerpts (short quotes + URLs)

> “The most common NPR email format is [first_initial][last] (ex. jdoe@npr.org), which is being used by 92.3% of NPR work email addresses.”  
> — https://rocketreach.co/npr-email-format_b5c60063f42e0c56

> NPR people page for Greta: story list only; og:description “NPR stories by Greta Pittenger” — no contact field.  
> — https://www.npr.org/people/g-s1-111855/greta-pittenger

### Confidence summary table

| Person | Address / path | Confidence |
|--------|----------------|------------|
| Greta Pittenger | `gpittenger@npr.org` | likely-pattern |
| Nicolette Khan | `nkhan@npr.org` | likely-pattern |
| Kriti Singh | `ksingh@npr.org` | likely-pattern (collision risk) |
| All three | LinkedIn InMail | verified path (not email) |
| Recruiter | `braynor@npr.org` | verified (user context) |
