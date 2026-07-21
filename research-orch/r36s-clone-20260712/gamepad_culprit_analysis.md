# Gamepad Persistence Culprit Analysis — R36S K36 Clone (ArkOS4Clone)

**Device:** R36S K36 clone · ArkOS4Clone K36 build (~Image dated 2025-06-23)  
**Investigation date:** 2026-07-12  
**SD card scanned from Windows:** BOOT = `D:\` · EASYROMS = `E:\` (both mounted)

---

## Executive verdict

| Question | Answer |
|----------|--------|
| **Primary culprit** | **Failing/corrupt SD card — writes to the ext4 root partition are not surviving reboot** |
| **New SD required?** | **Very likely yes** — `FSCK0000.REC` on BOOT is hard corruption evidence; try software fixes only after a write-persistence test passes |
| **Software-only possible?** | Yes, *if* persistence test passes and symptom is limited to RetroArch 32 / wrong save workflow |

---

## Primary culprit: SD card filesystem failure (write persistence)

### Why this is #1 for *this* card

1. **`FSCK0000.REC` (925 KB) on `D:\` (BOOT)** — Windows `chkdsk` / FAT `fsck` recovery artifact. File header is `BM` (recovered bitmap). This is not normal on a healthy card.
2. **Kernel cmdline includes `fsck.repair=yes`** in `D:\extlinux\extlinux.conf` — the OS is configured to auto-repair filesystem damage on boot, consistent with prior unclean shutdowns or card degradation.
3. **Symptom pattern matches exactly** — user must reconfigure controller **every reboot**. That is the classic signature of `es_input.cfg` / RetroArch configs appearing to save in RAM but not committing to disk.
4. **Authority alignment** — ArkOS4Clone maintainer on [#277](https://github.com/lcdyk0517/arkos4clone/issues/277): *"Please check whether your SD card might be damaged."* Handhelds wiki and all three prior research legs (A1/A2/A3) rank SD corruption as the top persistence cause.
5. **Config lives where Windows cannot see it** — `es_input.cfg` is on **ext4 root** (`/dev/mmcblk1p2`), not on BOOT or EASYROMS. Windows scan found **zero** `es_input.cfg` / `retroarch.cfg` files — expected, but means we cannot confirm writes from PC; device-side test is mandatory.

### What is *not* supporting SD-as-culprit

- User might still have *other* settings that persist (themes, WiFi creds). If **nothing at all** fails to persist, SD is near-certain. If **only** gamepad fails, layer/save-path bugs rise in rank — run tests below to split these cases.

---

## Secondary culprits (ranked)

### 2. EmulationStation `es_input.cfg` never persisted (wrong workflow)

| Evidence | Detail |
|----------|--------|
| Community pattern | Mappings only stick after **Start → Controller Settings → Configure Input** (writes `/etc/emulationstation/es_input.cfg`) |
| Symptom | Configure Input wizard runs every boot; menus feel "unmapped" |
| This card | Cannot verify timestamp from Windows; must check on device |

**Definitive test:** After Configure Input, on device shell:
```bash
ls -la /etc/emulationstation/es_input.cfg
stat /etc/emulationstation/es_input.cfg
```
Reboot → run again. If timestamp/size revert or file missing → persistence failure (usually SD) or boot script deleting it.

---

### 3. ArkOS4Clone RetroArch 32 save bug (#277 / #272)

| Evidence | Detail |
|----------|--------|
| Official fix | [20260305 release](https://github.com/lcdyk0517/arkos4clone/releases/tag/20260305): RA "cannot save configuration after booting" → replace `firstboot.sh`, delete `.console` |
| #277 resolution | Maintainer: use **Configuration File → Save Current Configuration** (not generic save) for RA32 |
| This card | **No `firstboot.sh`** and **no `.console`** on BOOT — consistent with post-fix state *or* never applying OTA fix |

**Important:** This bug affects **RetroArch 32 in-game settings**, not necessarily the ES Configure Input wizard every boot. If menus are fine but PS1/PSP controls revert, this is your culprit.

**Definitive test:**
1. Open RetroArch 32 → change menu color → **Configuration File → Save Current Configuration**
2. Reboot → reopen RA32. Color persisted? If not → RA32 save path or SD.

---

### 4. Prior wrong DTB (`rf3536k3ka_wifi2.dtb`) — now reverted

| Evidence | Detail |
|----------|--------|
| Stale note | `D:\WIFI_Status_Summary.md` still documents `wifi2` DTB (prior WiFi session) |
| **Current live config** | `D:\extlinux\extlinux.conf` → **`FDT /rf3536k3ka.dtb`** (correct K36) |
| #372 | K36 clone DTB: `odroidgo3-joypad node: not found`, no internal WiFi — matches this hardware |

Wrong DTB causes **wrong/inverted buttons**, not typically "wizard every reboot" unless combined with autoconfig regeneration. DTB is **currently correct**; one clean remap pass still required after DTB correction.

**Definitive test:**
```bash
dmesg | grep -i fdt
cat /proc/device-tree/compatible 2>/dev/null | tr '\0' ' '
evtest   # press all buttons; reboot; evtest again — codes must match
```

---

### 5. Split config layers (ES vs RA64 vs RA32 vs per-core remaps)

| Layer | Path |
|-------|------|
| EmulationStation | `/etc/emulationstation/es_input.cfg` |
| RetroArch 64 | `~/.config/retroarch/retroarch.cfg` |
| RetroArch 32 | `~/.config/retroarch32/retroarch.cfg` |
| Per-core overrides | `~/.config/retroarch*/config/` remaps |

Fixing one layer does not fix others. Per-core overrides can make **one emulator** revert while others work.

**Definitive test:** Note *where* reset happens — ES menus only? One system? All systems? Narrows layer.

---

### 6. Partial-match K36 DTB (MD5 differs from stock)

| This card | Issue #372 stock |
|-----------|------------------|
| `rf3536k3ka.dtb` 107,106 bytes | 107,328 bytes |
| MD5 `5af86392bba11edb0f26fc43d2b26330` | MD5 `6c18b1e9fc295ce2d4dbd824f99ed795` |

ArkOS4Clone rebuild of K36 panel DTB. Buttons work per #372 reports, but `odroidgo3-joypad` / `amux-channel-mapping` absent — may cause autoconfig drift on some builds. **Secondary** to SD corruption given `FSCK0000.REC`.

---

## Ruled out or downgraded for this card

| Suspect | Status | Reason |
|---------|--------|--------|
| **`.console` reset loop** | Downgraded | No `.console` on BOOT when scanned |
| **Missing `firstboot.sh` causing daily reset** | Downgraded | Absence is normal after successful OTA per [#272 comment](https://github.com/lcdyk0517/arkos4clone/issues/272#issuecomment-4025030513) ("delete firstboot.sh too"); not a daily remap trigger |
| **Wrong DTB currently active** | Ruled out | `extlinux.conf` → `rf3536k3ka.dtb` |
| **es_input.cfg on EASYROMS** | N/A | ArkOS stores it on ext4 root, not E:\ |

---

## SD card scan results (2026-07-12)

### `D:\` (BOOT) — contents relevant to gamepad

| Item | Finding |
|------|---------|
| `extlinux/extlinux.conf` | `FDT /rf3536k3ka.dtb` ✓ |
| `rf3536k3ka.dtb` | 107,106 B · MD5 `5af86392bba11edb0f26fc43d2b26330` |
| `rf3536k3ka_wifi2.dtb` | Present but **not** active (leftover from WiFi attempt) |
| `FSCK0000.REC` | **925,696 B** — FAT recovery artifact (**corruption signal**) |
| `firstboot.sh` | **Missing** |
| `.console` | **Missing** |
| `boot.ini` | **Missing** (console-detect uses DTB identity on newer builds) |
| `es_input.cfg` | **Not on BOOT** (expected — lives on ext4) |

### `E:\` (EASYROMS)

- Only `tools/` + `System Volume Information` — normal empty EASYROMS layout.
- No `es_input.cfg` or `retroarch.cfg` (expected).

---

## Definitive tests (run on device)

Run in order; stop when a test fails — that failure is your culprit.

### Test A — Filesystem write persistence (decides SD vs software)

```bash
touch /tmp/persist_test_$(date +%s)
echo "test" >> /etc/emulationstation/es_input.cfg 2>&1 | tee /tmp/es_write_test.log
sync
ls -la /tmp/persist_test_* /etc/emulationstation/es_input.cfg
```
Reboot → repeat `ls`. **If files gone or unchanged after Configure Input → replace SD card.**

Also:
```bash
mount | grep mmcblk1p2
dmesg | grep -iE 'read-only|I/O error|mmc|ext4'
```
Look for `ro` (read-only) or I/O errors.

### Test B — ES mapping saved

1. Start → Controller Settings → **Configure Input** → map all buttons.
2. `stat /etc/emulationstation/es_input.cfg` — note mtime.
3. Reboot → `stat` again. **mtime must advance and file must exist.**

### Test C — RetroArch 32 explicit save (#277)

1. RetroArch 32 → visible change (menu color).
2. **Configuration File → Save Current Configuration** (exact menu path).
3. Reboot → verify. **If RA64 persists but RA32 doesn't → #277 workflow, not SD.**

### Test D — Input device stability (DTB)

```bash
evtest
# press every button; note device name and codes
# reboot; evtest again — codes must be identical
```

### Test E — Other settings persistence (SD smell test)

Change a non-gamepad setting (theme, WiFi SSID if used). Reboot. **If multiple setting types revert → SD.**

---

## Fix steps (minimal order — "configure once and remember")

### Phase 0 — Decide SD fate (do first)

1. Run **Test A** and **Test E** on device.
2. If writes fail or multiple settings revert:
   - Buy **SanDisk Extreme / Samsung Pro Plus** 128GB+ (avoid stock seller card).
   - **Full reflash** ArkOS4Clone image (not BOOT-only swap) with `dtb_selector_win32.exe` → **K36 (Origin Panel)** → `rf3536k3ka.dtb`.
   - Skip to Phase 2 after flash.

### Phase 1 — If persistence tests PASS (software-only path)

1. Confirm `D:\extlinux\extlinux.conf` has `FDT /rf3536k3ka.dtb` (already correct on this card).
2. Delete stale `D:\rf3536k3ka_wifi2.dtb` and `D:\FSCK0000.REC` after backup (optional cleanup).
3. On device: Options → Advanced → **Reset EmulationStation Controls** → reboot.
4. Start → Controller Settings → **Configure Input** → complete full mapping.
5. RetroArch 32: **Configuration File → Save Current Configuration**.
6. Optional: run [R36S-FN-SELECT-FIX](https://github.com/schoperena/R36S-FN-SELECT-FIX) to sync FN/Select/hotkey IDs.
7. Reboot and verify Tests B + C.

### Phase 2 — If RA32 still won't save after Phase 1

1. Download `firstboot.sh` from current [ArkOS4Clone release](https://github.com/lcdyk0517/arkos4clone/releases).
2. Copy to `D:\firstboot.sh`.
3. Delete `D:\.console` if it appears after a device boot.
4. Reboot device; after OTA/setup completes, remove `firstboot.sh` per maintainer guidance.
5. Repeat Configure Input + RA32 explicit save.

### Phase 3 — Ongoing hygiene

- Always shut down via **FN+Power → Quit** (never long-press kill).
- After fixing, backup `/etc/emulationstation/es_input.cfg` and `~/.config/retroarch32/retroarch.cfg` to PC.
- Consider upgrading firmware to **ArkOS4Clone ≥ 20260305** (RA save fixes) or latest **20260711** — current Image timestamp (2025-06-23) predates those fixes.

---

## New SD card vs software-only — decision matrix

| Observation | Verdict |
|-------------|---------|
| Test A write fails | **New SD + full reflash** |
| `FSCK0000.REC` + any other settings also revert | **New SD + full reflash** |
| Only RA32 in-game reverts; ES menus OK; Test A passes | **Software-only** — #277 save path + optional `firstboot.sh` |
| Configure Input wizard every boot; Test A passes | **Software-only** — ES workflow + check for script deleting `es_input.cfg` |
| `evtest` codes change between reboots | Fix DTB first (already on `rf3536k3ka.dtb`), then remap once |

**For this specific card:** `FSCK0000.REC` pushes strongly toward **new SD + full reflash**, then a single Configure Input pass. Software-only is worth **one** attempt only if Test A passes cleanly.

---

## Prior research cross-reference

| Source | Gamepad-relevant signal |
|--------|-------------------------|
| `a1_last30days.md` | #277 RA32 save; `firstboot.sh`/`.console` fix; stock SD #1 cause |
| `a2_firecrawl.md` | ES `es_input.cfg` path; DTB mismatch; split RA/ES layers |
| `a3_perplexity.md` | Ranked table: SD > DTB > ES not written > RA remaps |
| `master_report.md` | Combined playbook; Phase 0 = DTB + SD before remap |
| GitHub #372 | This K36 DTB profile; no internal WiFi; partial MD5 match |
| GitHub #277 | RA32 needs "Save Current Configuration"; maintainer suspects SD |
| ArkOS4Clone wiki §7 | Delete `.console` to **reset** mappings (not cause daily reset) |

---

## Stale artifact note

`D:\WIFI_Status_Summary.md` documents `rf3536k3ka_wifi2.dtb` as active. **Live `extlinux.conf` has been reverted to `rf3536k3ka.dtb`.** Treat the markdown file as historical; trust `extlinux.conf`.

---

## Sources

- https://github.com/lcdyk0517/arkos4clone/issues/277
- https://github.com/lcdyk0517/arkos4clone/issues/272
- https://github.com/lcdyk0517/arkos4clone/issues/372
- https://github.com/lcdyk0517/arkos4clone/releases/tag/20260305
- https://github.com/lcdyk0517/arkos4clone/wiki
- https://handhelds.wiki/R36S_Problems_and_Troubleshooting
- https://github.com/schoperena/R36S-FN-SELECT-FIX
- Local SD scan: `D:\`, `E:\` (2026-07-12)
