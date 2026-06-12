# RTS-1 → grblHAL — session handoff / status

Living status doc so this work can resume on another machine (or a fresh Claude
session). Last updated during bring-up, after first grblHAL flash.

## TL;DR
Reverse-engineered the Onefinity **RTS-1 Open-Loop** controller (STM32F401RCT6,
5× DRV8452, USB-C CDC, Modbus VFD) and built a custom **grblHAL** firmware for it.
It flashes, boots, enumerates over USB, and a sender (ncSender/gSender) connects.
Now in **hardware bring-up** — wiring up fans/motors and verifying the pin map.

## What works / is proven
- Full **DFU flash + verified restore** path (RDP0, BOOT0 button). Stock firmware
  backed up (v1.4.7 + v1.5.9) in `firmware/`.
- grblHAL builds: F401RC, **HSE 8 MHz** (confirmed: USB enumerates), USB-CDC,
  4 axes X/Y/Z/A + **dual-Y auto-square** (5 DRV8452), Modbus VFD + PWM spindle.
  Flash ~80% / RAM ~31%.
- Sender connects; jogging updates the DRO (software only — see below).

## Current bring-up state — NEXT STEPS (resume here)
Last change: `board_init()` (`grblhal-rts1/boards/rts1.c`) drives **PA15, PB15,
PC15 HIGH at boot** to replicate stock power-on (2 fans + a master logic enable).
Re-flash, then test in order:
1. **Fans**: USB only → do the 2 cooling fans turn on? (expect yes → PB15/PC15 confirmed)
2. **Motor power**: connect the motor PSU to the 8-pin connector (pins 5-8 = VM+,
   1-4 = GND), release the external e-stop. VM+ feeds the DRV8452s directly — no
   VM, no motion.
3. **Motor enable**: in the sender console set `$1=255` (hold enable) and `$4=1`
   (invert stepper-enable — DRV8452 enable is assumed active-high). Jog a few mm.
   Motors should at least **hold** (resist by hand). If they go dead, flip `$4`.
4. Once they move: jog X+/Y+/Z+/A+ individually, note **which motor moves + direction**
   → fix axis swaps + direction inverts ($3) in `boards/rts1_map.h` / settings.

## Open items / TODO
- **Axis↔driver order + directions**: provisional. Verify by jogging (step 4).
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

## Recovered pin map (see PIN_MAP.md for full + confidence)
- STEP ×5: PB0, PB2, PB8, PB10, PB13   | DIR ×5: PC0, PC1, PC2, PC3, PC4
- ENABLE ×5: PB1, PB5, PB9, PB12, PB14 | Modbus: USART1 PA9/PA10, DE PA8 (ISL3485)
- Spindle PWM: PA0 | USB: PA11/PA12 | I2C(EEPROM?): PB6/PB7 | ADC: PA1, PA4
- Fans: PB15, PC15 | Master enable: PA15 | Inputs(provisional): PA5/6/7,PB4,PC5/6/7,PC13/14

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
