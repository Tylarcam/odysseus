## A1 Recency Digest

Research window: ~30 days ending **2026-07-12**, with broader high-signal threads where recent Reddit posts were sparse (Reddit blocked direct fetch; indexed snippets and GitHub/wiki used).

---

### Key signals (bullets with dates if known)

**Gamepad / controller persistence**

- **2026-07-04** — ArkOS4Clone wiki documents an official reset path for scrambled button maps: power off → delete `.console` on the BOOT partition → reboot restores default RetroArch/PPSSPP mappings. This implies `.console` is a persistent state file tied to input config lifecycle on clone firmware.
- **2026-03-05 / 2026-03-10** — ArkOS4Clone **20260305** release notes flag a known bug: *"RetroArch cannot save its configuration after booting."* Fix: re-download `firstboot.sh`, replace on BOOT partition, delete `.console`, reboot. GitHub issue **#277** (2026-03-10) shows RA64 saves persist while RA32 appeared not to until user used **Configuration File → Save Current Configuration** (not a silent auto-save).
- **2026-03-10** — User on **R36S clone Panel Choice 2** reported same RA32 save failure after fresh flash + updates (GitHub #277 comment by mitcssaoe).
- **2026-06-09** — **ArkOS-R3XS archived** (read-only). Community guidance (Tech Tactician, Mar 2026) now points clone owners to **dArkOSRE-R36** and **ArkOS4Clone** instead of legacy R3XS images for ongoing input/WiFi fixes.
- **2026-06-19** — ArkOS4Clone **20260619** fixes SoySauce R36S empty DTB selector bug — wrong/missing DTB is a root cause of inverted/wrong GPIO mappings that look like "controls reset every boot."
- **Ongoing (Handhelds Wiki, Jul 2026)** — Stock/cheap SD cards are repeatedly cited as cause of settings (including `es_input.cfg`, saves, themes) not persisting; replace card before chasing software fixes.
- **Broader** — Clone boards (Y3506/soysauce, G80C/G80CA, G80D, V20) have **panel- and batch-specific GPIO/ADC mappings**. Wrong `.dtb` = inverted sticks, Select/Start on D-pad, controls that "fix" in ES but break in Ports/RetroArch.
- **Broader** — Correct ES remap path: `Start → Controller Settings → Configure Input` writes `/etc/emulationstation/es_input.cfg`. Community script **R36S-FN-SELECT-FIX** syncs ES + RetroArch/RA32 autoconfigs and warns per-core overrides can re-break hotkeys after reboot.

**WiFi — internal vs dongle**

- **Default answer: no built-in WiFi** on standard R36S/R36S clones (RK3326). Wireless is via **USB dongle on the right OTG USB-C port** through a **USB-C→USB-A OTG adapter**. Left port is charge-only (Handhelds Wiki, r36swiki, ArkOS FAQ, Lumerk 2026 guide).
- **2026-06-19** — ArkOS4Clone **20260619**: *"added V30 support to fix the Wi-Fi bug on R36S V30 models"* — some **R36S-V30** boards (2025-10/11-18 revisions) have **internal WiFi pads/chip path** that was broken at DTB level, not a missing dongle issue.
- **2026-03-05** — ArkOS4Clone **20260305** fixed **built-in RK915 WiFi** sleep/wake on K36S, R36ULTRA, XF40H, etc.; also fixed RK915 MAC changing every reboot (looks like "WiFi broken after reboot").
- **2026-03-05** — Known issue on **Clone Type 1/3/4**: **5 GHz WiFi (incl. high-power RTL8821-class dongles) can trigger dwc2 errors**; **2.4 GHz RTL8188** recommended. Upcoming dwc2 fix noted in release.
- **Hardware exception** — Internal WiFi mod possible on **R36S-V21/V22/V30** boards with labeled WiFi pads (RTL8188ETV solder mod); occupies internal USB bus, disables simultaneous OTG WiFi dongle (Handhelds Wiki internal WiFi mod page).
- **AC600 / RTL8821** — **TP-Link Archer T2U Nano** (RTL8811AU) and **T2U Plus** (RTL8821AU) listed as working on ArkOS FAQ and r36swiki. Generic "AC600" dongles often ship **RTL8811CU** (also on R3XS compatibility list). **Chipset matters more than "AC600" branding**; WiFi 6 / "driverless" dongles fail.
- **2026 (indexed)** — r/SBCGaming thread *"Issue trying to connect to Wi-Fi on R36S (Clone) using dArkOS"* reports **TP-Link AC600 dongle** connection failures (full post blocked; title/snippet confirm clone + AC600 + dArkOS).
- **2026 (indexed)** — r/R36S *"Adding games…"* recommends **RTL8188 dongle**, Options → WiFi, for reliable setup on ArkOS.
- **Broader** — Clone on wrong stock DTB (e.g. K36): **neither WiFi dongle nor USB tether worked** until flash to ArkOS4Clone with correct K36 DTB (GitHub immo2n/R36S-K36-DTB-PATCH, Dec 2025).
- **Power/OTG** — Low battery, bad OTG adapter, or insufficient OTG power for RTL8821-class dongles causes "no networks" or dropouts; keep charged or use RTL8188 (~70 mA).

---

### Quotes / posts worth knowing

> "If you encounter an issue where **RetroArch cannot save its configuration after booting**, download **firstboot.sh** again and replace the **firstboot.sh** in the **boot** partition. Then delete the **`.console`** file in the **boot** partition and reboot."  
> — ArkOS4Clone release **20260305**, 2026-03-05

> "please use：Save the current configuration."  
> — lcdyk0517 (maintainer), closing GitHub **#277**, 2026-03-10 (RetroArch 32 appeared to save but did not persist)

> "If you've accidentally scrambled your button configuration, simply: Power off → delete the `.console` file on `/boot` → power on. The button mapping will be restored to defaults after reboot."  
> — ArkOS4Clone wiki §7, updated **2026-07-04**

> "On Clone Type 1, Type 3, and Type 4, using 5G WiFi may trigger dwc2 errors. Using low-power 2.4G WiFi (8188) does not cause this issue."  
> — ArkOS4Clone release **20260305**, 2026-03-05

> "Reverted the dts for panel4; **added V30 support to fix the Wi-Fi bug on R36S V30 models**."  
> — ArkOS4Clone release **20260619**, 2026-06-19

> "R36S has **no built-in WiFi**. You can use WiFi dongle with USB OTG adapter." / "Left USB-C port is charging only — **use right port for OTG**."  
> — r36swiki.com WiFi setup guide

> "I got a clone R36S… not able to connect to the internet. **Not with WIFI dongle nor with USB tether**… flashed arkos4clone and chose the K36 DTB files… **USB tether was working perfectly**."  
> — immo2n/R36S-K36-DTB-PATCH README, 2025-12-15

> "controller mapping functionality. **remove or rename es_input.cfg** Booted system back up, it makes you run through controller setup."  
> — r/R36S snippet, clone Y3506_V05_20251215 thread (indexed)

> "I'm using a **USB WiFi dongle** (AC600 from TP-Link) however, whenever I try to connect, it keeps giving me a message…"  
> — r/SBCGaming, *Issue trying to connect to Wi-Fi on R36S (Clone) using dArkOS* (indexed, ~2026)

> "Wifi **not working with dongle** (stock SD card)" on G80D-MB clone; inverted right joystick on ArkOS K36.  
> — Handhelds Wiki R36S Clones, G80D section (Jul 2026)

---

### Implications for the research question

**Issue 1 — Gamepad must be reconfigured every reboot**

Likely multi-factor, not a single toggle:

1. **Wrong or unstable DTB for clone board** — GPIO/ADC mapping mismatch makes controls look "wrong" or revert when ES/RA reload autoconfigs. Fix: identify board (dtbTools, stock BOOT dtb, Handhelds clone table) → correct ArkOS4Clone/dArkOSRE DTB → *then* remap once.
2. **Config not actually saved** — On ArkOS4Clone, use `firstboot.sh` + delete `.console` if RA won't persist; in RetroArch 32 use **Save Current Configuration** explicitly. ES mapping lives in `/etc/emulationstation/es_input.cfg` via Configure Input.
3. **SD card / improper shutdown** — Cheap stock microSD is the #1 "settings don't stick" cause across Handhelds troubleshooting; use branded card, menu shutdown (not long-press power).
4. **Per-core/per-game overrides** — Files under `configs/remaps/` or RA overrides can override global maps each launch; clean overrides if "fixed until next game/boot."
5. **Recent firmware path** — Prefer **ArkOS4Clone ≥ 20260619** or **dArkOSRE-R36** over archived ArkOS-R3XS for clone-specific input driver unification (odroidgo3 amux mapping per arkos4clone wiki).

**Issue 2 — WiFi: internal vs USB AC600**

| Scenario | What to check |
|----------|----------------|
| **Typical R36S clone** | **No internal WiFi.** Need USB dongle + OTG on **right** port. |
| **R36S-V21/V22/V30 (2024–2025 boards)** | May have **unpopulated WiFi pads** or V30 internal WiFi path; V30 needed arkos4clone **20260619** DTB fix. Inspect board label / Handhelds internal WiFi mod list. |
| **K36S / R36ULTRA / some 2025+ clones** | May have **built-in RK915 WiFi**; requires correct DTB + arkos4clone ≥ 20260305 for sleep/MAC stability. |
| **AC600 dongle** | Identify **actual chipset** (RTL8811AU / RTL8821AU / RTL8811CU). ArkOS supports these in principle, but **clone Type 1/3/4 + 5 GHz/high-power dongle** may hit dwc2 OTG bugs → try **2.4 GHz RTL8188** first. |
| **Dongle present but dead** | Wrong port, bad OTG adapter, low battery, wrong DTB (USB host not brought up), or dArkOS without driver for RTL8188FTV (XNL driver is ArkOS-only). |

**Practical triage order:** (1) Identify clone board + flash matching DTB, (2) replace SD card if any settings fail to persist, (3) for WiFi test RTL8188 on 2.4 GHz before AC600/5 GHz, (4) for controls fix DTB then single ES Configure Input pass + RA "Save Current Configuration", (5) apply `firstboot.sh`/`.console` fix if on ArkOS4Clone.

---

### Sources (url list)

- https://github.com/lcdyk0517/arkos4clone/releases/tag/20260619
- https://github.com/lcdyk0517/arkos4clone/releases/tag/20260305
- https://github.com/lcdyk0517/arkos4clone/wiki
- https://github.com/lcdyk0517/arkos4clone/issues/277
- https://github.com/lcdyk0517/arkos4clone/issues/272
- https://github.com/AeolusUX/ArkOS-R3XS (archived 2026-06-09)
- https://github.com/AeolusUX/ArkOS-R3XS/discussions/171
- https://github.com/AeolusUX/ArkOS-R3XS/issues/95
- https://github.com/immo2n/R36S-K36-DTB-PATCH
- https://github.com/southoz/dArkOSRE-R36
- https://github.com/southoz/dArkOSRE-R36/wiki/Firmware-Installation
- https://github.com/christianhaitian/arkos/wiki/Frequently-Asked-Questions---RK2023
- https://github.com/schoperena/R36S-FN-SELECT-fIX
- https://handhelds.wiki/R36S_Problems_and_Troubleshooting
- https://handhelds.wiki/R36S_Clones
- https://r36swiki.com/wiki-sdwifi.html
- https://r36swiki.com/wiki-wifiupgrade.html
- https://techtactician.com/r36s-handheld-full-starter-guide/
- https://www.lumerk.com.au/blogs/lumerktech/r36s-wifi-setup-guide-why-your-handheld-wont-connect-and-how-to-fix-it
- https://www.teamxnl.com/installing-cheap-wifi-on-your-r36s-or-r36h/
- https://retroconsoleclub.com/r36s-handheld-guide/
- https://www.reddit.com/r/SBCGaming/comments/1u7tl5j/issue_trying_to_connect_to_wifi_on_r36s_clone/
- https://www.reddit.com/r/R36S/comments/1r7qaan/i_bought_a_clone_y3506_v05_20251215_and_how_i_got/
- https://www.reddit.com/r/R36S/comments/1u5kdmc/adding_games_to_the_r36s_shouldnt_feel_like_it/
- https://www.reddit.com/r/R36S/comments/1supwlb/wifi_manager_major_update_rtl8188eus_wifi_driver/
- https://lcdyk0517.github.io/dtbTools.html
