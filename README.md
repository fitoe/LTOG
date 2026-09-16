<p align="center">
  <img src="gui/Assets/icon.png" alt="" width="16" /> <a href="https://github.com/rlaphoenix/LTOG">LTOG</a>
  <br/>
  <sup><em>Modern LTO Tape Manager with <a href="https://www.lto.org/ltfs/">LTFS 2.4</a> and <a href="https://github.com/winfsp/winfsp">WinFsp-based tape mounting</a></em></sup>
</p>

<p align="center">
  <a href="https://github.com/rlaphoenix/LTOG/blob/main/LICENSE">
    <img src="https://img.shields.io/:license-GPL%203.0-blue.svg" alt="License">
  </a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11%20x64-informational" alt="Platform">
  <a href="https://dotnet.microsoft.com">
    <img src="https://img.shields.io/badge/.NET-8.0-512BD4" alt=".NET 8">
  </a>
  <img src="https://img.shields.io/badge/LTFS-2.4.0-blue" alt="LTFS 2.4.0">
  <a href="https://winfsp.dev">
    <img src="https://img.shields.io/badge/WinFsp-2.1-informational" alt="WinFsp">
  </a>
</p>

![Screenshot](screenshot.png)

> [!WARNING]
> It is highly recommended to Copy files instead of Moving files or risk losing your data. While every
> reasonable measure has been taken to prevent data loss, it can still occur in rare cases or with aging
> hardware. Tape drives have an internal memory buffer that stores written data before flushing it to the
> tape. When Moving files to the mount point LTOG creates, it gets written to this memory buffer that we
> cannot control. Once moved to the memory buffer, Windows marks the original file for deletion. If the
> Tape drive has an unexpected or intermittent error or failure while its still in the internal memory
> buffer, you may lose your data. Copying instead of moving prevents this issue as you will retain the
> original file on your computer. Only once you unmount the tape should you delete any original files.

## Features

- 🖥️ Native WinUI 3 GUI
- 📼 LTO-5+ Support
- 🗂️ LTFS 2.4.0 Support
- 💽 Virtual Drive Mounting
- 💾 Automatic Index Backup
- 🔒 Honors Write-Protection and Read-Only
- 🛡️ WHQL-signed Drivers
- ❤️ Forever FLOSS (GPLv3)

## Requirements

- Windows 10/11, or Windows Server 2019 or newer (64-bit only)
- An LTO-5 or newer cartridge with a compatible LTO Tape Drive

See [Supported Tape Drives](https://github.com/rlaphoenix/WinLtfs#supported-tape-drives)
for a list of tape drives that are known to be compatible.

## Building

First clone and enter the repository:

```shell
git clone https://github.com/rlaphoenix/LTOG
cd LTOG
```

Then build the LTFS+WinFsp engine, the GUI, and the Installer with `.\build`.
Instructions below show how to individually build each part of the project.

### 1. WinLtfs (LTFS + WinFsp)

The LTFS executables, tape backends, and `winfsp-x64.dll` are built by the
[WinLtfs](https://github.com/rlaphoenix/WinLtfs) project and consumed here as a
pinned release.

To build the engine from source yourself (MSYS2 + WinFsp toolchain), follow the
build instructions in the [WinLtfs](https://github.com/rlaphoenix/WinLtfs) repo,
then copy its `dist/` output over LTOG's `dist/`.

### 2. GUI

Install the .NET 8 SDK:

```shell
winget install -e Microsoft.DotNet.SDK.8
```

In PowerShell:

```powershell
cd gui  # enter gui folder
dotnet build LTOG.Gui.csproj -c Release -p:Platform=x64  # build (self-contained)
robocopy "bin\x64\Release\net8.0-windows10.0.19041.0\win-x64" "..\dist\gui" /E  # self-contained output -> ..\dist
```

### 3. Installer

With `dist/` fully populated (LTFS engine + GUI), build the Windows installer:

```powershell
pwsh -ExecutionPolicy Bypass -File installer\build-installer.ps1
```

It fetches what it needs and writes `setup.exe` to `installer\Output\`.

## Credit

This project stands almost entirely on other people's work:

- **IBM** - the original Linear Tape File System Single Drive Edition;
  `libltfs` and the core utilities are IBM Almaden Research code.
- **Hewlett-Packard / HPE** - the Windows port (StoreOpen 3.5.0) and the
  `ltotape` drive backend for HP LTO drives.
- **OSR Open Systems Resources, Inc.** - the original Windows FUSE
  integration work inside the HP tree.
- **nix-community** - for preserving HPE's LGPL LTFS source after HPE stopped
  distributing it
  ([nix-community/hpe-ltfs](https://github.com/nix-community/hpe-ltfs)).
- **leavelet** - for preserving HPE's LGPL LTFS source (StoreOpen 3.5.0) after
  HPE stopped distributing it
  ([leavelet/ltfs-hp](https://github.com/leavelet/ltfs-hp)).
- **Bill Zissimopoulos** - [WinFsp](https://winfsp.dev), whose excellent
  FUSE-compatible layer and properly signed driver make this whole approach
  possible.
- Assistance with porting and orchestration by Claude (Anthropic).

## Licensing

LTOG as a whole is distributed under the **GNU General Public License v3.0**
(see [LICENSE](LICENSE)).

A full per-component inventory — every redistributed binary, its license,
copyright, and corresponding source — is in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), with the license texts in
[`licenses/`](licenses/). The installer ships these alongside the binaries. In
summary:

- Everything original to this repository (tooling, GUI, installer,
  documentation) is **GPL-3.0**.
- The LTFS engine + WinFsp port (from
  [WinLtfs](https://github.com/rlaphoenix/WinLtfs)) is **LGPL-2.1**, © IBM,
  HP/HPE, OSR, so it remains upstreamable. (LGPL-2.1 code may be conveyed as part
  of a GPLv3 work via LGPL §3.)
- **WinFsp** is GPLv3 with a FLOSS exception, © Bill Zissimopoulos. Its
  redistributable `winfsp-x64.dll` is shipped in `dist/`, and the **installer
  bundles the official WinFsp 2.1 MSI** and runs it to install the signed kernel
  driver. The FLOSS exception is what lets the LGPL-2.1 LTFS binaries link the
  WinFsp FUSE layer. Source: <https://github.com/winfsp/winfsp> (tag `v2.1`).
- Binary `dist/` folders also contain MSYS2-built runtime DLLs: libxml2 (MIT),
  ICU (Unicode v3), GNU libiconv (LGPL-2.1), zlib (Zlib), MinGW-w64 winpthreads
  (MIT/BSD), and the GCC runtime `libgcc`/`libstdc++` (GPL-3.0 with the GCC
  Runtime Library Exception).
- The GUI (`dist/gui/`) is published **self-contained**: it bundles the **.NET 8
  runtime** (MIT) and the **Microsoft Windows App SDK / WinUI 3** runtime plus
  WebView2 (Microsoft Software License Terms). The Windows App SDK AI/ML stack
  (ONNX Runtime, DirectML, WinML) is trimmed out — LTOG uses no AI APIs.
  Nothing extra is installed separately: the WinUI 3 binaries import only the
  OS-provided Universal CRT (Windows 10 1809+), so no .NET or Visual C++
  redistributable is needed.

---

© rlaphoenix 2026
