#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/build/WinLtfs-1.1.1/ltfs"
export PATH="/mingw64/bin:/usr/bin:$PATH"
gcc "$ROOT/tests/native_identity.c" -o "$ROOT/build/native-identity-test.exe" \
    -DHAVE_CONFIG_H -D_GNU_SOURCE -Dmingw_PLATFORM=1 -DHP_mingw_BUILD=1 \
    -DHPE_mingw_BUILD=1 -D_FILE_OFFSET_BITS=64 -I"$SRC" -I"$SRC/src" \
    -I"$SRC/../build/wfsp/inc/fuse" $(pkg-config --cflags libxml-2.0 icu-uc) \
    -L"$SRC/src/libltfs/.libs" -lltfs -lpthread -L"$SRC/../build/wfsp/lib" -lwinfsp-x64
export PATH="$ROOT/dist/winltfs:$PATH"
"$ROOT/build/native-identity-test.exe"
