#!/usr/bin/env bash
#
# Sets up a buildable grblHAL STM32F4xx tree for the RealTime CNC RTS-1 by
# cloning the pinned upstream driver and applying our board map + build env.
#
# Usage:   ./setup.sh   (run from this grblhal-rts1/ directory)
# Build:   cd STM32F4xx && pio run -e RTS1
#
set -euo pipefail

GRBLHAL_REPO="https://github.com/grblHAL/STM32F4xx.git"
GRBLHAL_COMMIT="a109b088015cd91f5b9153e3bc6decac862711fe"   # latest as of 2026-06-02
HERE="$(cd "$(dirname "$0")" && pwd)"
DST="$HERE/STM32F4xx"

if [ ! -d "$DST" ]; then
  echo ">> Cloning grblHAL/STM32F4xx ..."
  git clone --recurse-submodules "$GRBLHAL_REPO" "$DST"
fi
cd "$DST"
echo ">> Checking out pinned commit $GRBLHAL_COMMIT ..."
git checkout -q "$GRBLHAL_COMMIT"
git submodule update --init --recursive -q

echo ">> Installing board map ..."
cp "$HERE/boards/rts1_map.h" boards/rts1_map.h

echo ">> Wiring BOARD_RTS1 into Inc/driver.h ..."
if ! grep -q 'BOARD_RTS1' Inc/driver.h; then
  python3 - "$PWD/Inc/driver.h" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
anchor = '#elif defined(BOARD_STM32F401_UNI)\n  #include "boards/stm32f401_uni_map.h"\n'
ins = anchor + '#elif defined(BOARD_RTS1)\n  #include "boards/rts1_map.h"\n'
assert anchor in s, "anchor not found in driver.h"
open(p, 'w').write(s.replace(anchor, ins, 1))
PY
fi

echo ">> Appending [env:RTS1] to platformio.ini ..."
grep -q 'env:RTS1' platformio.ini || cat "$HERE/platformio_env.ini" >> platformio.ini

echo ">> Done. Build with:  cd '$DST' && pio run -e RTS1"
