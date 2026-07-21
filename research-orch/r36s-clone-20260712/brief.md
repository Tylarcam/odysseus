# Research Brief — R36S Clone Troubleshooting

## Topic / Question

How to fix two persistent issues on an **R36S clone** (RK3326 handheld retro gaming device running ArkOS / JELOS / similar Linux firmware):

1. **Gamepad controls reset on every reboot** — user must reconfigure button mappings each restart; need root cause and permanent fix.
2. **WiFi not working** — verify whether this clone has internal WiFi hardware; if not, configure a **USB WiFi AC600** dongle (Realtek RTL8811AU / RTL8821AU chipset common on AC600 adapters).

## Audience / Use

Personal device repair — actionable fix steps, not product review.

## Must-Answer Questions

1. Why do R36S clone gamepad/button mappings fail to persist across reboots? (common causes: wrong config path, read-only overlay, emulator-specific vs system-wide mapping, ArkOS vs stock firmware differences)
2. What is the **correct persistent config location** for gamepad mappings on R36S clones (ArkOS, AmberELEC, JELOS, ROCKNIX)?
3. Step-by-step fix for gamepad persistence — including `retroarch.cfg`, `emulationstation` controller config, `es_input.cfg`, and any clone-specific quirks.
4. Does the standard R36S / R36S clone board include **built-in WiFi** (which chip, which firmware builds enable it)?
5. How to identify WiFi hardware on-device (`lsusb`, `iwconfig`, `dmesg`, `/proc/net/wireless`)?
6. How to get a **USB AC600 WiFi dongle** working on ArkOS/R36S — driver (8821cu, 8812au), `wifi.sh`, NetworkManager, or manual wpa_supplicant steps?
7. Which AC600 chipset variants work out-of-box vs need driver install on RK3326 handheld firmware?
8. Recommended firmware/OS for this clone if stock image lacks WiFi drivers?

## Authority URLs

- https://github.com/christianhaitian/arkos/wiki
- https://github.com/christianhaitian/arkos/wiki/Wifi
- https://github.com/christianhaitian/arkos/wiki/ArkOS-Emulators-and-Ports-information
- https://retrogamecorps.com/2023/06/08/r36s-handheld-review-and-guide/
- https://wiki.batocera.org/r36s
- https://www.reddit.com/r/SBCGaming/search/?q=r36s+wifi
- https://www.reddit.com/r/SBCGaming/search/?q=r36s+controller+reset
- https://handhelds.wiki/R36S
- https://github.com/morrownr/8821cu (common AC600 driver)

## Recency Keywords

R36S clone, R36S wifi, R36S gamepad reset, R36S controller mapping, ArkOS wifi dongle, AC600 RTL8821, R36S reboot controller, es_input.cfg, retroarch autoconfig, RK3326 wifi

## Synthesis Angle

Reconcile community reports (Reddit, forums) with official ArkOS wiki guidance to produce a **single ordered troubleshooting playbook**: (A) diagnose gamepad persistence, (B) diagnose internal vs USB WiFi, (C) enable AC600 dongle if needed.

## Category

`howto`

## Session ID

`rp-r36s-clone-20260712`

## Owner

`tylarcam`
