# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Visual LTFS index viewer: browse the off-tape index (`.schema`) backups of a
  volume's metadata directly in the GUI.
- LTO-9 tape support, via the updated LTFS engine.

### Changed

- The LTFS + WinFsp engine is now sourced from the
  [WinLtfs](https://github.com/rlaphoenix/WinLtfs) project and bundled as a
  pinned, checksum-verified release, rather than built from source in this
  repository.
- Updated the bundled engine from HPE StoreOpen 3.4.2 to 3.5.0.
- The About page now references the WinLtfs engine project.

### Fixed

- Write and index errors that occur when a file is closed are now surfaced
  instead of being silently dropped by the FUSE layer.
- The drive head position is verified after a `LOCATE`, failing on a mismatch to
  avoid reading or writing at the wrong position on the tape.

## [1.0.0] - 2026-06-12

### Added

- Initial release.

[Unreleased]: https://github.com/rlaphoenix/LTOG/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/rlaphoenix/LTOG/releases/tag/v1.0.0
