# RTS-2 bring-up notes (WIP — branch `feat/rts2-support`)

The RTS-2 is the **closed-loop** sibling of the RTS-1: **no internal DRV8452 drivers**
(step/dir goes to *external* closed-loop drivers), plus per-axis closed-loop **motor-fault**
inputs and separate homing-sensor connectors. Stock firmware is **byte-identical** to
RTS-1 stock v1.5.9 (md5 `708d2e93…`) — one RealTime CNC image serves both products.

## Done (this branch)
- **Driver-presence auto-detect** (`rts1_drv_present()` → `rts1_have_drivers`): probes the
  DRV8452 over SPI with a two-value sentinel echo. Absent on RTS-2 → skips driver config
  **and** the VM/UVLO e-stop, so the firmware boots clean on RTS-2 (no false EStop). RTS-1
  unaffected (drivers detected → all as before). Re-probed by the poller so an RTS-1 that
  booted with the driver logic dark still recovers. **Verified on RTS-2 hardware.**
- **Diagnostics** (temporary, remove before any RTS-2 release):
  - `$LPIN` — dump raw GPIOA/B/C input registers.
  - `$ADC`  — read all 16 ADC1 channels.

## Findings
- **Per-axis motor-fault detection (how stock alarms):** stock shows a *per-axis* "Closed-Loop
  Motor Error" (X, Y1, Y2, Z) when a driver is **unpowered or disconnected**. These are the
  driver **ALM** outputs wired to the controller — almost certainly the pins the RTS-1 map
  calls "limits": **PC5=X, PC9=Y1, PB4=Y2, PC10=Z** (axis names match the stock dialog exactly).
  They read **HIGH = fault**; sat HIGH+constant in every scan because no closed-loop drivers
  were connected on the bench (always faulted → nothing to observe). NOT limit switches on RTS-2.
- **No single power-sense line:** cutting the PSU changed **nothing** on any GPIO, the TCA9555
  (`$IEX`), or any ADC channel (`$ADC` identical PSU on/off). The controller is USB-powered;
  the PSU only feeds the external drivers. So RTS-1-style VM detection isn't reproducible as a
  single signal — it's the per-axis ALM inputs above.
- **Homing sensors:** separate 3-pin connectors on the expansion board, **pin1=GND, pin2=5V,
  pin3=SW** (trigger by 5V→SW). Pin mapping unconfirmed (bench probing hit floating pins / a
  flipped donor board). Not yet located.
- **Microstepping:** stock = 1/16 (DRV8452 CTRL2=0x06) → 3200 pulses/rev. Set the external
  closed-loop drivers to 3200 pulses/rev to match the baked `$100-103`, or recalibrate.

## TODO (needs a real closed-loop driver + motor on the bench)
1. Confirm the 4 motor-fault pins (PC5/PC9/PB4/PC10) + polarity: connect one powered driver,
   watch the pin flip fault→OK. Then wire them to grblHAL's **motor-fault** input / e-stop so
   RTS-2 alarms per-axis like stock.
2. Map the homing-sensor pins (trigger each 5V→SW, watch `$LPIN`/`$IEX`), set `$5` polarity,
   and route homing to grblHAL's **native** limits (skip the RTS-1 stall/`-limitsw` path when
   `!rts1_have_drivers`).
3. Verify steps/mm vs the external drivers' pulses/rev.
4. Remove the `$LPIN`/`$ADC` diagnostics before releasing an RTS-2 build.
