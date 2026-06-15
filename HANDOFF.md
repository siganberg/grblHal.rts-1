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

### Settings now MATCH STOCK (from RealTimeCNC config UI), in env + rts1.c
- Microstep **1/16** (the "resonance" was a bad Y2 connector, since fixed). CTRL2=0x06.
- **Steps/mm = stock "Stepper Resolution" x 16** (UI value is FULL-STEP res):
  X=20x16=**320**, Y=**320**, Z=50x16=**800**. Verified 100 mm ~= 100 mm.
  (Cross-check: 5715 mm/min x 320 / 60 = 30.5 kHz = UI "Max Step Rate". ✓)
- Travel 420/420/110, max rate 5715/5715/3000 mm/min, accel 208 mm/sec^2
  (=750000 mm/min^2), Z reversed ($3=4), $8=0 — all DEFAULT_* in the env.
- **Current**: DRV8452 PWP pkg = 4 A full-scale = **2.8 A RMS = TRQ_DAC 0xFF**.
  We use RUN=0xC0 (~2.1 A) / HOLD=0x40 in rts1.c (0xFF tripped OCP on X/Y).
- spindle: all-VFD + quiet **on/off default** (NOT PWM - PA0's timers TIM5/TIM2 are
  grblHAL's stepper/RPM timers, so a PA0 PWM spindle hangs boot).

### KNOWN ISSUE - X/Y thermal dropout under sustained running
At 0xC0 (~2.1 A, below stock's 2.8 A) X/Y still cut out after ~9 min. Stock runs
2.8 A for hours, so the difference is likely **cooling** (fan drive) not current.
NEXT: confirm thermal (feel X/Y chips after a dropout; check both fans), then RE
how stock drives the fans (we just hold PB15/PC15 high; stock may PWM/run harder).

### E-STOP (motor-power monitor) - SOLVED (detection + auto-recovery both work)
rts1.c polls the DRV8452 over SPI ~10 Hz (`rts1_realtime` in boards/rts1.c):
- **VM lost -> grblHAL e_stop alarm: WORKS** (FAULT reg 0x00 bit5 UVLO = 0xA0).
- **Auto-recovery now WORKS**: release e-stop -> motors re-energize on their own,
  no MCU reboot, then click reset to clear the alarm. Confirmed over many cycles +
  boot-order (connect USB first, then turn on PSU -> motors power). Matches stock feel.
- **KEY INSIGHT that cracked it**: the e-stop cuts the DRV8452 **logic/VCC supply too**
  (not just motor VM). While e-stop is held the driver chips are **fully dark** and
  every SPI read returns **0x00** - which looks like "no fault" but is just an
  unpowered chip. The old recovery trusted the FAULT reg, saw 0x00, tried to
  reconfigure dead chips, and silently "succeeded" into nothing.
- **The fix** (`rts1_realtime` faulted branch): don't trust FAULT while dark. Probe
  **liveness** - write a sentinel (CTRL3=0x3C) and read it back; only a powered chip
  echoes it. While dark, wait quietly. Once the chip is alive + stable (~300 ms), run
  `rts1_recover_drivers` = PC15 reset pulse + **verified** per-driver config (read-back
  CTRL1==0x8F), and release the e-stop ONLY when all 5 verify EN_OUT on; else retry.
- **Register READS DO work** (earlier "reads return status byte" was wrong). Proven by
  `$DRV` (dumps all 5 drivers' regs). This made read-back verify + the liveness probe
  + the snapshot idea all viable - no logic analyzer needed after all.
- **`$DRV` console command**: dumps F/C1/C2/C3/C5/C6/C10/C11/C13 for all 5 drivers.
  Gated with the rest of the diagnostics behind `RTS1_DIAG` (boards/rts1.c, =1 now).
- ncSender debug-log dir: `~/Library/Application Support/ncSender/logs/`.

NEXT (besides e-stop + thermal):
1. **Steps/mm: DONE** (320/320/800, verified 100 mm). Fine-tune microns later.
2. **Axis direction/mapping**: $3=4 (Z), $8=0 (Y2 ganged) are baked defaults. Verify
   each axis jogs correct way + correct motor. ($8 was 2, set to 0 per bring-up.)
3. **Run `$RST=$`** after flashing to load compiled defaults (NVS keeps old else).

## BUILD GOTCHA - boards/rts1.c exists in TWO places (sync before building!)
`grblhal-rts1/boards/rts1.c` is the tracked SOURCE; `setup.sh` copies it to
`grblhal-rts1/STM32F4xx/boards/rts1.c` (gitignored) which is what `pio run` actually
compiles. **Editing the source alone does NOT reach the build** - it silently uses the
stale copy (flash verifies OK but new behavior is absent). After editing, re-sync:
`cp grblhal-rts1/boards/rts1.c grblhal-rts1/STM32F4xx/boards/rts1.c` (or re-run setup.sh),
then verify: `strings .pio/build/RTS1/firmware.elf | grep <new-string>`. (Same for rts1_map.h.)

## Quieter drivers (open) - RE answered the "how", needs stock's CTRL5/CTRL6 bytes
Disassembly (both v1.4.7 + v1.5.9, identical) shows our DRV8452 config already MATCHES
stock for CTRL13=0xFE, CTRL3=0x3C, CTRL1=0x0F->0x8F, CTRL2=0x06 (1/16). Stock does NOT
touch CTRL4/7/8/9 (no secret decay register). The only gap: stock writes a per-driver
**CTRL5/CTRL6** stall/"SmartTune" value (we leave them at reset defaults 0x03/0x20, seen
via `$DRV`). That + stock's higher current (2.8 A vs our 2.1 A) is the sound difference.
Run/hold current (CTRL11/CTRL10) + CTRL5/6 are host-supplied bytes (no amps formula in fw)
-> get them via the **snapshot** (no-config build + `$DRV` reads stock's live values).

## Flashing (now bullet-proof + fast, `scripts/`)
`flash-grblhal.sh` auto-enters DFU with no BOOT0: it closes whatever app holds the
CDC port (`lsof`→kill ncSender) and sends `$DFU` over serial (held-open fd, retries).
`RTS1_FAST=1` skips read-back verify for quick iteration; `RTS1_NO_KILL=1` /
`RTS1_NO_AUTODFU=1` to opt out. ncSender log dir: `~/Library/Application Support/ncSender/logs/`.

## Sensorless stall homing - DONE (X/Y auto-square/Z working; A configured/untested)
grblHAL's native sensorless homing is Trinamic-only, so this is a custom board module
in `boards/rts1.c`. KEY HW FACT: **nFAULT is a SHARED line** (PC5, all 5 DRV8452s
OR-tied) - so the hardware-pin path can't tell axes apart and breaks ganged-Y. Instead:
- Enable DRV8452 stall per driver: `EN_STL` (CTRL4=0x59) + a 12-bit `STALL_TH`
  (CTRL5/6). Stall latches `FAULT` reg (0x00) **bit2** and pulls nFAULT low.
- **Override `hal.homing.get_state`** to read each homed axis's OWN driver stall over
  SPI: axis->driver {X:0, Y1:1, Y2:2, Z:3, A:4}; Y1->`.a`, Y2->`.b` so grblHAL
  auto-squares the gantry. (homeGetState reads GPIO directly, so override homing.get_
  state, NOT limits.get_state.)
- Latch-clear hooks (cycle start / each phase / completion) so pull-off + locate work.
- Per-axis `STALL_TH`: X/Y/A=140 (belt), Z=230 (leadscrew - loaded TRQ ~140 vs no-load
  ~300). Tune live with `$MD=<drv>` + `$STH=<val>` (RTS1_DIAG build); watch the 5Hz MON
  stream. STALL_TH is speed-dependent - re-tune if you change `$24/$25`.
- **No physical switches**: `hal.limits.get_state` is overridden to report limits CLEAR
  (sender indicators stay green; the phantom pins were floating/shared-nFAULT).
- Baked defaults (NVS doesn't persist): `$5`(invert, cosmetic now), `$22=79`, `$20=1`,
  `$40=1`. Diagnostics gated behind `RTS1_DIAG` (=0 ships quiet; =1 for re-tuning).

## Open items / TODO
- **Axis↔driver order + directions**: provisional. Verify by jogging.
- **A-axis homing**: configured (driver 4, STALL_TH=140) but untested (no A motor).
- **NVS persistence**: settings don't survive reboot on their own (flash-NVS not
  working?) - we baked the important defaults as a workaround. Worth fixing properly.
- **E-stop = motor-power loss**: DONE via SPI UVLO poll + auto-recovery (see below).
- **Modbus VFD (H100)**: scaffolded (MODBUS_ENABLE=2, all VFD types, DE on PA8). Being
  RE'd from stock fw on the `modbus` branch. Verify VFD type + register map + DE timing.
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
