# grblHAL for the RealTime CNC RTS-1

Custom grblHAL build for the Onefinity **RTS-1 Open-Loop** controller
(STM32F401RCT6, 5× DRV8452, RS-485 Modbus VFD, USB-C CDC).

These are the **deltas only** — the upstream grblHAL STM32F4xx driver is fetched
by `setup.sh` (pinned to a tested commit) and our files are applied on top, so
this repo stays small and the upstream stays updatable.

## Build
```bash
cd grblhal-rts1
./setup.sh                       # clones grblHAL + applies our board map/env
cd STM32F4xx
pio run -e RTS1                  # -> .pio/build/RTS1/firmware.bin
```

## What this delta contains
| File | Purpose |
|---|---|
| `boards/rts1_map.h` | RTS-1 pin map (reverse-engineered — see `../PIN_MAP.md`) |
| `platformio_env.ini` | `[env:RTS1]` build config |
| `setup.sh` | fetches pinned grblHAL and applies the above + a `driver.h` include |

## Current config (`[env:RTS1]`)
- MCU `genericSTM32F401RC`, `STM32F401RC_FLASH.ld`, **HSE 8 MHz**, USB-CDC console.
- **4 axes** X/Y/Z/A, **dual-Y auto-square** (`Y_AUTO_SQUARE`) → 5 DRV8452 motors.
- Spindle: **Modbus VFD** (Huanyang) on USART1 (PA9/PA10), RS-485 DE on PA8
  (`MODBUS_DIR_AUX`), plus a **PWM/laser** spindle on PA0.
- Flash ~80% / RAM ~31% of the F401RC.

## DB-25 I/O mapping

### Inputs — physical limit/home switches (`-limitsw` binary only)
The default binary homes **sensorless** (DRV8452 stall). The separate
`grblhal-rts1-limitsw-*.bin/.hex` binary instead homes off **physical switches**
wired to the DB-25 **isolated inputs** (active-low — switch the input to **IGND**).
One switch per axis; the auto-squared gantry uses two Y switches:

| DB-25 isolated input | Axis / motor |
|---|---|
| Input 1 | X |
| Input 2 | Y1 (left gantry motor) |
| Input 3 | Y2 (right gantry motor — auto-square) |
| Input 4 | Z |
| Input 5 | A |

(Input numbering follows the RealTimeCNC RTS-X I/O breakout — see
<https://docs.realtimecnc.com/io/>.) Inputs 6-8, the probe (J6) and tool-setter
are unchanged between both binaries.

### Outputs — 4 isolated relays (both binaries)
There are **4 isolated outputs** on the DB-25, each a **CPC1017N solid-state
dry-contact pair** (silent — no click; verify with a multimeter on continuity).
They are exposed as grblHAL **auxiliary outputs P1-P4**:

| grblHAL port | Output | DB-25 pins |
|---|---|---|
| **P1** | OUT0 | 9 & 10 |
| **P2** | OUT1 | 11 & 12 |
| **P3** | OUT2 | 19 & 20 |
| **P4** | OUT3 | 17 & 18 |

> Port **P0** is the MCU's on-board spindle-PWM pin (PA0), **not** a DB-25 output —
> leave it alone. The DB-25 relays are **P1-P4**.

**Manual control** (any output, from a G-code line or the MDI):
```
M64 P1   ; OUT0 on        M65 P1   ; OUT0 off
M64 P2   ; OUT1 on        M65 P2   ; OUT1 off
M64 P3   ; OUT2 on        M65 P3   ; OUT2 off
M64 P4   ; OUT3 on        M65 P4   ; OUT3 off
```

**Coolant (default out of the box):** Flood and Mist are bound to the first two
relays, so the sender's Flood/Mist buttons and the coolant M-codes just work:

| Function | G-code | Realtime toggle byte | Output |
|---|---|---|---|
| Flood | `M8` (on) | `0xA0` (toggle) | **OUT0 / P1** |
| Mist | `M7` (on) | `0xA1` (toggle) | **OUT1 / P2** |
| Both off | `M9` | — | OUT0 + OUT1 |

`M7`/`M8`/`M9` are modal G-code (`M9` = *all* coolant off). The `0xA0`/`0xA1`
realtime bytes (sent as a single character, no newline) **toggle one channel
independently** and bypass the planner buffer — this is what most senders' Flood/
Mist toggle switches use, so turning one off leaves the other untouched. OUT0/OUT1
also remain usable as manual `M64/M65 P1/P2` outputs (last write wins).

### Inverting outputs
Each relay's polarity can be flipped so its *idle* state is closed instead of open
(useful for normally-closed valves/contactors). An inverted output reads **closed at
idle** and **opens when switched on** — and the inversion applies to *both* the coolant
(`M7`/`M8`) and manual (`M64`/`M65`) drive of that relay.

| Setting | Inverts | Notes |
|---|---|---|
| **`$15`** "Invert coolant outputs" | Flood (OUT0), Mist (OUT1) | The intuitive one for coolant — Flood/Mist toggles |
| **`$372`** "Invert I/O Port outputs" | any of OUT0–OUT3 | Generic per-output invert. Its `Aux N` labels are *function* numbers: **Aux 2 = OUT0, Aux 3 = OUT1, Aux 4 = OUT2, Aux 5 = OUT3** (Aux 0/1 are the on-board PA0/PA8 pins, not DB-25 outputs) |

For OUT0/OUT1 either setting works and they don't stack (an output is inverted if `$15`
*or* `$372` asks for it). OUT2/OUT3 use `$372` only.

## NOT yet flashed — open items before/at bring-up
1. **HSE 8 MHz** extracted from firmware; final proof = USB enumerates after flash.
2. **Provisional pins** (driver↔axis order, input roles) — verify by jogging /
   toggling at bring-up; remap in `rts1_map.h` as needed.
3. **Homing** is sensorless (no switches): design goal is to map the DRV8452 STALL
   outputs to grblHAL limit inputs — needs the stall-wiring RE (TBD).
4. First flash needs the **BOOT0 button** (USB DFU); restore-to-stock is proven.

Flash (in DFU mode). Use a **download-only** command and power-cycle afterwards —
the `:leave` variant can hang on some hosts (notably macOS):
```bash
dfu-util -a 0 -s 0x08000000 -D STM32F4xx/.pio/build/RTS1/firmware.bin
```
