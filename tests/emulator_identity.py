"""Integration test using only disk-backed, read-only mounted test media.

Formats fresh local directories with the explicit 'file' backend, never a
TAPEn device. Terminates only the read-only emulator processes it creates.
"""
import ctypes
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from ltfs_identity import IdentityError, NAMES, identity_from_eas, query_eas, read_identity, read_attributes, CATALOG

DIST = ROOT / "dist/winltfs"


def wait_for(predicate, detail):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise AssertionError(detail)


def fingerprints(media):
    return {str(p.relative_to(media)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in media.rglob("*") if p.is_file()}


def main():
    if ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Run from an ordinary, non-elevated terminal")
    letters = ("R:", "S:")
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    if any(mask & (1 << (ord(letter[0]) - ord('A'))) for letter in letters):
        raise RuntimeError("R: and S: must both be unused; existing mounts are never touched")
    work = Path(tempfile.mkdtemp(prefix="identity-emulator-", dir=ROOT / "build"))
    report = {"ordinaryUser": True, "workDirectory": str(work), "checks": []}
    processes = []

    def mount(media, letter):
        log = (work / f"mount-{letter[0]}-{len(processes)}.log").open("wb")
        args = [str(DIST / "ltfs.exe"), letter, "-f", "-o", f"config_file={DIST.as_posix()}/ltfs.conf",
                "-o", "tape_backend=file", "-o", f"devname={media.as_posix()}", "-o", "ro"]
        process = subprocess.Popen(args, cwd=DIST, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        log.close()
        processes.append(process)
        wait_for(lambda: process.poll() is not None or Path(letter + "\\").exists(), "Mount timed out")
        if process.poll() is not None:
            raise AssertionError(f"Emulator mount failed: see {work}")
        return process

    def disconnect(process, letter):
        # Deliberately exercise disappearing mounts. This process has only a
        # read-only file backend; no physical mount is ever terminated.
        process.terminate()
        process.wait(timeout=15)
        wait_for(lambda: not Path(letter + "\\").exists(), "Emulator did not detach")
        try:
            read_identity(letter)
        except IdentityError:
            report["checks"].append(f"{letter} disconnected: no stale identity")
        else:
            raise AssertionError("Disconnected mount returned an identity")

    try:
        media_list, expected, before = [], [], []
        for serial in ("ID0001", "ID0002"):
            media = work / serial
            media.mkdir()
            # Both backend and local directory are explicit; no fallback driver.
            with (work / f"format-{serial}.log").open("wb") as log:
                subprocess.run([str(DIST / "mkltfs.exe"), "-i", str(DIST / "ltfs.conf"),
                                "-e", "file", "-d", media.as_posix(), "-s", serial, "-n", serial],
                               cwd=DIST, stdout=log, stderr=log, timeout=30, check=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            uuids = set()
            for p in media.iterdir():
                if p.is_file():
                    uuids.update(re.findall(rb"<volumeuuid>([^<]+)</volumeuuid>", p.read_bytes()))
                    # Prepare an empty-file fixture directly in the disk emulator
                    # index before mounting; never write through a mounted tape.
                    if b'<ltfsindex' in p.read_bytes():
                        tree = ET.fromstring(p.read_bytes())
                        tree.find('highestfileuid').text = '2'
                        directory = tree.find('directory')
                        file = ET.SubElement(directory.find('contents'), 'file')
                        for tag, value in [('name', 'metadata-test.txt'), ('length', '0'), ('readonly', 'false')]:
                            ET.SubElement(file, tag).text = value
                        for tag in ('creationtime', 'changetime', 'modifytime', 'accesstime', 'backuptime'):
                            ET.SubElement(file, tag).text = directory.find(tag).text
                        ET.SubElement(file, 'fileuid').text = '2'
                        p.write_bytes(ET.tostring(tree, encoding='UTF-8', xml_declaration=True))
            assert len(uuids) == 1, "Expected one UUID in freshly formatted disk fixture"
            expected.append(dict(zip(NAMES, (serial, uuids.pop().decode()))))
            before.append(fingerprints(media))
            media_list.append(media)
        first = mount(media_list[0], letters[0])
        second = mount(media_list[1], letters[1])
        for letter, identity in zip(letters, expected):
            actual = read_identity(letter)
            assert all(actual[k] == v for k, v in identity.items()), actual
            for names in (NAMES, tuple(n.upper() for n in NAMES)):
                assert identity_from_eas(query_eas(letter + "\\", names)) == identity
            metadata = query_eas(letter + "\\")
            assert metadata['ltfs.volumename'].decode() == identity[NAMES[0]]
            assert 'ltfs.indexgeneration' in metadata
            assert 'ltfs.medialoads' not in metadata, 'EA enumeration must not fetch health statistics'
            assert 'ltfs.drivecapturedump' not in metadata
            complete = read_attributes(letter, all_attributes=True)
            assert len(complete['attributes']) == len(CATALOG)
            assert complete['volumeUUID'] == identity[NAMES[1]]
            for name, value in identity.items():
                assert complete['attributes'][name] == {'status': 'ok', 'value': value}
            assert complete['attributes']['ltfs.volumeName']['value'] == identity[NAMES[0]]
            assert complete['attributes']['ltfs.mediaDataPartitionTotalCapacity']['unit'] == 'MiB'
            assert complete['attributes']['ltfs.startblock']['status'] == 'unavailable'
            assert complete['attributes']['ltfs.policyMaxFileSize']['status'] == 'unavailable'
            subset = read_attributes(letter, names=['LTFS.VOLUMENAME'], groups=['software'])
            assert subset['status'] == 'ok'
            assert len(subset['attributes']) == 5
            file_info = read_attributes(letter, relative_path='metadata-test.txt')
            assert file_info['volumeUUID'] == identity[NAMES[1]]
            assert file_info['attributes']['ltfs.fileUID']['value'] == '2'
            assert file_info['attributes']['ltfs.startblock']['status'] == 'unavailable'
            assert not query_eas(letter + '\\metadata-test.txt'), 'No virtual EAs on ordinary files'
            (work / f'attributes-{letter[0]}.json').write_text(json.dumps(complete, indent=2), encoding='utf-8')
            report["checks"].append({"mount": letter, "enumerationAndNamedQueries": actual})
            report['checks'].append(f"{letter} all {len(CATALOG)} attribute queries and targeted/group queries passed")
        assert expected[0][NAMES[1]] != expected[1][NAMES[1]]
        disconnect(first, letters[0])
        # Reuse the same drive letter for another medium, with S: still mounted.
        third = mount(media_list[1], letters[0])
        assert read_identity(letters[0])[NAMES[0]] == "ID0002"
        assert read_identity(letters[0])[NAMES[1]] == expected[1][NAMES[1]]
        report["checks"].append("Same drive remounted with a different medium: new identity")
        disconnect(third, letters[0])
        disconnect(second, letters[1])
        for media, snapshot in zip(media_list, before):
            assert fingerprints(media) == snapshot, "Read-only media content changed"
        report["checks"].append("Both disk media unchanged byte-for-byte")
        report["status"] = "passed"
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
        (work / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
