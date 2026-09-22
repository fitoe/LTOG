# Live LTFS identity for external Windows applications

With LTOG's patched engine, query the **root directory of the explicit mounted
drive** for these Windows extended attributes:

| EA name | Value source | Encoding |
| --- | --- | --- |
| `ltfs.volumeSerial` | Current mount's LTFS label barcode | UTF-8 bytes, no terminating NUL |
| `ltfs.volumeUUID` | Current mount's LTFS label UUID | UTF-8 bytes, no terminating NUL |

Open `T:\` with `CreateFileW(FILE_READ_EA, FILE_SHARE_READ | FILE_SHARE_WRITE |
FILE_SHARE_DELETE, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS)`. Call
`NtQueryEaFile` and parse `FILE_FULL_EA_INFORMATION`, respecting byte lengths
and aligned `NextEntryOffset`. Match names case-insensitively: Windows can
uppercase EA names. No elevation or `\\.\TAPE0` handle is needed. The EA query
must be repeated for each decision; do not cache identities by drive letter.

The query returns both values from one mounted filesystem instance. Unmount
or remount requires a fresh root handle; the provided client opens and closes
one per call. The engine checks medium readiness and rejects failed media
revalidation. Windows EA caching is disabled by the patched engine. As with
any device query, the result is an observation at query time, not a guarantee
that media cannot change afterward.

## Read-only example (Python 3, standard library only)

Keep `tools/ltfs_identity.py` and its companion `tools/ltfs_attributes.json`
together. Additional metadata and on-demand diagnostics are documented in
[LTFS-ATTRIBUTES.md](LTFS-ATTRIBUTES.md); the default identity command below
retains its original JSON contract and exit codes.

```powershell
python tools/ltfs_identity.py T:\
```

Successful JSON contains `status: "ok"`, `mountPoint`, `ltfs.volumeSerial`,
and `ltfs.volumeUUID`. The CLI's importable `read_identity(root)` function
uses the same interface. It never reads schema files, Windows volume labels,
or generic volume serial numbers. Two drives must be queried separately.

| Exit code | Status | Meaning |
| --- | --- | --- |
| 0 | `ok` | Both validated identity attributes were read |
| 2 | `invalid_mount_point` | Explicit drive root required |
| 3 | `mount_unavailable` | Missing drive, removed device, or media unavailable |
| 4 | `access_denied` | Root EA read denied; no elevated retry |
| 5 | `identity_missing` | Empty/missing attributes, including an old engine |
| 6 | `unsupported` | Platform/filesystem does not support this query |
| 7 | `io_error`, `invalid_response`, `invalid_identity` | Raw error/detail included |

Failure JSON contains no identity. An old engine and a medium with absent
attributes may both return `identity_missing`; EA alone cannot distinguish
them. Media-change errors may surface as generic I/O errors, with raw NTSTATUS.
Never substitute a previous successful result on failure. The client accepts
an LTFS barcode of one to six ASCII alphanumeric characters and a canonical
UUID; it deliberately rejects malformed responses.

## Deployment and physical-tape verification

Rebuilding does not update a running mount. Install/stage the new engine and
GUI only after the current tape workload has ended and the mount is cleanly
unmounted. Unmounting can flush pending tape data/indexes; it interrupts access
to the mounted drive. Do not replace a loaded DLL or terminate a physical
tape mount to apply this change.

After the next authorized mount with the new engine, run the example as an
ordinary user. For the physical cartridge described in the handoff, expected
values are `CP1316` and `4bcd059c-015c-40b3-8e16-e50c5bc99015`. These are
verification expectations only, never constants or fallback values in the
implementation. See `IDENTITY-VALIDATION.md` for what was actually verified.
