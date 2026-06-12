# RealTime CNC RTS-1 → grblHAL project

Reverse-engineering the Onefinity **RTS-1 Open-Loop** controller ("GSD RTS-1")
to replace the stock closed firmware with **grblHAL**.

## Hardware
- **MCU:** STM32F401RCT6 (Cortex-M4F, 256 KB flash / 64 KB RAM, LQFP64)
- **Drivers:** 5× TI DRV8452 (STEP/DIR), 2.8 A RMS, up to 1/64 microstep — X, Y1, Y2, Z, A
- **Spindle:** RS-485 Modbus VFD via ISL3485 transceiver (U5)
- **I/O:** DB-25 = 8 isolated inputs + 4 isolated outputs; dedicated probe + toolsetter
- **USB-C** CDC (ST default VID/PID 0483:5740). Power: 6-pin Molex Mini-Fit Jr.

## Flashing access (fully unlocked)
- **BOOT0 button** → STM32 ROM **DFU** bootloader (`0483:DF11`). No ST-Link needed.
- **RDP Level 0** — flash freely readable/writable. Reversible.
- Read:  `dfu-util -a 0 -s 0x08000000:0x40000 -U dump.bin`
- Write: `dfu-util -a 0 -s 0x08000000:leave -D firmware.bin`
- Flash layout: `[48 KB RTS bootloader @0x08000000]` + `[app + image-header @0x0800C000]`.
  The bootloader validates the app (CRC + version in the header).

## Flash / restore helper scripts (`scripts/`)
Put the controller in DFU mode first (hold **BOOT0** while plugging in USB-C). Each
script flashes, **verifies by read-back**, then boots — aborting if verification fails.
- `scripts/flash-grblhal.sh` — flash the custom grblHAL build (build it first via `grblhal-rts1/setup.sh` + `pio run -e RTS1`).
- `scripts/restore-stock.sh` — restore stock firmware (default **v1.5.9**; `restore-stock.sh 1.4.7` for the original dump).

## Folders
- **`firmware/`** — full 256 KB flash dumps (+ option bytes, checksums):
  - `RTS-1_fw_v1.4.7_original_2026-06-11.bin` — first dump (original, pre-update)
  - `RTS-1_fw_v1.5.9_2026-06-11.bin` — after the host app auto-updated it
  - `option_bytes.bin` — 16 B option bytes (RDP=0xAA)
- **`analysis/`** — Python/capstone disassembly scripts used to extract the pin map
  (key: `init_decode2.py`; needs `../.venv`). Plus the older `PIN_MAP_draft.md`.
- **`PIN_MAP.md`** — the recovered STM32F401 pin map (primary doc).
- **`.venv/`** — Python venv with `capstone`, `pyserial`.

## Firmware versions seen
| Version | md5 | Note |
|---|---|---|
| v1.4.7 | 7a47f94e… | original dump |
| v1.5.9 | 708d2e93… | after host-software auto-update; full app rewrite, bootloader unchanged |

Stock firmware = closed FreeRTOS app, custom JSON (`msgType`) protocol over USB CDC.
Host motion software pushes firmware updates via the RTS bootloader.

## Status
Pin map ~90% recovered from firmware (see `PIN_MAP.md`). Flashing path de-risked
(USB DFU). Remaining: STEP↔axis order, motor ENABLE pin, status-LED pin, then build
the grblHAL STM32F4xx board map.
