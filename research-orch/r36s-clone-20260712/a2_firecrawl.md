## A2 Authority Digest

**Scrape tool:** Firecrawl MCP (`user-firecrawl-mcp`) was available and used for primary authority fetches and supplemental searches.

**URL status notes:**
- `retrogamecorps.com/2023/06/08/r36s-handheld-review-and-guide/` returned 404; used Retro Game Corps YouTube review (`1JazW_Rf0Ko`) and handhelds wiki instead.
- `wiki.batocera.org/r36s` has no page yet.
- `github.com/christianhaitian/arkos/wiki/Wifi` redirected to ArkOS Home (no dedicated WiFi wiki page); WiFi guidance taken from RG351MP FAQ (shared RK3326 ArkOS docs).
- `github.com/morrownr/8821cu` is 404; active repo is `morrownr/8821au-20210708` (RTL8811AU/RTL8821AU).

---

### R36S hardware (WiFi, board)

The R36S is an RK3326 vertical handheld clone ecosystem, not a single fixed board.

| Spec | Authority value |
|------|-----------------|
| SoC | Rockchip RK3326 (Cortex-A35, Mali-G31 MP2) |
| RAM | 1 GB DDR3L (official spec); clones may ship 512 MB or RK3128 fakes |
| Storage | 2× microSD (TF1 OS/roms, TF2 roms-only) |
| Screen | 3.5" IPS, 640×480, 4:3 |
| **WiFi** | **No** |
| Bluetooth | No |
| Video out | No |

Handhelds wiki explicitly lists **WiFi: no** and **Bluetooth: no**. File-transfer docs state: *"The R36S does not have built-in wifi"* and require a **compatible USB dongle + OTG adapter**, USB-C Ethernet, or phone USB tethering.

Clone variance is the main hardware trap: different panels, amplifiers, joysticks (including *"Invert Right Joystick"* DTBs), G80/G80C mainboards, 512 MB RAM units, and stock images that expose **no WiFi menu** or reject dongles. BOOT-partition **`.dtb` files** select panel/audio/joystick wiring; wrong DTB = wrong controls even if software mappings look correct.

Retro Game Corps (Nov 2023 video): budget RK3326 device (~$40), strong community firmware support (ArkOS path), but quality varies by seller/clone batch.

ArkOS main wiki (archived Dec 2025, superseded by dArkOS): RK3326 target, EmulationStation-FCAMOD + RetroArch, EASYROMS exfat partition, online updates, and **"Stability tweaks for RTL8188 and RTL8812/RTL8811 wireless chipsets."**

---

### Gamepad / controller persistence

#### Why mappings reset after reboot on R36S clones

1. **Wrong DTB / clone hardware profile** — Clones ship many panel and mainboard variants. Handhelds clones wiki: *"Lots of reports about audio output issues and inverted controls"* and DTB names like *"Clone Type 1 … Invert Right Joystick"*. If the kernel DTB does not match your board, axes/buttons are wrong at the driver level; UI remaps may appear to work until reboot or emulator launch.

2. **Post-update mismatch** — AeolusUX ArkOS-R3XS issue #95: after ArkOS R3XS V2.0 update, joysticks inverted with *"no remapping of the controller found in system settings"*; maintainer response: *"You might have a clone you just remap it depending on which system."*

3. **EmulationStation config never persisted** — ES stores pad layout in `es_input.cfg`. Community fix repo (`schoperena/R36S-FN-SELECT-FIX`) requires running **Start → Controller Settings → Configure Input** first; otherwise `es_input.cfg` is missing and mappings revert.

4. **Split config domains** — ArkOS uses **EmulationStation** (`es_input.cfg`) plus **RetroArch / RetroArch32** (`retroarch.cfg`, autoconfigs, per-core overrides). Fixing one layer does not fix the other; per-core overrides can reapply old bindings on boot.

5. **SD card / save failures** — Handhelds troubleshooting lists *"Emulator Settings Keep Resetting"* and save issues; cheap stock microSD cards are a known failure mode on R36S.

6. **Stock/EmuELEC clone firmware quirks** — Some clones map FN→Y, show 497 MB RAM in RetroArch, or lack proper input tooling.

**Remediation pattern (authority-backed):**
- Cycle correct **BOOT `.dtb`** for your clone type (handhelds clones + BOOT partition docs).
- **Options → Advanced → Reset EmulationStation Controls** (community guides), then re-run Configure Input.
- If DTBs fail: remap ES (SjslTech: *"Remap EmulationStation Controls in ArkOS K36 - Handy for Clones!"*) and per-emulator maps.
- Normalize FN/Select/hotkey IDs via `schoperena/R36S-FN-SELECT-FIX` script.

#### Correct persistent config paths (ArkOS / R36S)

| Layer | Path |
|-------|------|
| EmulationStation (system) | `/etc/emulationstation/es_input.cfg` |
| RetroArch (64-bit) | `~/.config/retroarch/retroarch.cfg` |
| RetroArch (32-bit) | `~/.config/retroarch32/retroarch.cfg` |
| Controller autoconfigs | `/usr/share/retroarch/autoconfig/udev`, `/usr/share/retroarch32/autoconfig/udev` (+ user autoconfig dirs if present) |
| Per-core/game overrides | under `~/.config/retroarch*/config/` (clear if they fight global settings) |
| Hardware/input at boot | BOOT partition `.dtb` files (not ES/RA configs) |
| Backups (script convention) | `~/backup_inputs_YYYYmmdd-HHMMSS/` |

Generic EmulationStation reference (`~/.emulationstation/es_input.cfg`) applies to Raspberry Pi builds; **ArkOS community tooling explicitly uses `/etc/emulationstation/es_input.cfg`.**

---

### ArkOS WiFi setup (internal + dongle)

**Internal WiFi:** None. All network access is external: USB WiFi dongle (most common), USB Ethernet, or phone USB tethering.

**Physical setup (handhelds + TeamXNL):**
- Use **OTG port** (bottom-right USB on R36S/R36H) via **USB-C → USB-A OTG adapter**.
- **Do not** use the left/charge-only port for dongles.
- Insert dongle before or at boot if detection fails.

**ArkOS native WiFi flow** (RG351MP/RK3326 FAQ, applies to R36S ArkOS builds):
1. Plug in a **compatible USB WiFi dongle**.
2. **Options → WIFI**.
3. Press **R1** to reach **+**, add SSID/password with **A**.
4. Confirm WiFi icon (top-right) or **Options → NETWORK INFO** for an IP.
5. For special characters in passwords: use RetroArch **Settings → WiFi**, or manual import (below).
6. **Enable Remote Services** (SSH/Samba) from Options when transferring files — handhelds notes this must be re-enabled **after each reboot**.

**Manual credential import:** place `wifikeyfile.txt` in `roms/tools` (or `roms2/tools` on dual-SD) with:
```
ssid="your ssid"
pass="your ssid password"
```
ArkOS imports at boot and deletes the file on success.

**Dongle compatibility:**
- ArkOS FAQ links a [compatible USB WiFi dongle list](https://github.com/retrogamehandheld/oga/wiki/Frequently-Asked-Questions#what-wifi-adapters-work) and reports **TP-Link Archer T2U Nano AC600** (2.4/5 GHz) works well.
- Handhelds wiki maintains a [compatible dongle spreadsheet](https://docs.google.com/spreadsheets/d/1gWxtr-GmwWop-_qGUq022RXxK2aTLpPg9Qra68TQLI8/edit?gid=0#gid=0) and recommends cheap RTL8188-class nano dongles + OTG.
- Reddit reports many random dongles fail; **802.11n** adapters often work where unsupported **AC** sticks do not.

**RTL8188FTV cheap-dongle driver (TeamXNL, ArkOS-specific):**
1. Flash/update official ArkOS image.
2. Download TeamXNL **RTL8188FTV** driver zip.
3. Copy extracted `XNL RTL8188FTV` folder to SD **`Tools`** partition folder.
4. Boot → **Options** (or theme-equivalent) → **XNL RTL81888FTV → Install Driver → Yes**.
5. Reboot, plug dongle into OTG, then use ArkOS WiFi menu.
6. Driver **not compatible with dArkOS** per TeamXNL (2025 note).

AeolusUX **ArkOS-R3XS** community image bundles WiFi drivers; official ArkOS may need TeamXNL or a known-good dongle.

---

### AC600 / Realtek driver notes

| Chip / product | Authority guidance |
|----------------|-------------------|
| **TP-Link Archer T2U Nano (AC600, RTL8821AU class)** | ArkOS FAQ: reported to work very well on ArkOS; 2.4 + 5 GHz. |
| **RTL8812 / RTL8811** | ArkOS ships stability tweaks (disabled USB/wireless power saving). |
| **RTL8188FTV / RTL8188FU** | Not in stock ArkOS for all units; use TeamXNL compiled ARM driver + installer in `Tools`. |
| **morrownr `8821cu`** | Repo gone (404). |
| **morrownr `8821au-20210708`** | Active out-of-tree driver for **RTL8811AU and RTL8821AU** (v5.12.5.2). README: kernel **6.14+** includes good in-kernel **rtw88** driver; on 6.14+ use `lwfinger/rtw88` instead. Remove old driver with `sudo sh remove-driver.sh` before switching. |
| **ArkOS kernel context** | ArkOS is Ubuntu 19.10-era; likely **older than 6.14**, so in-kernel rtw88 may not apply on stock ArkOS images — prefer FAQ-tested dongles (Archer T2U Nano) or compile/port morrownr driver for your exact kernel. |

**Practical AC600 guidance for R36S ArkOS:**
- First try **Archer T2U Nano** out of box (ArkOS FAQ authority).
- If `lsusb` shows 8821AU but no interface: morrownr `8821au-20210708` is the maintained out-of-tree path (not `8821cu`).
- Do **not** assume TeamXNL RTL8188FTV installer covers AC600/8821AU — it targets 8188FTV only.
- Reddit: many "AC" dongles fail on R36S; verify chipset against compatibility lists before buying.

---

### Source excerpts (short quotes + URLs)

- *"WiFi \| no"* — https://handhelds.wiki/R36S
- *"The R36S does not have built-in wifi but you can enable WiFi … Compatible Dongle + OTG adapter"* — https://handhelds.wiki/R36S_File_Transfer
- *"Lots of reports about audio output issues and inverted controls"* — https://handhelds.wiki/R36S_Clones
- *"You might have a clone you just remap it depending on which system it is you're trying to run."* — https://github.com/AeolusUX/ArkOS-R3XS/issues/95
- *"`sudo grep -E 'hotkeyenable|select' /etc/emulationstation/es_input.cfg`"* — https://github.com/schoperena/R36S-FN-SELECT-FIX
- *"You must have a compatible USB wifi dongle plugged in … TP-Link Archer T2U Nano AC600 … works very well with ArkOS."* — https://github.com/christianhaitian/arkos/wiki/Frequently-Asked-Questions---RG351MP
- *"Stability tweaks for RTL8188 and RTL8812/RTL8811 wireless chipsets."* — https://github.com/christianhaitian/arkos/wiki
- *"Copy the folder XNL RTL8188FTV … into the folder Tools on your SD-Card … Install Driver"* — https://www.teamxnl.com/installing-cheap-wifi-on-your-r36s-or-r36h/
- *"Linux Driver for USB WiFi Adapters that are based on the RTL8811AU and RTL8821AU Chipsets"* — https://github.com/morrownr/8821au-20210708
- *"The R36S is a budget handheld that packs some impressive quality for its $40 price point."* — https://www.youtube.com/watch?v=1JazW_Rf0Ko (Retro Game Corps)
