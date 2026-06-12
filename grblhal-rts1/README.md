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

## NOT yet flashed — open items before/at bring-up
1. **HSE 8 MHz** extracted from firmware; final proof = USB enumerates after flash.
2. **Provisional pins** (driver↔axis order, input roles) — verify by jogging /
   toggling at bring-up; remap in `rts1_map.h` as needed.
3. **Homing** is sensorless (no switches): design goal is to map the DRV8452 STALL
   outputs to grblHAL limit inputs — needs the stall-wiring RE (TBD).
4. First flash needs the **BOOT0 button** (USB DFU); restore-to-stock is proven.

Flash (in DFU mode):
```bash
dfu-util -a 0 -s 0x08000000:leave -D STM32F4xx/.pio/build/RTS1/firmware.bin
```
