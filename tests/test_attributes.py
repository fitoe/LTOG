import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch, MagicMock
import ctypes as C
from ctypes import wintypes as W

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from ltfs_identity import (ATTRIBUTES, CATALOG, IdentityError, decode_attribute_response,
                           entry_path, read_attributes, select_attributes)

UUID = '11111111-2222-4333-8444-555555555555'


def reply(value=b'', status=0, uid=UUID):
    return (struct.pack('<IIiI', 0x474f544c, 1, status, len(value)) +
            uid.encode().ljust(40, b'\0') + bytes(8) + value.ljust(4032, b'\0'))


class AttributeTests(unittest.TestCase):
    def test_catalog_commands_unique_and_no_operations(self):
        self.assertEqual(len(CATALOG), len({r['id'] for r in CATALOG}))
        for r in CATALOG:
            self.assertNotIn(r['name'], ('ltfs.sync', 'ltfs.driveCaptureDump', 'ltfs.volumeLockState'))
            if r['ea']:
                self.assertNotIn(r['group'], ('capacity', 'health', 'alerts', 'encryption', 'file'))

    def test_selection_and_unknown_rejection(self):
        rows = select_attributes(['LTFS.VOLUMENAME'], ['volume'])
        self.assertEqual(sum(r['name'] == 'ltfs.volumeName' for r in rows), 1)
        for name in ('ltfs.driveCaptureDump', 'ltfs.sync', 'ltfs.vendor.HPE.dump', 'ltfs.unknown'):
            with self.assertRaises(IdentityError):
                select_attributes([name])
        with self.assertRaises(IdentityError):
            select_attributes(groups=['unknown'])

    def test_per_attribute_status_and_units(self):
        capacity = ATTRIBUTES['ltfs.mediadatapartitiontotalcapacity']
        health = ATTRIBUTES['ltfs.medialoads']
        encryption = ATTRIBUTES['ltfs.mediaencrypted']
        for data, row, expected in (
            (reply(b'0'), capacity, {'status': 'ok', 'value': '0', 'unit': 'MiB'}),
            (reply(b'-1'), health, {'status': 'unsupported'}),
            (reply(b'unknown'), encryption, {'status': 'unknown'}),
            (reply(), capacity, {'status': 'empty'}),
            (reply(status=-1040), capacity, {'status': 'unavailable', 'ltfsError': -1040}),
            (reply(status=-1037), capacity, {'status': 'unsupported', 'ltfsError': -1037}),
            (reply(status=-1049), capacity, {'status': 'too_large', 'ltfsError': -1049}),
            (reply(status=-9999), capacity, {'status': 'read_error', 'ltfsError': -9999}),
            (reply(b'\xff'), capacity, {'status': 'invalid_encoding'}),
        ):
            self.assertEqual(decode_attribute_response(data, row), (UUID, expected))

    def test_malformed_protocol(self):
        row = CATALOG[0]
        good = reply(b'ID0001')
        for data in (good[:100], b'FAIL' + good[4:], reply(uid='bad'),
                     good[:12] + struct.pack('<I', 4033) + good[16:], reply(b'x', -1040)):
            with self.assertRaises(IdentityError):
                decode_attribute_response(data, row)

    def test_path_validation_and_scope_before_open(self):
        self.assertEqual(entry_path('r:', '目录/file.txt'), 'R:\\目录\\file.txt')
        for path in ('../a', '/a', 'x/../a', 'x//a', 'x:a', 'file.', 'file ', '\\\\server\\file'):
            with self.assertRaises(IdentityError):
                entry_path('R:', path)
        with self.assertRaises(IdentityError) as e:
            read_attributes('R:', groups=['volume'], relative_path='file.txt')
        self.assertEqual(e.exception.status, 'invalid_scope')

    def test_cli_offline_catalog_and_rejected_operation(self):
        cli = [sys.executable, str(ROOT / 'tools/ltfs_identity.py')]
        result = subprocess.run(cli + ['--list'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(json.loads(result.stdout)['attributes']), len(CATALOG))
        result = subprocess.run(cli + ['Z:', '--get', 'ltfs.sync'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('attributes', json.loads(result.stdout))

    def test_mid_query_failure_discards_report_and_closes_handle(self):
        for changed_uuid in (False, True):
            kernel = MagicMock()
            kernel.CreateFileW.return_value = 123
            calls = []
            def query(handle, command, input_buffer, input_size, output, size, returned, overlapped):
                calls.append(command)
                if len(calls) == 2 and not changed_uuid:
                    C.set_last_error(5)
                    return False
                uid = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee' if len(calls) == 2 else UUID
                data = reply(b'ID0001' if len(calls) == 1 else uid.encode(), uid=uid)
                C.memmove(output, data, len(data))
                C.cast(returned, C.POINTER(W.DWORD))[0] = len(data)
                return True
            kernel.DeviceIoControl.side_effect = query
            with patch('ltfs_identity.C.WinDLL', return_value=kernel):
                with self.assertRaises(IdentityError) as e:
                    read_attributes('R:', groups=['identity'])
            self.assertEqual(e.exception.status, 'media_changed' if changed_uuid else 'access_denied')
            self.assertEqual(len(calls), 2)
            kernel.CloseHandle.assert_called_once_with(123)


if __name__ == '__main__':
    unittest.main()
