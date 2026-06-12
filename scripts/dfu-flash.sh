#!/usr/bin/env bash
#
# dfu-flash.sh <firmware.bin> [label]
#
# Flashes a full 256 KB STM32F401 image over USB DFU (the ROM bootloader),
# verifies it by reading the flash back and comparing, then boots it.
# Reversible: if verification fails it aborts WITHOUT booting.
#
# Entering DFU mode:
#   - If grblHAL is already running, this script auto-enters DFU by sending the
#     "$DFU" command over the USB-CDC serial port (no BOOT0 button needed).
#   - Otherwise (restoring stock, or a non-responsive app) hold BOOT0 while
#     plugging in USB-C, then run this script.
#   - Set RTS1_NO_AUTODFU=1 to skip the serial auto-enter and require BOOT0.
#
set -euo pipefail

ADDR=0x08000000
BIN="${1:?usage: dfu-flash.sh <firmware.bin> [label]}"
LABEL="${2:-firmware}"

DFU="$(command -v dfu-util || true)"
[ -n "$DFU" ]    || { echo "ERROR: dfu-util not found  (brew install dfu-util)"; exit 1; }
[ -f "$BIN" ]    || { echo "ERROR: firmware not found: $BIN"; exit 1; }

md5of() { md5 -q "$1" 2>/dev/null || md5sum "$1" | awk '{print $1}'; }

dfu_present() { "$DFU" -l 2>/dev/null | grep -q "Found DFU"; }

# Free a serial port a sender app (ncSender/gSender) is holding, so we can write
# to it. Closes whatever process has it open (SIGTERM, then SIGKILL). Skip with
# RTS1_NO_KILL=1.
free_port() {
  local port="$1" pids
  command -v lsof >/dev/null 2>&1 || return 0
  pids="$(lsof -t "$port" 2>/dev/null)"
  [ -z "$pids" ] && return 0
  [ "${RTS1_NO_KILL:-0}" = 1 ] && return 0
  echo ">> $port is held by PID(s) $pids — closing the app to free the port..."
  kill $pids 2>/dev/null
  for _ in 1 2 3 4 5 6; do                       # up to ~3s for graceful release
    [ -z "$(lsof -t "$port" 2>/dev/null)" ] && return 0
    sleep 0.5
  done
  pids="$(lsof -t "$port" 2>/dev/null)"
  [ -n "$pids" ] && { echo ">> forcing close (PID $pids)"; kill -9 $pids 2>/dev/null; sleep 1; }
  return 0
}

# Ask a running grblHAL to reboot into the ROM DFU bootloader by sending "$DFU"
# over its USB-CDC serial port. Best-effort: returns non-zero if no port found.
enter_dfu_via_serial() {
  local sent=0 port
  # macOS exposes the CDC ACM device as /dev/cu.usbmodem*; a DFU device does not.
  for port in /dev/cu.usbmodem* /dev/cu.usbserial*; do
    [ -e "$port" ] || continue
    free_port "$port"                            # close ncSender/gSender if it holds it
    echo ">> Sending \$DFU to $port ..."
    stty -f "$port" 115200 2>/dev/null || true
    # $ is literal inside single quotes; printf renders the CRLF.
    if printf '$DFU\r\n' > "$port" 2>/dev/null; then
      sent=1
    else
      echo "   (port still busy — close the sender app manually, or type \$DFU there)"
    fi
  done
  [ "$sent" = 1 ]
}

echo "============================================================"
echo " Flashing: $LABEL"
echo " File:     $BIN  ($(wc -c < "$BIN" | tr -d ' ') bytes)"
echo "============================================================"

# --- ensure DFU mode (auto-enter from running grblHAL, else require BOOT0) ---
if ! dfu_present; then
  if [ "${RTS1_NO_AUTODFU:-0}" != 1 ] && enter_dfu_via_serial; then
    echo ">> Waiting for the DFU bootloader to enumerate..."
    for _ in $(seq 1 40); do        # up to ~20 s
      dfu_present && break
      sleep 0.5
    done
  fi
fi

if ! dfu_present; then
  echo
  echo ">> Device is NOT in DFU mode (auto-enter via \$DFU did not take)."
  echo ">> Hold the BOOT0 button while plugging in USB-C, then re-run this script."
  echo ">>   (or unset RTS1_NO_AUTODFU if you set it)"
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
# Compare md5 of a clean read-back against the source. The first upload right
# after a download can fail while the device settles (dfuDNLOAD-IDLE), so retry.
# NOTE: do NOT pipe dfu-util into `grep -q` here — grep closes the pipe on match,
# SIGPIPEs dfu-util mid-upload, and leaves a truncated read-back (false mismatch).
echo ">> Verifying (reading flash back)..."
RB="$(mktemp)"; SRC="$(mktemp)"; trap 'rm -f "$RB" "$SRC"' EXIT
head -c "$IMG" "$BIN" > "$SRC"; SRC_MD5=$(md5of "$SRC")
RB_MD5=""
sleep 1
for attempt in 1 2 3 4; do
  rm -f "$RB"          # dfu-util -U refuses to overwrite an existing file
  "$DFU" -a 0 -s ${ADDR}:${IMG} -U "$RB" >/dev/null 2>&1 || true
  RB_MD5=$(md5of "$RB")
  [ "$SRC_MD5" = "$RB_MD5" ] && break
  echo "   read-back attempt $attempt didn't match yet; retrying..."
  sleep 1
done
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
