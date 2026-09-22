#!/bin/bash
# Invoked by build-native.py inside MSYS2. All outputs stay in this repository.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/build/WinLtfs-1.1.1"
WFSP="$SRC/build/wfsp"
export PATH="/mingw64/bin:/usr/bin:$PATH"
mkdir -p "$WFSP/lib" "$WFSP/bin"
cp -r "$ROOT/build/winfsp-2.1/inc" "$WFSP/"
cp "$(cygpath -u "$LTOG_WINFSP_DLL")" "$WFSP/bin/winfsp-x64.dll"
cd "$WFSP/lib"
gendef "$WFSP/bin/winfsp-x64.dll"
dlltool -d winfsp-x64.def \
    -D winfsp-x64.dll -l "$WFSP/lib/libwinfsp-x64.a"
cd "$SRC/ltfs"
if [ ! -f Makefile ]; then
    autoreconf -fi
    ./configure --host=x86_64-w64-mingw32 --build=x86_64-w64-mingw32 \
        --with-winfsp="$WFSP" \
        CFLAGS="-Dmingw_PLATFORM=1 -DHP_mingw_BUILD=1 -DHPE_mingw_BUILD=1 -D_FILE_OFFSET_BITS=64"
fi
bash -e "$SRC/build.sh" make
bash -e "$SRC/build.sh" filedebug
# Stage the upstream portable plugin registry into the final directory.
DIST="$ROOT/dist/winltfs" bash -e "$SRC/build.sh" dist
