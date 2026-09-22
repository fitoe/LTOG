"""Build the pinned WinLtfs sources with LTOG's root identity EA patch."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("winltfs-source.zip", "rlaphoenix/WinLtfs", "v1.1.1",
     "8fd9d8ba574672fda6e48ab1fc80d97ba4275d39ce3ed03da3b7e0461892c2ff"),
    ("winfsp-source.zip", "winfsp/winfsp", "v2.1",
     "7b51f3c64fc5596eab315c8812f8b13e96d6830deef66e30df2019dafd3e0dd4"),
]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msys", type=Path, default=Path("C:/msys64"))
    parser.add_argument("--winfsp-dll", type=Path,
                        default=Path("C:/Program Files (x86)/WinFsp/bin/winfsp-x64.dll"))
    args = parser.parse_args()
    if not args.winfsp_dll.is_file():
        parser.error("Install WinFsp 2.1 or provide --winfsp-dll")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    for filename, repo, tag, digest in SOURCES:
        archive = build / filename
        if not archive.exists():
            urllib.request.urlretrieve(f"https://codeload.github.com/{repo}/zip/refs/tags/{tag}", archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Source checksum mismatch: {archive}")
        with zipfile.ZipFile(archive) as z:
            target = build / z.namelist()[0].split('/')[0]
            if not target.exists():
                z.extractall(build)
    source = build / "WinLtfs-1.1.1"
    import sys
    subprocess.run([sys.executable, str(ROOT / "native/update-patch.py"), "--check"], check=True)
    patch = ROOT / "native/root-identity.patch"
    check = subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, capture_output=True)
    if check.returncode == 0:
        subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
    else:
        # Accept only the exact already-applied patch; never ignore source drift.
        subprocess.run(["git", "apply", "--reverse", "--check", str(patch)], cwd=source, check=True)
    env = os.environ.copy()
    env.update(MSYSTEM="MINGW64", CHERE_INVOKING="1", LTOG_WINFSP_DLL=str(args.winfsp_dll))
    subprocess.run([str(args.msys / "usr/bin/bash.exe"), "-l", "native/build.sh"],
                   cwd=ROOT, env=env, check=True)
    (ROOT / "dist/winltfs/ltog-identity-build.txt").write_text(
        "WinLtfs v1.1.1 + root-identity.patch\npatch-sha256=" +
        hashlib.sha256(patch.read_bytes()).hexdigest() + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
