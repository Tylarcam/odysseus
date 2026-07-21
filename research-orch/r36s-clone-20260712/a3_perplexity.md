## A3 Perplexity Digest

**Research method:** Odysseus `POST /api/research/start` with `research_engine=perplexity_agent` failed (API token lacks scope-aware research route). Fallback: Perplexity deep-research MCP + Firecrawl/web sources. Raw metadata saved to `a3_perplexity_raw.json`.

---

### Findings (numbered, cited)

1. **Controller mappings live in two layers** — EmulationStation (`es_input.cfg`) for menus and RetroArch (`retroarch.cfg`, autoconfigs, core/game remaps) for in-game input. A "reset" may affect only one layer. [1][2]
2. **Most common persistence failure: SD card / filesystem** — If the card is corrupt or mounted read-only after unsafe shutdown, `es_input.cfg` and RetroArch remaps appear to save but revert on reboot. [1]
3. **DTB/panel mismatch is a top clone-specific cause** — Wrong panel DTB (Screen V1–V4, Origin Panel) can change input device names/IDs between boots, invalidating saved mappings. [3][4]
4. **FN/Hotkey vs Select conflicts are endemic on R36S** — FN mapped as Select or missing `hotkeyenable` in ES causes menus and hotkeys to break; community script fixes ES + RetroArch + autoconfigs together. [2]
5. **Many R36S clones ship without internal WiFi** — Networking requires a USB dongle on the **OTG port** (bottom-right on R36S/R36H); the left port is charge-only. [5][6]
6. **Cheap RTL8188FTV dongles are the proven path on official ArkOS** — TeamXNL provides a Tools-folder installer; avoid "AC600/1200M/WiFi-6/free driver" dongles. [5][6]
7. **RTL8811AU/8821AU/8812AU (AC600 class) are NOT plug-and-play on stock ArkOS** — Need out-of-tree modules (`8821au`, `8812au`); `lsusb` may show device but `iwconfig` shows no interface. [1][7][8]
8. **Internal WiFi models can break after ArkOS update** — Restoring a known-good DTB on the boot partition often fixes WiFi that worked before an update. [1][3]
9. **AeolusUX ArkOS-R3XS community build** includes broader dongle driver support; official ArkOS prioritizes stability over exotic chipsets. [3][5]
10. **Low battery can mimic WiFi failure** — R36S step-up converter may not supply 5 V to OTG under load; plug in charger and retest. [5]

---

### Gamepad persistence — root causes ranked

| Rank | Root cause | Signal |
|------|-----------|--------|
| 1 | SD card read-only / corruption | `touch ~/.emulationstation/es_input.test` fails; remaps don't stick |
| 2 | Wrong DTB / panel variant | `evtest`/`jstest-sdl` button IDs change between reboots |
| 3 | ES config not written | `es_input.cfg` timestamp unchanged after Configure Input |
| 4 | RetroArch remaps not saved | Menus OK, in-game controls revert; check `~/.config/retroarch*/` |
| 5 | Per-core/game overrides | Global fix works once, specific emulator reverts |
| 6 | FN/Select/hotkey collision | FN acts as Select; FN+X menu fails [2] |
| 7 | Manual XML edit broke ES | ES regenerates defaults on parse error [1] |

---

### WiFi — internal vs dongle decision tree

```
Boot ArkOS → Options → WIFI (no dongle)
├─ Networks appear → INTERNAL WiFi (likely OK)
│   └─ Broke after update? → Replace boot DTB with pre-update copy [3]
├─ No devices / empty scan → NO internal WiFi OR bad DTB
│   └─ Plug dongle in BOTTOM-RIGHT OTG port + USB-C→A adapter
│       ├─ lsusb shows Realtek device?
│       │   ├─ YES + iwconfig shows wlan0 → Options → WIFI → Connect
│       │   └─ YES + NO wlan0 → DRIVER MISSING (see playbook step 8)
│       └─ NO lsusb entry → wrong port, bad adapter, or dead dongle [5]
```

**Chipset quick reference:**

| Chipset | Stock ArkOS | Recommended action |
|---------|-------------|-------------------|
| RTL8188FTV / RTL8188EU | Partial / OOB on some | TeamXNL installer or buy RTL8188FTV dongle [5] |
| RTL8811AU / RTL8821AU | Not included | Use AeolusUX build, or compile/load `8821au` [7] |
| RTL8812AU | Not included | Compile/load `8812au` [8] |
| Internal (WiFi model) | DTB-dependent | Match panel DTB; restore if post-update break [3] |

---

### Step-by-step fix playbook

#### Part A — Gamepad mappings that reset

1. **Safe shutdown** — Hold FN+Power (ArkOS) before power-off to avoid SD corruption.
2. **Verify hardware stability** — SSH in, run `evtest`, press all buttons; reboot and confirm same codes. If codes drift, fix DTB first: Options → Advanced → choose correct panel/DTB (or use AeolusUX DTB selector). [3][4]
3. **Check filesystem writable** — `touch ~/.emulationstation/es_input.test`; if error, reflash ArkOS to a quality SD card.
4. **Reset ES controls cleanly** — Options → Advanced → **Reset EmulationStation Controls** (reboots). Then Start → Controller Settings → Configure Input. [4]
5. **Confirm ES saved** — `ls -la ~/.emulationstation/es_input.cfg` and `/etc/emulationstation/es_input.cfg`; timestamp should update.
6. **Fix FN/Select/hotkey (R36S-specific)** — Clone [schoperena/R36S-FN-SELECT-FIX](https://github.com/schoperena/R36S-FN-SELECT-fIX): run as user, then `sudo ./r36s-fn-select-fix.sh`, reboot. Defaults: FN=12, SELECT=16, MENU(X)=2. [2]
7. **Persist RetroArch in-game** — In-game FN+X → Quick Menu → Controls → save **Core Remap** (or Game Remap). Clear stale overrides: `./r36s-fn-select-fix.sh --clean-overrides`. [2]
8. **Backup working configs** — Copy `es_input.cfg`, `retroarch.cfg`, and remap folders to PC before ArkOS/DTB updates.

#### Part B — WiFi diagnosis and enable

1. **Identify WiFi type** — No dongle: open Options → WIFI. Networks visible = internal; empty = dongle required (most clones). [5]
2. **Use correct port** — Dongle → USB-C OTG adapter → **bottom-right** port only. [5][6]
3. **Terminal diagnostics (SSH)**:
   ```bash
   lsusb
   dmesg | grep -iE 'wifi|wlan|rtl|8188|8821'
   iwconfig
   lsmod | grep -iE '8188|8821|8812|rtl8'
   nmcli device status
   nmcli device wifi list
   ```
4. **Interpret results:**
   - No `lsusb` entry → port/adapter/dongle hardware issue.
   - `lsusb` + no `wlan0` → install/load driver (step 5–8).
   - `wlan0` + empty scan → reboot with dongle inserted; check battery/charger. [5]
5. **RTL8188FTV cheap dongle (recommended)** — Flash latest official ArkOS; download TeamXNL driver; copy `XNL RTL8188FTV` folder to SD `Tools/`; Options → XNL RTL8188FTV → Install Driver → reboot → connect via Options → WIFI. [5]
6. **RTL8188EU already works OOB?** — Skip installer if dongle connects without it; confirm with `iwconfig`. [5]
7. **Internal WiFi broken after update** — Mount SD on PC; backup boot partition; replace `*.dtb` with pre-update copy from vendor/community pack; reboot. [1][3]
8. **RTL8811AU / RTL8821AU / RTL8812AU (AC600)** — Stock official ArkOS unlikely to support. Options (easiest→hardest):
   - Flash **AeolusUX ArkOS-R3XS** (community; may include Realtek drivers). [3]
   - On-device: clone morrownr `8821au` or `8812au`, cross-compile for ArkOS kernel (advanced). [7][8]
   - After module load: `sudo modprobe 8821au` (or `8812au`), verify `wlan0`, then Options → WIFI.
9. **Connect** — Options → WIFI → Connect to new WiFi connection → select SSID → password → verify under Current Network Info.
10. **Known quirks** — R36S speaker crackle with WiFi dongle is a PCB design issue (not fixable in software); R36H less affected. [5]

---

### Contradictions / uncertainty

- **Reddit claims MT7601/MT7610 dongles** work on some ArkOS builds while RTL8188 fails — conflicts with TeamXNL's RTL8188FTV focus; chipset varies by seller and firmware fork. [6]
- **"AC600" dongles are often mislabeled** — Many cheap sticks use RTL8188, not 8811AU; always verify with `lsusb` (ID `0bda:…`) before chasing 8821au drivers.
- **Odysseus Perplexity agent unavailable via API token** — research route not exposed to scoped tokens; MCP Perplexity used instead.
- **dArkOS vs ArkOS** — TeamXNL driver explicitly incompatible with dArkOS; use official ArkOS or AeolusUX. [5]
- **Internal WiFi on "WiFi model" R36S** — Some units advertise WiFi but need correct DTB; not all clones match marketing.

---

### Sources

1. Perplexity deep-research synthesis (MCP `perplexity_research`, 2026-07-12) — R36S/ArkOS controller + WiFi stack analysis
2. [schoperena/R36S-FN-SELECT-FIX](https://github.com/schoperena/R36S-FN-SELECT-FIX) — FN/Select/RetroArch fix script
3. [AeolusUX/ArkOS-R3XS](https://github.com/AeolusUX/ArkOS-R3XS) — Community R36S ArkOS with broader hardware support
4. [AeolusUX/ArkOS-R3XS#95](https://github.com/AeolusUX/ArkOS-R3XS/issues/95) — Reset EmulationStation Controls for inverted sticks
5. [TeamXNL — Installing Cheap WiFi on R36S/R36H](https://www.teamxnl.com/installing-cheap-wifi-on-your-r36s-or-r36h/) — RTL8188FTV driver installer, OTG port, WiFi manager walkthrough
6. [Reddit r/SBCGaming — cheap WiFi dongles for R36S](https://www.reddit.com/r/SBCGaming/comments/18pgngw/very_cheap_wifi_dongle_that_works_on_the_r36s/)
7. [morrownr/8821au](https://github.com/morrownr/8821au) — RTL8811AU/RTL8821AU Linux driver
8. [morrownr/8812au](https://github.com/morrownr/8812au) — RTL8812AU Linux driver
