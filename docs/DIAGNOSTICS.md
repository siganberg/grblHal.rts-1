# RTS-1 → grblHAL — custom diagnostic console commands

These `$…` commands are **custom to this board** (implemented in
`grblhal-rts1/boards/rts1.c`, function `rts1_sys_command`). They are NOT part of
upstream grblHAL — they hook in via `grbl.on_unknown_sys_command`, so grblHAL hands any
unrecognized `$word` to our handler. On stock grblHAL (or any other board) they just
return `error:3` (Invalid statement).

They are safe to leave in: they don't run during normal motion, only when typed.

## Always available (shipping build)

### `$IEX` — read the TCA9555 isolated-I/O expander
Dumps the 16 input bits of the **TCA9555 I²C I/O expander** (U6 @ addr 0x27 on I²C1),
which is the gateway to all the isolated DB-25 I/O. See `PIN_MAP.md` for the full story.

```
$IEX
[MSG:IEX =87FF]
```
- 4-hex-digit value = input ports 0 (low byte) + 1 (high byte). **Active-LOW**: a
  triggered/grounded input reads **0**.
- Returns `[MSG:IEX =ERR]` if the expander doesn't ACK on I²C.

Known bit map (active-low):
| Bit(s) | Signal |
|---|---|
| 0–7  | the 8 isolated DB-25 inputs (pins 1–8) |
| **8**  | **PROBE** (DB-25 pin 22 / connector J6) |
| **9**  | **tool-setter / TLS** |
| 11–14 | the 4 isolated outputs (OUT0–3) |

**How to map an unknown input/output:** run `$IEX` open, short the connector to IGND,
run `$IEX` again, and see which hex digit changed — that bit is that connector. (This is
exactly how probe=bit8 and TLS=bit9 were found.)

### `$MD=N` — select the monitored / tuned DRV8452 driver
Selects which stepper driver (`N` = 0–4) the `$STH` command targets (and the `RTS1_DIAG`
stall-monitor stream reports on). Driver→axis: 0=X, 1=Y1, 2=Y2, 3=Z, 4=A.

```
$MD=3
[MSG:MON drv=3]
```

### `$STH=N` — set the selected driver's stall threshold (live)
Writes the DRV8452 `STALL_TH` (CTRL5/CTRL6, 12-bit, decimal `N`) on the `$MD`-selected
driver. Used to tune **sensorless stall homing** without reflashing.

```
$STH=230
[MSG:STALL_TH D3=0x0E6]
```

## Gated behind `RTS1_DIAG` (compiled OUT of the shipping build)

`RTS1_DIAG` is a `#define` in `boards/rts1.c` (default **0**). Set it to **1** and reflash
to enable verbose diagnostics; it costs flash so it's off for release.

### `$DRV` — dump all five DRV8452 register sets
Reads the key registers (FAULT, CTRL1–6, TRQ_COUNT, CTRL10/11/13) from all 5 drivers.
```
$DRV
[MSG:DRV0 F=0x00 C1=0x8F C2=0x06 C3=0x3C ... ]
... (one line per driver)
```

When `RTS1_DIAG=1` also enables: a one-shot register dump at boot, a `@fault` pin
snapshot on each e-stop/VM-loss transition, and a 5 Hz stall-monitor stream
(`[MSG:MON D… TQ=… min=… PC5=… F=…]`) that runs automatically while homing/jogging.

## Removed (kept here for history)
These existed during bring-up and were deleted once their job was done, to reclaim flash:
- **`$FPIN`** — dumped candidate fault/limit input pins (used to find the OR-tied nFAULT).
- **`$IDR`** — raw GPIOA/B/C/D input registers (used while hunting for the probe pin,
  before we learned the inputs are behind the I²C expander, not GPIO).
- **`$IBIAS`** — pulled up spare candidate GPIOs (same probe-pin hunt).

## Notes
- The flash budget is tight (the F401RC's usable code region is ~224 KB — the ldscript
  reserves 16 KB for flash-NVS emulation). If you need space, gate `$IEX`/`$MD`/`$STH`
  under `RTS1_DIAG` too — but the bigger win is moving NVS to the I²C EEPROM (frees the
  16 KB sector + makes settings persist). See `HANDOFF.md`.
