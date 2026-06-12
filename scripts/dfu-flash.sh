#!/usr/bin/env bash
#
# dfu-flash.sh <firmware.bin> [label]
#
# Flashes a full 256 KB STM32F401 image over USB DFU (the ROM bootloader),
# verifies it by reading the flash back and comparing, then boots it.
# Reversible: if verification fails it aborts WITHOUT booting.
#
# The device must be in DFU mode: hold the BOOT0 button while plugging in USB-C.
#
set -euo pipefail

ADDR=0x08000000
BIN="${1:?usage: dfu-flash.sh <firmware.bin> [label]}"
LABEL="${2:-firmware}"

DFU="$(command -v dfu-util || true)"
[ -n "$DFU" ]    || { echo "ERROR: dfu-util not found  (brew install dfu-util)"; exit 1; }
[ -f "$BIN" ]    || { echo "ERROR: firmware not found: $BIN"; exit 1; }

md5of() { md5 -q "$1" 2>/dev/null || md5sum "$1" | awk '{print $1}'; }

echo "============================================================"
echo " Flashing: $LABEL"
echo " File:     $BIN  ($(wc -c < "$BIN" | tr -d ' ') bytes)"
echo "============================================================"

# --- require DFU mode ---
if ! "$DFU" -l 2>/dev/null | grep -q "Found DFU"; then
  echo
  echo ">> Device is NOT in DFU mode."
  echo ">> Hold the BOOT0 button while plugging in USB-C, then re-run this script."
  exit 1
fi
echo ">> DFU device detected."

# --- image size (strip 16-byte PlatformIO DFU suffix if present) ---
SIZE=$(wc -c < "$BIN" | tr -d ' ')
IMG=$SIZE
if command -v dfu-suffix >/dev/null 2>&1 && dfu-suffix -c "$BIN" >/dev/null 2>&1; then
  IMG=$((SIZE - 16))
  echo ">> DFU suffix present; flashed image = $IMG bytes."
fi

# --- flash (no auto-boot yet) ---
echo ">> Writing flash..."
"$DFU" -a 0 -s ${ADDR} -D "$BIN" 2>&1 | grep -iE "download|done|success|error|fail" | tail -3

# --- verify by read-back ---
echo ">> Verifying (reading flash back)..."
RB="$(mktemp)"; trap 'rm -f "$RB"' EXIT
"$DFU" -a 0 -s ${ADDR}:${IMG} -U "$RB" 2>&1 | grep -iE "upload done|error" | tail -1

SRC="$(mktemp)"; head -c "$IMG" "$BIN" > "$SRC"
SRC_MD5=$(md5of "$SRC"); RB_MD5=$(md5of "$RB"); rm -f "$SRC"
echo "   source: $SRC_MD5"
echo "   device: $RB_MD5"
if [ "$SRC_MD5" != "$RB_MD5" ]; then
  echo "   ❌ VERIFY FAILED — flash does not match. NOT booting; please re-flash."
  exit 1
fi
echo "   ✅ verified byte-for-byte."

# --- boot the firmware (leave DFU) ---
echo ">> Booting firmware (leaving DFU)..."
"$DFU" -a 0 -s ${ADDR}:leave -D "$BIN" >/dev/null 2>&1 || true
echo "✅ Done: $LABEL flashed, verified, and booted."
echo "   (If USB doesn't re-enumerate, power-cycle without holding BOOT0.)"
