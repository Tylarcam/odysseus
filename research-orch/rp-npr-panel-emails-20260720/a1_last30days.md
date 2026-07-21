## A1 Recency Digest

### Key signals (bullets with dates if known)

- **No plain-text personal `@npr.org` emails** surfaced on public NPR people pages, recent story bylines, or LinkedIn for Greta Pittenger, Nicolette Khan, or Kriti Singh (searched 2026-07-20).
- **NPR org email pattern (third-party):** RocketReach reports `[first_initial][last]@npr.org` as **92.3%** of NPR work emails (example `jdoe@npr.org`). Secondary patterns include `[first][last]@npr.org` (~2.9%). Source: https://rocketreach.co/npr-email-format_b5c60063f42e0c56
- **Known verified pattern instance from Tylar’s pipeline:** `braynor@npr.org` (Ben Raynor) — matches first-initial + last.
- **Show / program inboxes** appear in credits (not personal): e.g. `TheSundayStory@npr.org` on stories fact-checked by Greta/Nicolette (2024–2026). Unsuitable as primary thank-you destination.
- **Kriti Singh** credited on NPR reporting as recently as 2026-06-03 (“NPR's Kriti Singh contributed reporting…”). GitHub `kritisgh` lists AI Labs @ NPR + personal site `www.kritisingh.xyz` (no email in profile scrape).
- **Name collision risk:** Unrelated Greta Pittenger (KY real estate / Limestone Title) has `Greta@Limestone-Title.com` — **not** the NPR RAD person.
- RocketReach person pages exist for Nicolette Khan and Kriti Singh but **do not expose the address in free snippets** (paywalled).

### Candidate emails by person (with confidence)

| Person | Candidate | Confidence | Notes |
|--------|-----------|------------|-------|
| Greta Pittenger | `gpittenger@npr.org` | **likely-pattern** | Not printed on npr.org/people page. Matches RocketReach primary format + `braynor` precedent. |
| Nicolette Khan | `nkhan@npr.org` | **likely-pattern** | Same. Short last name → lower collision risk than Singh. |
| Kriti Singh | `ksingh@npr.org` | **likely-pattern / collision risk** | Common surname; if bounce, try LinkedIn. Not verified. |
| (wrong person) | `Greta@Limestone-Title.com` | **reject** | Different Greta Pittenger. |

**Verified:** none of the three panelists’ personal work emails found in cleartext.

### Quotes / posts worth knowing

- RocketReach NPR format page: “The most common NPR email format is [first_initial][last] (ex. jdoe@npr.org), which is being used by 92.3% of NPR work email addresses.”
- Story credits route listener mail to show boxes (e.g. Sunday Story), not RAD individuals.

### Implications for the research question

Best public path is **pattern-inferred `@npr.org` addresses** plus LinkedIn backup. Treat all three as unconfirmed until a reply or non-bounce. Prefer asking Ben Raynor (known `braynor@npr.org`) to forward thank-yous if any bounce.

### Sources (url list)

- https://rocketreach.co/npr-email-format_b5c60063f42e0c56
- https://rocketreach.co/nicolette-khan-email_19619156
- https://rocketreach.co/kriti-singh-email_508337853
- https://www.npr.org/people/g-s1-111855/greta-pittenger
- https://www.linkedin.com/in/gretapittenger
- https://www.linkedin.com/in/nicolette-khan-889393109
- https://www.linkedin.com/in/kritisinghh
- https://github.com/kritisgh
- https://www.npr.org/2026/06/03/nx-s1-5843359/white-house-gov-website-alien-immigration
- https://www.npr.org/2026/01/18/nx-s1-5647661/defending-the-disabled
- https://limestonetitleandescrow.com/team/greta-pittenger/
