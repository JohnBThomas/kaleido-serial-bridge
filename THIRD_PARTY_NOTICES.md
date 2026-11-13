# Third-party software in the app bundle

The packaged app contains the following, each under its own license. The full license texts
ship inside the bundle with the respective package, or are available at the links.

| Component | Used for | License |
|---|---|---|
| [Python](https://www.python.org) 3.14 (python-build-standalone build) | runtime | [PSF License](https://docs.python.org/3/license.html) |
| [pyserial](https://github.com/pyserial/pyserial) 3.5 | opening the serial port | BSD-3-Clause |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) (core, Cocoa) | macOS user interface | MIT |
| [PyInstaller](https://pyinstaller.org) bootloader | starting the bundled app | GPL-2.0-or-later with a [special exception](https://pyinstaller.org/en/stable/license.html) that allows distributing bundled apps under any license |

This project is not affiliated with, or endorsed by, Kaleido or the Artisan project. "Artisan"
refers to [Artisan roaster scope](https://artisan-scope.org); no Artisan code is included.
Menu bar and status symbols are Apple SF Symbols, drawn by macOS at run time. The app icon is the
project's own drawing.
