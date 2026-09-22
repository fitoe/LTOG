# Patched native engine

LTOG builds WinLtfs **v1.1.1** with `root-identity.patch` (LGPL-2.1, like
the modified upstream files). The source ZIP and WinFsp v2.1 headers are
SHA-256 pinned in `build-native.py`. Sources and intermediates live under
`build/`; no sibling checkout or installed LTOG binary is modified.

Install Python 3, MSYS2, and WinFsp 2.1. In an MSYS2 MINGW64 terminal:

```sh
pacman -S --needed make autoconf automake libtool mingw-w64-x86_64-gcc mingw-w64-x86_64-tools mingw-w64-x86_64-libxml2 mingw-w64-x86_64-icu mingw-w64-x86_64-pkgconf
```

From the LTOG repository in PowerShell:

```powershell
python native/build-native.py
# Optional locations: --msys C:/msys64 --winfsp-dll 'C:/Program Files (x86)/WinFsp/bin/winfsp-x64.dll'
powershell -ExecutionPolicy Bypass -File build.ps1 -SkipNative -NoInstaller
```

The native output is `dist/winltfs/`. The normal `build.ps1` also builds
these patched sources; `-SkipNative` requires the matching patch manifest.
The installer still requires PowerShell 7 and Inno Setup per its build script.
`gendef`/`dlltool` generate an import library from the installed WinFsp DLL,
so installing the SDK feature is unnecessary. The installed DLL is copied,
never replaced. Builds can be repeated without downloads while the checked
source ZIPs remain in `build/`.

The patch exposes identity and inexpensive metadata names on the root, retaining
LTFS's existing virtual getters. Capacity/health/alerts/encryption and file
metadata use a fixed, output-only WinFsp DeviceIoControl allowlist. A root EA enumeration checks
medium readiness with the mounted engine's existing handle and normal LTFS
revalidation. An absent or changed medium fails instead of using its old
label. CLI and GUI mounts disable WinFsp EA caching (`EaTimeout=0`). No new
hardware handle, persistent identity cache, or identity-writing operation is
introduced. Virtual EAs with operational side effects are not listed or accepted
by the new query interface. Some metadata getters have existing upstream setters;
the query interface never calls these setters. The two identity setters remain
rejected by upstream LTFS. Encryption getters now take the device lock before
issuing MODE SENSE, matching the existing health/capacity serialization.

`tools/ltfs_attributes.json` is the catalog and stable command-ID registry.
`native/update-patch.py` generates the patch from the checksum-verified upstream
ZIP and `native/attribute-query.h`; each native build verifies that they match.
Never renumber existing commands when extending the catalog. To update the patch
on an existing build tree, reverse the old patch first, then regenerate and build:

```powershell
git -C build/WinLtfs-1.1.1 apply --reverse ../../native/root-identity.patch
python native/update-patch.py
python native/build-native.py
```

See `docs/LTFS-ATTRIBUTES.md` for protocol sizes, status semantics, and exclusions.

Validation:

```powershell
python -m unittest discover -s tests -v
python tests/emulator_identity.py
# In an MSYS2 MINGW64 terminal: bash tests/native_identity.sh
```

The integration test creates **disk-backed** media inside `build/`, mounts
them read-only at explicitly reserved unused drive letters, and exercises
the real Windows EA path. It never opens a physical tape device. Do not use
the emulator format commands against a hardware backend.
