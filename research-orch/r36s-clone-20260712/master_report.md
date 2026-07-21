# R36S Clone — Gamepad Persistence & WiFi Fix Playbook

**Question:** Why do gamepad controls reset every reboot on my R36S clone, and how do I get WiFi working (internal or USB AC600 dongle)?  
**Engines:** A1 last30days · A2 Firecrawl · A3 Perplexity  
**Date:** 2026-07-12

---

## Executive summary (read first)

Your two issues share a common root on R36S clones: **wrong hardware profile (DTB) + fragile SD storage + split config layers**. Most R36S clones have **no built-in WiFi** — you need a USB dongle on the **bottom-right OTG port** (left port is charge-only). If your unit is a rare V30/RK915 board with internal WiFi, that path only works with the **correct DTB** and recent **ArkOS4Clone ≥ 20260619** firmware.

**Gamepad resets** are usually not "you forgot to save" — they are: (1) cheap/corrupt SD card not persisting writes, (2) wrong `.dtb` for your clone panel/board so button IDs drift, (3) EmulationStation vs RetroArch configs saved in only one layer, or (4) on ArkOS4Clone specifically, a known bug where RetroArch 32 won't persist until you run **Save Current Configuration** and/or replace `firstboot.sh` + delete `.console` on the BOOT partition.

**WiFi with AC600:** "AC600" is a marketing label — identify the **actual chipset** with `lsusb`. TP-Link Archer T2U Nano (RTL8811AU/8821AU) is FAQ-tested on ArkOS, but many generic AC600 sticks fail on clone OTG (especially 5 GHz / high-power dongles causing dwc2 errors). The **safest path** is a **2.4 GHz RTL8188FTV** dongle + TeamXNL driver installer. If your AC600 shows in `lsusb` but no `wlan0`, you need out-of-tree drivers (`8821au`) or a community firmware like **ArkOS4Clone** / **dArkOSRE-R36**.

**Do this first (30 min):** Identify board → match DTB → replace SD card if anything won't stick → fix controls once → test WiFi with dongle in correct port.

---

## Answers

### 1. Why gamepad controls reset every reboot

| Cause | How to confirm | Fix |
|-------|----------------|-----|
| **Bad SD card** | Settings/saves also vanish; `touch` test fails | Replace with SanDisk/Samsung; reflash ArkOS |
| **Wrong DTB** | Inverted sticks, FN on wrong button, IDs change in `evtest` after reboot | Use [dtbTools](https://lcdyk0517.github.io/dtbTools.html) or Handhelds clone table; pick correct panel DTB in Options → Advanced |
| **ES config not saved** | `/etc/emulationstation/es_input.cfg` timestamp unchanged | Start → Controller Settings → **Configure Input** (not just in-game remap) |
| **RetroArch layer separate** | Menus OK, in-game wrong | In-game FN+X → Controls → **Save Core Remap**; use explicit **Save Current Configuration** for RA32 |
| **ArkOS4Clone RA32 bug** | Config appears saved but reverts | Replace `firstboot.sh` on BOOT partition; delete `.console`; reboot |
| **Per-core overrides** | One emulator reverts, others fine | Run `R36S-FN-SELECT-FIX --clean-overrides` |

### 2. Correct persistent config locations

| Layer | Path |
|-------|------|
| EmulationStation | `/etc/emulationstation/es_input.cfg` |
| RetroArch 64-bit | `~/.config/retroarch/retroarch.cfg` |
| RetroArch 32-bit | `~/.config/retroarch32/retroarch.cfg` |
| Autoconfigs | `/usr/share/retroarch*/autoconfig/udev/` |
| Hardware wiring | BOOT partition `.dtb` files |

Community fix script: [schoperena/R36S-FN-SELECT-FIX](https://github.com/schoperena/R36S-FN-SELECT-FIX) — syncs ES + RetroArch FN/Select/hotkey IDs.

### 3. Does my R36S clone have internal WiFi?

**Default: NO.** Handhelds wiki and ArkOS docs list WiFi as absent on standard R36S.

**Exceptions (check your board label):**
- **R36S-V30** (2025 revisions) — internal WiFi path; needed ArkOS4Clone **20260619** DTB fix
- **K36S / R36ULTRA / XF40H** — may have **RK915** internal WiFi; needs correct DTB + ArkOS4Clone ≥ 20260305
- **V21/V22** — unpopulated WiFi pads; possible solder mod (RTL8188ETV) but disables OTG dongle

**Quick test:** Boot without dongle → Options → WIFI. If networks appear, you have internal WiFi. Empty = dongle required.

### 4. Getting your USB AC600 dongle working

**Physical setup:**
1. USB-C → USB-A **OTG adapter** → **bottom-right port** (not left/charge port)
2. Plug dongle **before boot** if detection fails
3. Keep device **charged** — low battery can starve OTG power

**Diagnose (SSH or terminal):**
```bash
lsusb                    # see Realtek device? note 0bda:xxxx ID
dmesg | grep -iE 'wifi|rtl|8188|8821'
iwconfig                 # wlan0 present?
nmcli device wifi list   # networks visible?
```

**By chipset:**

| Your dongle | Stock ArkOS | Recommended fix |
|-------------|-------------|-----------------|
| RTL8188FTV / RTL8188EU | Often needs driver | TeamXNL installer → copy folder to SD `Tools/` → Install Driver → reboot |
| RTL8811AU / RTL8821AU (AC600) | **Not plug-and-play** | Try **TP-Link Archer T2U Nano** first; else flash **ArkOS4Clone** or compile `8821au` driver |
| Generic "AC600" mislabeled | Varies | `lsusb` — many are actually RTL8188 inside |

**If lsusb shows device but no wlan0:** driver missing. Easiest paths:
1. Buy a known-good **RTL8188FTV** nano dongle (~$5) + TeamXNL driver
2. Flash **ArkOS4Clone** (active clone support) or **dArkOSRE-R36**
3. Advanced: cross-compile [morrownr/8821au-20210708](https://github.com/morrownr/8821au-20210708) for your kernel

**Connect once driver works:** Options → WIFI → R1 (+) → add SSID/password → confirm IP under Network Info.

**Clone OTG quirk:** On Type 1/3/4 clones, **5 GHz / high-power AC600 dongles** can trigger dwc2 USB errors. Prefer **2.4 GHz only** dongles first.

---

## Recommended fix order (your two issues together)

### Phase 0 — Foundation (do before anything else)
1. Identify clone board (seller label, `dtbTools`, Handhelds [R36S Clones](https://handhelds.wiki/R36S_Clones) table)
2. Flash **ArkOS4Clone ≥ 20260619** or **dArkOSRE-R36** with **matching DTB**
3. Replace stock SD card with quality 128GB+ card if *any* settings fail to persist
4. Always shut down via **FN+Power** menu (not long-press kill)

### Phase 1 — Fix gamepad persistence (one time)
1. Options → Advanced → **Reset EmulationStation Controls** → reboot
2. Start → Controller Settings → **Configure Input** → map all buttons
3. Run [R36S-FN-SELECT-FIX](https://github.com/schoperena/R36S-FN-SELECT-FIX) script
4. In RetroArch: **Configuration File → Save Current Configuration**
5. Reboot and verify — if still broken, fix DTB (Phase 0) before remapping again
6. If on ArkOS4Clone: replace `firstboot.sh`, delete `.console` on BOOT partition

### Phase 2 — Fix WiFi
1. No dongle test → Options → WIFI (internal check)
2. Plug dongle in **right OTG port** → `lsusb` → identify chipset
3. **RTL8188FTV:** TeamXNL driver install (easiest, proven)
4. **AC600 (8811AU/8821AU):** if no wlan0, switch to ArkOS4Clone or RTL8188 dongle
5. Options → WIFI → connect → verify IP

---

## Risks, gaps, open questions

- **Unknown board variant** — without DTB match, both issues may persist regardless of remapping
- **AC600 chipset unknown** — run `lsusb` on device and share output for exact driver path
- **dArkOS vs ArkOS** — TeamXNL RTL8188 driver is **ArkOS-only**; dArkOS needs different approach
- **Remote Services** — SSH/Samba must be re-enabled after each reboot on ArkOS (separate from WiFi)
- **Speaker crackle with WiFi dongle** — known R36S PCB issue, not software-fixable

**Open question for you:** What firmware are you running (stock, ArkOS, ArkOS4Clone, dArkOS)? What does `lsusb` show with the AC600 plugged in?

---

## Appendix — research legs

### A1 Recency

See `a1_last30days.md` — key signals: ArkOS4Clone 20260305 RA32 save bug, 20260619 V30 WiFi DTB fix, dwc2/5GHz dongle issues on clone Type 1/3/4, `.console`/`firstboot.sh` reset path.

### A2 Authority

See `a2_firecrawl.md` — handhelds wiki confirms no built-in WiFi; ArkOS FAQ confirms Archer T2U Nano AC600 works; config paths and TeamXNL RTL8188FTV installer documented.

### A3 Perplexity

See `a3_perplexity.md` — full step-by-step playbook with decision trees for both issues; ranked root causes for gamepad persistence.
