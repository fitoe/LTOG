"""Read live LTFS identity/EAs or select read-only attributes (no tape handle).

Usage: python tools/ltfs_identity.py T:\
Exit codes: 0 identity, 2 invalid argument, 3 unmounted/unavailable,
4 access denied, 5 identity missing, 6 unsupported, 7 I/O or malformed data,
8 partial attribute report. --list is offline; --all includes diagnostics.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import re
import struct
import sys
import uuid
from pathlib import Path

CATALOG = json.loads(Path(__file__).with_name("ltfs_attributes.json").read_text(encoding="utf-8"))
ATTRIBUTES = {row["name"].lower(): row for row in CATALOG}
GROUPS = tuple(dict.fromkeys(row["group"] for row in CATALOG))

NAMES = ("ltfs.volumeSerial", "ltfs.volumeUUID")


class IdentityError(Exception):
    def __init__(self, status, code, detail):
        super().__init__(detail)
        self.status, self.code = status, code


def normalize_root(root):
    # Require an explicit drive root: never resolve a drive-relative working dir.
    if not re.fullmatch(r"[a-zA-Z]:[\\/]?", root):
        raise IdentityError("invalid_mount_point", 2, "Specify a drive root, e.g. T:\\")
    return root[0].upper() + ":\\"


def parse_eas(data):
    """Decode bounded FILE_FULL_EA_INFORMATION records; names are case-insensitive."""
    result = {}
    offset = 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError("Truncated EA header")
        nxt, flags, name_len, value_len = struct.unpack_from("<IBBH", data, offset)
        end_name = offset + 8 + name_len
        end_value = end_name + 1 + value_len
        if end_value > len(data) or data[end_name] != 0:
            raise ValueError("Invalid EA length or name terminator")
        # Unrelated EAs may use non-ASCII bytes; only the identity names need
        # ASCII case matching. Preserve unknown bytes instead of failing them.
        name = data[offset + 8:end_name].decode("ascii", errors="surrogateescape").lower()
        if name in result:
            raise ValueError("Duplicate EA name")
        result[name] = data[end_name + 1:end_value]
        if nxt == 0:
            break
        if nxt % 4 or nxt < end_value - offset or offset + nxt >= len(data):
            raise ValueError("Invalid EA record offset")
        offset += nxt
    return result


def identity_from_eas(eas):
    if any(not eas.get(name.lower()) for name in NAMES):
        raise IdentityError("identity_missing", 5, "Mount does not expose both nonempty identity EAs")
    try:
        serial, volume_uuid = (eas[name.lower()].decode("utf-8", errors="strict") for name in NAMES)
        if not re.fullmatch(r"[A-Za-z0-9]{1,6}", serial):
            raise ValueError("Invalid LTFS volume serial")
        if str(uuid.UUID(volume_uuid)) != volume_uuid.lower():
            raise ValueError("Invalid LTFS volume UUID")
    except (ValueError, UnicodeError) as e:
        raise IdentityError("invalid_identity", 7, str(e)) from e
    return dict(zip(NAMES, (serial, volume_uuid)))


def query_eas(root, names=None):
    """One fresh FILE_READ_EA handle/query, shared for read/write/delete.

    Optional names exercises NtQueryEaFile's named-query path. The default
    enumerates EAs and matches names without case sensitivity.
    """
    if sys.platform != "win32":
        raise IdentityError("unsupported", 6, "Windows is required")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    ntdll = C.WinDLL("ntdll")
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p,
                                  W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL

    class IOSB(C.Structure):
        _fields_ = [("Status", C.c_size_t), ("Information", C.c_size_t)]

    query = ntdll.NtQueryEaFile
    query.argtypes = [W.HANDLE, C.POINTER(IOSB), C.c_void_p, W.ULONG, C.c_ubyte,
                      C.c_void_p, W.ULONG, C.c_void_p, C.c_ubyte]
    query.restype = W.LONG
    handle = kernel.CreateFileW(root, 0x8, 0x7, None, 3, 0x02000000, None)
    if handle == C.c_void_p(-1).value:
        error = C.get_last_error()
        status, code = ("access_denied", 4) if error == 5 else (
            ("mount_unavailable", 3) if error in (2, 3, 15, 21, 55, 1167) else ("io_error", 7))
        raise IdentityError(status, code, f"CreateFileW: WinError {error}")
    try:
        request = bytearray()
        if names:
            for i, name in enumerate(names):
                name = name.encode("ascii")
                record_len = (6 + len(name) + 3) & ~3
                request.extend(struct.pack("<IB", record_len if i + 1 < len(names) else 0, len(name)))
                request.extend(name + b"\0" + bytes(record_len - 6 - len(name)))
        ea_list = C.create_string_buffer(bytes(request)) if request else None
        buffer = C.create_string_buffer(65536)
        iosb = IOSB()
        status = query(handle, C.byref(iosb), buffer, len(buffer), 0,
                       ea_list, len(request), None, 1) & 0xffffffff
        if status in (0xC0000052, 0x80000012):
            return {}
        if status != 0:
            category, code = {
                0xC0000022: ("access_denied", 4),
                0xC000004F: ("unsupported", 6),
                0xC0000010: ("unsupported", 6),
                0xC00000BB: ("unsupported", 6),
                0xC0000013: ("mount_unavailable", 3),
                0xC00000A3: ("mount_unavailable", 3),
                0xC000009D: ("mount_unavailable", 3),
                0xC000026E: ("mount_unavailable", 3),
            }.get(status, ("io_error", 7))
            raise IdentityError(category, code, f"NtQueryEaFile: NTSTATUS 0x{status:08X}")
        if iosb.Information > len(buffer):
            raise IdentityError("invalid_response", 7, "EA response exceeds buffer")
        try:
            return parse_eas(buffer.raw[:iosb.Information])
        except (ValueError, UnicodeError) as e:
            raise IdentityError("invalid_response", 7, str(e)) from e
    finally:
        kernel.CloseHandle(handle)


def read_identity(root):
    root = normalize_root(root)
    return {"status": "ok", "mountPoint": root, **identity_from_eas(query_eas(root))}


def select_attributes(names=None, groups=None, all_attributes=False):
    selected = []
    for name in names or []:
        row = ATTRIBUTES.get(name.lower())
        if row is None:
            raise IdentityError("invalid_attribute", 2, f"Not a supported read-only attribute: {name}")
        selected.append(row)
    for group in groups or []:
        if group not in GROUPS:
            raise IdentityError("invalid_group", 2, group)
        selected.extend(row for row in CATALOG if row["group"] == group)
    if all_attributes:
        selected.extend(CATALOG)
    if not selected:
        selected.extend(row for row in CATALOG if row["group"] == "identity")
    return list({row["id"]: row for row in selected}.values())


def entry_path(root, relative):
    root = normalize_root(root)
    if not relative:
        return root
    # File queries stay beneath this explicit mount; no ADS, device paths,
    # relative-parent traversal, or ambiguous Win32 trailing-dot aliases.
    parts = relative.replace("/", "\\").split("\\")
    if any(not p or p in (".", "..") or p[-1:] in (".", " ") or
           any(c in p for c in ':*?"<>|\0') for p in parts):
        raise IdentityError("invalid_path", 2, "Use a relative file/directory path inside the mount")
    return root + "\\".join(parts)


def decode_attribute_response(data, row):
    if len(data) != 4096:
        raise IdentityError("invalid_response", 7, "Expected a 4096-byte attribute response")
    magic, version, status, length = struct.unpack_from("<IIiI", data)
    if magic != 0x474f544c or version != 1 or status > 0 or length > 4032 or (status and length):
        raise IdentityError("invalid_response", 7, "Invalid attribute protocol header")
    try:
        uid = data[16:56].split(b"\0", 1)[0].decode("ascii")
        if str(uuid.UUID(uid)) != uid.lower():
            raise ValueError("Invalid mount UUID")
    except (ValueError, UnicodeError) as e:
        raise IdentityError("invalid_response", 7, str(e)) from e
    if status:
        label = {-1040: "unavailable", -1037: "unsupported", -1049: "too_large"}.get(status, "read_error")
        return uid, {"status": label, "ltfsError": status}
    try:
        value = data[64:64 + length].decode("utf-8", errors="strict")
    except UnicodeError:
        return uid, {"status": "invalid_encoding"}
    if not value:
        return uid, {"status": "empty"}
    if row["name"] == "ltfs.volumeSerial" and not re.fullmatch(r"[A-Za-z0-9]{1,6}", value):
        raise IdentityError("invalid_identity", 7, "Invalid LTFS volume serial")
    if row["name"] == "ltfs.volumeUUID" and value.lower() != uid.lower():
        raise IdentityError("invalid_identity", 7, "UUID value does not match response mount UUID")
    if row["group"] == "health" and value == "-1":
        return uid, {"status": "unsupported"}
    if row["group"] == "encryption" and value.lower() == "unknown":
        return uid, {"status": "unknown"}
    result = {"status": "ok", "value": value}
    if row["unit"]:
        result["unit"] = row["unit"]
    return uid, result


def read_attributes(root, names=None, groups=None, all_attributes=False, relative_path=None):
    """Output-only DeviceIoControl queries on one fresh filesystem handle.

    Never opens a tape device. Per-attribute replies retain raw LTFS errors;
    transport/media failure discards the entire report, including earlier values.
    """
    root = normalize_root(root)
    path = entry_path(root, relative_path)
    if relative_path and not (names or groups or all_attributes):
        groups = ["file"]
    selected = select_attributes(names, groups, all_attributes)
    if relative_path and any(row["scope"] == "root" for row in selected):
        raise IdentityError("invalid_scope", 2, "File paths require file attributes (--group file)")
    expected_uuid = None
    if relative_path:
        # Bind entry queries to the explicitly selected root, even if an
        # intermediate directory is a reparse point to another mounted volume.
        expected_uuid = read_attributes(root, names=["ltfs.volumeUUID"])["volumeUUID"]
    if sys.platform != "win32":
        raise IdentityError("unsupported", 6, "Windows is required")
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.CloseHandle.restype = W.BOOL
    kernel.DeviceIoControl.argtypes = [W.HANDLE, W.DWORD, C.c_void_p, W.DWORD,
                                      C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
    kernel.DeviceIoControl.restype = W.BOOL
    # OPEN_REPARSE_POINT prevents following a final symlink outside this mount.
    # Extended paths also prevent DOS names such as CON being interpreted as
    # devices instead of entries in the mounted filesystem.
    handle = kernel.CreateFileW("\\\\?\\" + path, 0x8, 0x7, None, 3, 0x02200000, None)
    if handle == C.c_void_p(-1).value:
        error = C.get_last_error()
        category, code = ("access_denied", 4) if error == 5 else (
            ("mount_or_path_unavailable", 3) if error in (2, 3, 15, 21, 55, 1167) else ("io_error", 7))
        raise IdentityError(category, code, f"CreateFileW: WinError {error}")
    try:
        values, mount_uuid = {}, expected_uuid
        for row in selected:
            buffer = C.create_string_buffer(4096)
            returned = W.DWORD()
            control = (0xc657 << 16) | (row["id"] << 2)
            if not kernel.DeviceIoControl(handle, control, None, 0, buffer, 4096, C.byref(returned), None):
                error = C.get_last_error()
                category, code = ("access_denied", 4) if error == 5 else (
                    ("unsupported", 6) if error in (1, 50) else ("io_error", 7))
                raise IdentityError(category, code, f"DeviceIoControl: WinError {error}; {row['name']}")
            uid, value = decode_attribute_response(buffer.raw[:returned.value], row)
            if mount_uuid and uid != mount_uuid:
                raise IdentityError("media_changed", 3, "Mount UUID changed during query; report discarded")
            mount_uuid = uid
            values[row["name"]] = value
        # No successful-looking identity with a malformed UUID or serial.
        if all(n in values and values[n]["status"] == "ok" for n in NAMES):
            identity_from_eas({n.lower(): values[n]["value"].encode("utf-8") for n in NAMES})
        return {"status": "ok" if all(v["status"] == "ok" for v in values.values()) else "partial",
                "mountPoint": root, "path": path, "volumeUUID": mount_uuid, "attributes": values}
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mount_point", nargs="?")
    parser.add_argument("--list", action="store_true", help="List supported names without contacting a mount")
    parser.add_argument("--all", action="store_true", help="Query all read-only attributes, including hardware diagnostics")
    parser.add_argument("--get", action="append", metavar="NAME", help="Read an attribute; repeat to select more")
    parser.add_argument("--group", action="append", choices=GROUPS, help="Read a group; repeat to combine")
    parser.add_argument("--path", help="Relative entry path; use with --group file")
    args = parser.parse_args()
    try:
        if args.list:
            result, code = {"status": "ok", "attributes": CATALOG}, 0
        elif not args.mount_point:
            raise IdentityError("invalid_mount_point", 2, "Specify a drive root, e.g. T:\\")
        elif args.all or args.get or args.group or args.path:
            result = read_attributes(args.mount_point, args.get, args.group, args.all, args.path)
            code = 8 if result["status"] == "partial" else 0
        else:
            result, code = read_identity(args.mount_point), 0
    except IdentityError as e:
        result, code = {"status": e.status, "detail": str(e)}, e.code
    print(json.dumps(result, ensure_ascii=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
