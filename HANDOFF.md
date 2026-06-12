# RTS-1 → grblHAL — session handoff / status

Living status doc so this work can resume on another machine (or a fresh Claude
session). Last updated during bring-up, after first grblHAL flash.

## TL;DR
Reverse-engineered the Onefinity **RTS-1 Open-Loop** controller (STM32F401RCT6,
5× DRV8452, USB-C CDC, Modbus VFD) and built a custom **grblHAL** firmware for it.
It flashes, boots, enumerates over USB, a sender connects, and **the motors now
energize, hold, and jog** (fans + steppers working). Down to calibration/tuning.

**KEY DISCOVERY:** the 5 DRV8452s are in **SPI interface mode** — outputs stay
Hi-Z until configured over SPI (EN_OUT + current). grblHAL now does this in
`board_init()` (boards/rts1.c). This also corrected the pin map (see below).

## What works / is proven
- Full **DFU flash + verified restore** path (RDP0, BOOT0 button). Stock firmware
  backed up (v1.4.7 + v1.5.9) in `firmware/`.
- grblHAL builds: F401RC, **HSE 8 MHz** (confirmed: USB enumerates), USB-CDC,
  4 axes X/Y/Z/A + **dual-Y auto-square** (5 DRV8452), Modbus VFD + PWM spindle.
  Flash ~80% / RAM ~31%.
- Sender connects; jogging updates the DRO (software only — see below).

## Current bring-up state — NEXT STEPS (resume here)
Motors energize/hold/jog. `board_init()` (`grblhal-rts1/boards/rts1.c`) now:
- drives **PA15 LOW** = master enable (rail + fans on; active-low, CONFIRMED), and
  PB15/PC15 HIGH (board straps);
- sets up **SPI1** and configures all 5 **DRV8452** drivers: VREF_INT_EN, microstep
  (1/16), current (CTRL11 TRQ_DAC / CTRL10 ISTSL), then **EN_OUT** — with read-back
  verify + retry per driver (a dropped frame was leaving a driver dark).
Current is `RTS1_DRV_RUN_CURRENT` / `RTS1_DRV_HOLD_CURRENT` in rts1.c (tune there).

NEXT:
1. **Steps/mm calibration** ($100–$103): drivers are at 1/16 microstep. Command a
   known distance, measure, adjust.
2. **Axis direction/mapping**: Z dir + Y2 ganged dir are now baked as defaults
   ($3=4, $8=2). Verify X/Y/Z/A each jog the correct way + correct motor.
3. **Run `$RST=$`** after flashing to load the new compiled defaults (accel 500,
   max rate 5000, travel, inverts) — NVS keeps old values otherwise.
4. **Driver fault auto-recovery**: a stall (e.g. Y racking) latches a DRV8452 off
   until re-init (power-cycle). TODO: small DRV8452 plugin to re-assert EN_OUT on
   nFAULT + expose current/microstep as live `$` settings.

## Open items / TODO
- **Axis↔driver order + directions**: provisional. Verify by jogging.
- **Homing is sensorless (no limit switches)**: stock uses DRV8452 stall detection
  (`stall_thresholds`). grblHAL's native sensorless homing is Trinamic-only, so plan
  is to map DRV8452 STALL outputs → grblHAL limit inputs. **Needs RE** (find stall
  pins + threshold mechanism). The current limit pins (PC5/6/7, PB4) are GUESSES —
  ignore the limit indicator colors for now; disable hard limits/homing (`$21=0 $22=0`).
- **E-stop = motor-power loss** (no signal wire), sensed via ADC on **PA1 or PA4**
  (VM voltage). Optional grblHAL plugin later: alarm on VM drop.
- **Modbus VFD**: DE on PA8 (AUXOUTPUT1, MODBUS_DIR_AUX=1) — verify with a scope
  during a Modbus frame; confirm VFD type (currently Huanyang) and `$` addr.
- **Travel defaults** set: X440 Y440 Z110 (apply via `$RST=$` or `$130/$131/$132`).

## Recovered pin map (CORRECTED at bring-up via DRV8452 SPI RE)
- STEP ×5: PB0, PB2, PB8, PB10, PB13   | DIR ×5: **PB1, PB5, PB9, PB12, PB14**
- **DRV8452 SPI**: SPI1 PA5=SCK PA6=MISO PA7=MOSI; **CS ×5 = PC0,PC1,PC2,PC3,PC4**
  (active-low). No GPIO stepper-enable — output-enable is SPI EN_OUT (CTRL1 bit7).
  SPI mode 1, 8-bit, MSB, /16. Interface strap: PC14 LOW = SPI.
- Modbus: USART1 PA9/PA10, DE PA8 (ISL3485) | Spindle PWM: PA0 | USB: PA11/PA12
- Master enable: **PA15 (active-LOW)** | board straps: PB15, PC15 (HIGH)
- Limits/inputs (provisional, mis-reading — see TODO): PB4, PC5/6/7, PC13
  NOTE: prior map had DIR on PC0-4 and "enable" on PB1/5/9/12/14 — BOTH WRONG.

## Set up a new machine (e.g. garage laptop)
```bash
# tools
brew install dfu-util
pip3 install --user platformio        # or: brew install platformio

# get the project
git clone git@github.com:siganberg/grblHal.rts-1.git
cd grblHal.rts-1

# build grblHAL (fetches pinned upstream + applies our board files)
cd grblhal-rts1 && ./setup.sh && cd STM32F4xx && pio run -e RTS1

# flash (controller in DFU mode: hold BOOT0 + plug USB-C):
../../scripts/flash-grblhal.sh
# restore stock:  ../../scripts/restore-stock.sh         (v1.5.9; or `1.4.7`)

# (optional) RE tooling for firmware analysis:
cd .. && python3 -m venv .venv && ./.venv/bin/pip install capstone pyserial
```

## Resuming with a fresh Claude session
Claude's conversation + memory are per-machine and don't sync. On the new machine,
start Claude in the cloned repo and tell it: *"read HANDOFF.md, README.md, and
PIN_MAP.md to get up to speed on this project."* The git log is the progress trail.
