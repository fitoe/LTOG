import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from ltfs_identity import IdentityError, identity_from_eas, normalize_root, parse_eas

UUID = b"4bcd059c-015c-40b3-8e16-e50c5bc99015"


def record(name, value, last=True):
    name = name.encode("ascii") if isinstance(name, str) else name
    length = 9 + len(name) + len(value)
    padded = (length + 3) & ~3
    return (struct.pack("<IBBH", 0 if last else padded, 0, len(name), len(value)) +
            name + b"\0" + value + (b"" if last else bytes(padded - length)))


class IdentityTests(unittest.TestCase):
    def test_case_insensitive_aligned_enumeration(self):
        data = record("unrelated", b"abc", False)
        data += record("LTFS.VOLUMESERIAL", b"CP1316", False)
        data += record("ltfs.volumeUUID", UUID)
        self.assertEqual(identity_from_eas(parse_eas(data)), {
            "ltfs.volumeSerial": "CP1316", "ltfs.volumeUUID": UUID.decode()})

    def test_missing_and_empty_never_return_partial_identity(self):
        for eas in ({}, {"ltfs.volumeserial": b"CP1316"},
                    {"ltfs.volumeserial": b"", "ltfs.volumeuuid": UUID}):
            with self.assertRaises(IdentityError) as e:
                identity_from_eas(eas)
            self.assertEqual(e.exception.status, "identity_missing")

    def test_unrelated_non_ascii_ea(self):
        data = record(b"custom.\xff", b"\xff\xfe", False)
        data += record("ltfs.volumeSerial", b"ID0001", False)
        data += record("ltfs.volumeUUID", UUID)
        self.assertEqual(identity_from_eas(parse_eas(data))["ltfs.volumeSerial"], "ID0001")

    def test_invalid_identity(self):
        for serial, uid in ((b"CP\x0016", UUID), (b"CP1316", b"bad"), (b"\xff", UUID)):
            with self.assertRaises(IdentityError):
                identity_from_eas({"ltfs.volumeserial": serial, "ltfs.volumeuuid": uid})

    def test_malformed_records(self):
        valid = record("x", b"y")
        for data in (b"\0", valid[:-1], valid[:9] + b"!" + valid[10:],
                     struct.pack("<I", 4) + valid[4:],
                     record("x", b"y", False) + record("X", b"z")):
            with self.assertRaises(ValueError):
                parse_eas(data)

    def test_explicit_drive_root(self):
        self.assertEqual(normalize_root("t:"), "T:\\")
        self.assertEqual(normalize_root("R:/"), "R:\\")
        for root in ("", "T:folder", "T:\\folder", "\\\\.\\TAPE0", "../", "T:\\..\\"):
            with self.assertRaises(IdentityError):
                normalize_root(root)


if __name__ == "__main__":
    unittest.main()
