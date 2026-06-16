# RTS-1 → grblHAL — Modbus VFD spindle

Status doc for the spindle/VFD over Modbus RTU (RS-485). Target VFD: **H-100**, but
**all grblHAL VFD drivers are compiled in** and selectable at runtime — keep them all.

## Hardware path (CONFIRMED working in stock fw)
- **USART1**: PA9 = TX, PA10 = RX (AF7) → **ISL3485** RS-485 transceiver.
- **RS-485 DE/RE on PA8** (our build: `MODBUS_DIR_AUX=1`; stock toggles PA8 around each TX).
- Stock RTS-1 link: **Modbus RTU, 9600 8N1, slave address 1**, CRC16 (poly 0xA001). ✓
- So the wiring + transport are proven; switching VFD brand is just driver + settings.

## Stock VFD = GS20 protocol (NOT H100)
RE of stock fw (firmware/RTS-1_fw_v1.5.9): spindle frames are `func 0x06 → reg 0x2000`
(control) + `reg 0x2001` (freq) — that's grblHAL's **Durapulse GS20** map, not H100.
(H100 uses WriteCoil 0x05 → coils 0x49/4A/4B for run/fwd/rev, WriteRegister → reg 0x0201.)
Frame builder @0x0801373a; CRC tables @0x08027e68/0x08027f68; UART init @~0x08013320
(Instance=USART1 + BaudRate=9600 8N1, Mode=TX_RX). So if you ever drive the ORIGINAL
GS20-style VFD: `$395 = Durapulse GS20` matches stock exactly.

## $395 spindle types (all built in)
Basic (on/off, current default) · Huanyang v1 · Huanyang P2A · **Durapulse GS20** ·
Yalang YS620 · MODVFD (generic) · **H-100** · Nowforever. `$395` needs a hard reset to apply.

## H-100 setup (when the VFD arrives)
1. **Wire** RS-485 A/B from the H100 to the board's RS-485 terminals (the USART1/ISL3485 pair).
2. **On the H100 VFD**, set: RS-485/Modbus **control mode** (run+freq from comms, not the
   panel), **slave address**, **baud**, **format** — e.g. addr 1, 9600, 8N1.
3. **In grblHAL** (ncSender Firmware tab or `$`):
   - `$395` = **H-100**, then **hard reset** (power-cycle / re-enumerate).
   - `$374` = ModBus baud — radio `2400,4800,9600,19200,38400,115200`; **idx 2 = 9600**
     (note: our build default is idx 3 = 19200 — set it to match the VFD).
   - `$681` = ModBus serial format — `8N1 / 8E1 / 8O1`; **idx 0 = 8N1**.
   - Spindle Modbus unit address setting = the VFD's slave address (check `$$`).
   - The H100 driver reads its min/max frequency from the VFD (PD05/PD11) to build the
     RPM range; confirm `$30/$31` (max/min RPM) look right after connect.

## Test checklist
- `M3 S<rpm>` → spindle runs forward at speed; `M5` → stops; `M4 S<rpm>` → reverse.
- Watch ncSender Logs / `$spindle` state for Modbus exceptions/timeouts.
- If no response: re-check addr/baud/format match, RS-485 A/B polarity, and that the
  VFD is in comms-control mode. A scope on PA8 should show DE pulse around each frame.

## Notes
- Keep `DEFAULT_SPINDLE=SPINDLE_ONOFF0` (Basic) as the boot default so a missing/unpowered
  VFD doesn't stall on Modbus timeouts; select the VFD via `$395` when present.
- Multi-VFD support is intentional — do not remove drivers; users may run any of the above.
