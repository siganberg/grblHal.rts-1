# RTS-1 grblHAL Firmware

Open-source **[grblHAL](https://github.com/grblHAL)** firmware for the Onefinity
**RTS-1 Open-Loop** controller (RealTime CNC / GSD RTS-1). It replaces the stock
firmware so you can run the controller with grblHAL and senders like **ncSender**.

> ⚠️ **Please read first.** This is an **unofficial, community project** — **not** affiliated
> with, endorsed by, or supported by RealTime CNC or Onefinity. Flashing replaces the stock
> firmware; it's reversible (the original is backed up in [`firmware/`](firmware/) and you can
> [restore it](#-restore-the-stock-firmware)), but **you do this entirely at your own risk.**
> **I take no responsibility whatsoever** for any damage to your controller, machine, tools,
> workpiece, or anything else, or for any loss arising from using this firmware, these scripts,
> or these instructions. No warranty of any kind. If you're not comfortable with that, don't flash.

---

## ✨ What you get
- Full **grblHAL** with all 4 axes (X, Y, Z, A) + **dual-Y auto-squaring** gantry.
- **Probe + tool-setter**, **sensorless homing**, **parking**, and **probe macros**.
- **All VFD types** (Huanyang, GS20, H-100, …) selectable in software — pick yours with `$395`.
- Works with **ncSender** over USB-C.

---

## ⚠️ Before you begin — what you need
- Your RTS-1 controller and its **USB-C** cable.
- A computer (**Windows / macOS / Linux**).
- The latest firmware files from the **[Releases page](../../releases)**:
  - `grblhal-rts1-<version>.hex` — for ncSender's flashing tool
  - `grblhal-rts1-<version>.bin` — for manual DFU flashing
- **First-time install only:** a **2.5 mm hex driver** to open the controller case (to reach
  the **BOOT0** button). After grblHAL is installed, future updates need **no opening**.

---

## 🔌 Install grblHAL for the first time (coming from stock firmware)

The first install needs the controller in **DFU mode** (a special update mode built into
the chip). You put it there by holding the **BOOT0** button while plugging in USB.

> 💡 You only ever do this once. After grblHAL is installed, updates are done from
> ncSender without opening the case (see [Updating](#️-update-grblhal-already-on-grblhal)).

### Step 1 — Download the firmware
Go to the **[Releases page](../../releases)** and download the latest
`grblhal-rts1-<version>.bin` (and `.hex`) to your computer.

### Step 2 — Open the case and find the BOOT0 button
Power **off** the controller and unplug everything. Open the case (**2.5 mm hex driver**)
and locate the small **BOOT0** button on the board.

<!-- TODO image: photo of the controller board with the BOOT0 button circled -->
![BOOT0 button location](docs/images/boot0-button.png)

### Step 3 — Enter DFU mode
1. **Press and hold** the **BOOT0** button.
2. While holding it, **plug the USB-C cable** into the controller and your computer.
3. **Release** the button after a second.

The controller is now in **DFU mode** (it shows up as a *STM32 BOOTLOADER* /
`0483:DF11` device). Nothing will light up like normal — that's expected.

![Holding BOOT0 while connecting USB](docs/images/boot0-usb-dfu.webp)

### Step 4 — Flash grblHAL
Use **one** of these:

**Option A — ncSender (friendliest):**
Open ncSender → **Settings → Firmware → Flash Firmware**, select the downloaded
`grblhal-rts1-<version>.hex`, and start. ncSender flashes the controller while it's in
DFU mode.

<!-- TODO image: ncSender Settings > Firmware > Flash Firmware dialog -->
![ncSender Flash Firmware](docs/images/ncsender-flash.png)

**Option B — command line (advanced):**
Install **dfu-util** (`brew install dfu-util` on macOS, `sudo apt install dfu-util` on
Linux; on Windows install dfu-util and set the WinUSB driver with **Zadig**), then run:
```bash
dfu-util -a 0 -s 0x08000000:leave -D grblhal-rts1-<version>.bin
```

### Step 5 — Done
Close the case, reconnect USB, and open ncSender — it should connect to grblHAL. If the
machine starts in an **Alarm** state, that's normal (homing lock); click **Unlock**, then
**Home**.

> 🆘 **If something goes wrong / it won't connect:** just repeat Steps 2–4. DFU mode is in
> the chip's ROM and can't be bricked — you can always re-enter it with the BOOT0 button.

---

## ⬆️ Update grblHAL (already on grblHAL)

**No need to open the case.** From ncSender:

1. Download the latest `grblhal-rts1-<version>.hex` from the **[Releases page](../../releases)**.
2. ncSender → **Settings → Firmware → Flash Firmware** → select the `.hex` → start.

ncSender puts the controller into update mode and flashes it for you.

<!-- TODO image: ncSender update flow (same dialog as above is fine) -->

---

## ↩️ Restore the stock firmware

Want to go back? The restore script and the original firmware backups live in **this
repository**, so first **clone it** (one-time):
```bash
git clone https://github.com/siganberg/grblHal.rts-1.git
cd grblHal.rts-1
```
Then put the controller in **DFU mode** (Steps 2–3 above) and run:
```bash
./scripts/restore-stock.sh          # restores v1.5.9 (or: restore-stock.sh 1.4.7)
```

---

## 🛠️ Build from source (developers)

```bash
# tools: Python + PlatformIO + (for flashing) dfu-util
pip install platformio

# fetch pinned upstream grblHAL + apply the RTS-1 board files, then build
cd grblhal-rts1 && ./setup.sh && cd STM32F4xx && pio run -e RTS1

# flash the build you just made (controller in DFU mode):
../../scripts/flash-grblhal.sh
```
**Cutting a release:** run **`./scripts/release.sh`** — it bumps the version, generates
user-facing release notes from the commit log (via the `claude` CLI), and pushes an
annotated tag. CI then builds the firmware and publishes a **GitHub Release** with the
`.bin` + `.hex` and those notes (same flow as ncSender). Every push/PR also builds and
uploads the artifacts for testing. See [`.github/workflows/build.yml`](.github/workflows/build.yml).

---

## 📚 Documentation
- **[docs/PIN_MAP.md](docs/PIN_MAP.md)** — the recovered STM32F401 pin map + isolated-I/O (TCA9555).
- **[docs/HANDOFF.md](docs/HANDOFF.md)** — bring-up status, design decisions, what's done / next.
- **[docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md)** — the custom `$` diagnostic console commands.
- **[docs/MODBUS.md](docs/MODBUS.md)** — VFD spindle setup (H-100 etc.).
- **[docs/RTS-X-UPDATE.md](docs/RTS-X-UPDATE.md)** — RE notes for no-BOOT0 flashing (shelved, future).

---

## Hardware
- **MCU:** STM32F401RCT6 (Cortex-M4F, 256 KB flash / 64 KB RAM)
- **Drivers:** 5× TI DRV8452 over SPI — X, Y1, Y2, Z, A
- **Spindle:** RS-485 Modbus VFD (ISL3485)
- **I/O:** isolated inputs + probe + tool-setter via a TCA9555 I²C expander; settings in an I²C EEPROM
- **USB-C** CDC. **BOOT0** button → STM32 ROM DFU (fully unlocked, RDP level 0).

## Status
Firmware is working and in testing: motors energize/home, probe + tool-setter, parking,
all VFDs, persistent settings, and self-healing boot power-up. See **[docs/HANDOFF.md](docs/HANDOFF.md)**.
