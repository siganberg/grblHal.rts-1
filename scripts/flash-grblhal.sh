#!/usr/bin/env bash
#
# Flash the custom grblHAL firmware to the RTS-1 controller (USB DFU).
# Build it first:  cd grblhal-rts1 && ./setup.sh && cd STM32F4xx && pio run -e RTS1
# Then put the controller in DFU mode (hold BOOT0 + plug USB-C) and run this.
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# Prefer the active build tree, fall back to the setup.sh tree.
for B in \
  "$HERE/../grblhal/STM32F4xx/.pio/build/RTS1/firmware.bin" \
  "$HERE/../grblhal-rts1/STM32F4xx/.pio/build/RTS1/firmware.bin"; do
  [ -f "$B" ] && BIN="$B" && break
done

if [ -z "${BIN:-}" ]; then
  echo "ERROR: grblHAL firmware.bin not found."
  echo "Build it:  cd grblhal-rts1 && ./setup.sh && cd STM32F4xx && pio run -e RTS1"
  exit 1
fi

exec "$HERE/dfu-flash.sh" "$BIN" "grblHAL (RTS-1)"
