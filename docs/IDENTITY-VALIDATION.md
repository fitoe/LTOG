# Validation — 2026-09-21

## Build and automated checks

- Built checksum-pinned WinLtfs v1.1.1 with the LTOG patch using MSYS2
  MINGW64 GCC 16.1.0 and installed WinFsp 2.1.
- Built the self-contained .NET 8 x64 GUI and staged the distribution with
  `powershell -File build.ps1 -SkipNative -NoInstaller`: 0 warnings, 0 errors.
- All 13 Python unit tests passed, covering EA parsing, protocol bounds,
  status handling, scope validation, and report invalidation after permission
  failures or a UUID change.
- Native tests against the actual patched DLL passed: root-only metadata
  enumeration, exact/short buffers with overrun sentinels, identity getters,
  missing serial, identity setter rejection, nonempty-file partition/start-block
  getters, and rejection of malformed control requests before device access.
- Patch/catalog consistency passed. Source whitespace checks passed excluding the
  generated patch, whose upstream context contains whitespace flagged by Git.

## Ordinary-user emulator integration

Two simultaneous disk-backed media were mounted read-only with the actual
patched engine and installed WinFsp driver. The non-elevated integration test
verified identity enumeration and named queries, all 59 catalog entries,
grouped/case-insensitive queries, and file metadata. Hardware diagnostics are
excluded from ordinary root EA enumeration.

Disconnecting a mount invalidated subsequent queries. Reusing its drive letter
for the other medium returned the new UUID. All media files retained their
pre-mount SHA-256 hashes. Fixtures were prepared before mounting; only emulator
processes started by the test were terminated.

## Installed application and physical tape

The installed application was backed up and replaced with the verified build.
Its existing layout (native engine in the installation root, GUI in `gui/`),
shortcuts, plugin configuration, and drive mapping were preserved. The GUI's
parent-directory engine discovery was verified by rebuilding the distribution.

After remounting with the installed engine, a non-elevated process verified the
drive through GetLogicalDriveStrings, filesystem access, GetVolumeInformation,
and the shell's This PC namespace. Both cartridge serial and UUID were read
successfully using the installed query client.

All 59 queries completed with 51 `ok`, 1 `empty`, 3 `unavailable`,
1 `unsupported`, and 3 `unknown`, returning the documented partial-report
exit code 8. Validation issued read-only queries and no file-content writes,
formatting, or repair commands. The physical mount retained its existing
read/write mode with `sync_type=close`; it was not a read-only mount.

On the tested HP LTO6 backend, encryption MODE SENSE queries failed and the
backend automatically captured diagnostic dumps in its error handler. The
three encryption results were `unknown`. No explicit dump operation is exposed
by this interface, but diagnostic reads can trigger this existing backend side
effect. Ordinary identity and metadata EA queries do not call encryption getters.

## Limits

- Physical media removal, hardware hot-swap, and a denied root ACL were not
  induced. Emulator disconnect/replacement and client error handling were tested.
- Earlier missing-Explorer-drive behavior was not retrospectively reproduced;
  visibility of the newly installed mount was verified successfully.
- The existing GUI `requireAdministrator` manifest is unchanged. External query
  clients were verified without elevation.
- No installer was built or run. Remote GitHub Actions were not executed locally.
- Multiple values are checked for a consistent volume UUID, but are not an
  atomic snapshot of changes within the same volume.

## Reproduction and evidence

See `native/README.md` for build/test commands and `LTFS-ATTRIBUTES.md` and
`LTFS-IDENTITY.md` for API details. Local build, native-test, client-test, and
emulator-test logs are retained under ignored `build/`; physical query output
is in `build/installed-attributes.json`. Generated binaries, media fixtures,
installation backups, and machine-specific logs are excluded from the PR.
