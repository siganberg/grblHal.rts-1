# RTS-X / stock-bootloader firmware-update path — RE notes (SHELVED, revisit later)

Goal (for later): let users on **stock firmware** flash grblHAL **without opening the
case** (no BOOT0), by pushing our image through the stock RTS bootloader the same way
the RTS-X host app does — then wire that into ncSender's Flash Firmware tool.

**Status: shelved.** This doc records what's been reverse-engineered so we can pick it
up later. For now, initial flashing uses BOOT0 + DFU (see `README.md`).

## Architecture (confirmed)
The stock flash has a **custom bootloader + app**, not a single image:

```
0x08000000  ┌─────────────────────────────┐
            │  RTS bootloader (~48 KB)     │  validates the app (CRC), then boots it
0x0800C000  ├─────────────────────────────┤
            │  App: [image header][vectors │  the CNC firmware (or grblHAL, if we push it)
            │        + code ...]           │
            └─────────────────────────────┘
```
Bootloader strings: `Bootloader started.` · `Image header version: %u` ·
`Firmware version: %u.%u.%u` · `App sector 0/1/2 erased` · `CRC mismatch!` ·
`Booting firmware %u.%u.%u`.

When we flash grblHAL today (DFU at `0x08000000`) we **overwrite the bootloader** and
boot grblHAL directly. The no-BOOT0 path instead **keeps the bootloader** and writes
grblHAL into the **app** region with a valid header — so the bootloader accepts and
boots it, and future updates go the same way (and a bad app can't brick it).

## Feasibility gate: OPEN ✅
- The update is **CRC-only — NO cryptographic signature** (searched the whole image:
  no rsa/sha/ecdsa/aes/hmac/sign/cert strings). So we can forge a valid image.
- The CRC is **standard CRC-32**, software (table-based), polynomial **`0xEDB88320`**
  (reflected) — constant sits at `0x08000a58`, routine at `0x08000a5c`. Fully reproducible
  in a build/wrap script.

## Key addresses (bootloader, fw v1.5.9)
| What | Address |
|---|---|
| Bootloader reset handler | `0x080014d9` |
| Bootloader main (`"Bootloader started."`) | `0x08000ee0` |
| CRC-32 routine | `0x08000a5c` (poly const `0x08000a58`) |
| CRC compare (`"CRC mismatch!"`) | `0x08000dc0` |
| Boot/jump to app (`"Booting firmware"`) | `0x08000e1c` |
| App region base | ~`0x0800C000` (header first, then vectors — exact offsets TBD) |
| Stored CRC in header | header **offset +8** (`ldr r3,[hdr,#8]`); CRC covers a (start,len) region |

## Still TODO (when we implement)
1. **Full image-header layout** — fields + offsets (header version, fw version `%u.%u.%u`,
   CRC@+8, image size/length, start address, any magic). RE the header reads around
   `0x08000d80`+ and the `"Image header version"` print.
2. **Exact app base + entry** — the app vector table is *after* the header (plain
   `0x0800C000` is not a vector table). Confirm header size → vector base, and how the
   bootloader sets `VTOR`/jumps.
3. **CRC init / xorout** — read the rest of `0x08000a5c` (running value inits to 0; confirm
   no final XOR vs standard `0xFFFFFFFF`). Match it byte-for-byte.
4. **Wire protocol** — how RTS-X triggers update mode and streams the image (over USB-CDC?
   a JSON `msgType` command + raw blocks? a reboot-to-bootloader signal?). **Best obtained
   from a USBPcap/Wireshark capture of one real RTS-X update**, not static RE.

## Implementation sketch (later)
1. Link grblHAL at the **app base** (not `0x08000000`); set `VTOR` to the app vectors.
2. Post-build **wrap script**: prepend/patch the stock image header + compute CRC-32
   (`0xEDB88320`) over the image; emit an `.rts`-style file.
3. **Pusher** (standalone tool, then folded into ncSender Flash Firmware): speak the RTS-X
   wire protocol to trigger update mode and stream the wrapped image. Keep the stock
   bootloader intact → no BOOT0 ever, plus recovery.

## Risks
- If a future stock bootloader adds signing, this path closes (current one does not).
- Getting the header/CRC/VTOR wrong → the bootloader rejects (CRC mismatch) and keeps the
  old app: **safe-fails, doesn't brick** (the bootloader only boots a valid app). Good.
