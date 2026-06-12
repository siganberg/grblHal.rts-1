#!/usr/bin/env bash
#
# Restore the ORIGINAL RealTime CNC stock firmware to the RTS-1 controller (USB DFU).
# Defaults to v1.5.9 (the version the host software last installed).
# Pass v1.4.7 as an arg to restore the very first dump instead:
#     ./restore-stock.sh 1.4.7
#
# Put the controller in DFU mode (hold BOOT0 + plug USB-C) and run this.
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FW_DIR="$HERE/../firmware"

VER="${1:-1.5.9}"
case "$VER" in
  1.5.9) BIN="$FW_DIR/RTS-1_fw_v1.5.9_2026-06-11.bin";     LABEL="stock v1.5.9 (latest)";;
  1.4.7) BIN="$FW_DIR/RTS-1_fw_v1.4.7_original_2026-06-11.bin"; LABEL="stock v1.4.7 (original dump)";;
  *) echo "ERROR: unknown version '$VER' (use 1.5.9 or 1.4.7)"; exit 1;;
esac

exec "$HERE/dfu-flash.sh" "$BIN" "$LABEL"
