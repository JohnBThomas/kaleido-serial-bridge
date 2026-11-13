# PyInstaller spec for "Kaleido Serial Bridge.app". Run through packaging/build.sh.
#
# CODESIGN_IDENTITY (optional): a "Developer ID Application: ..." identity. Without it the app is
# signed ad hoc, which runs on the Mac it was built on and on others after the user allows it.

import os
import sys

root = os.path.abspath(os.path.join(SPECPATH, '..'))
sys.path.insert(0, os.path.join(root, 'src'))
from kaleido_serial_bridge import APP_NAME, BUNDLE_ID, __version__

identity = os.environ.get('CODESIGN_IDENTITY') or None

a = Analysis(
    [os.path.join(SPECPATH, 'launcher.py')],
    pathex=[os.path.join(root, 'src')],
    datas=[(os.path.join(root, 'LICENSE'), '.'), (os.path.join(root, 'THIRD_PARTY_NOTICES.md'), '.')],
    hiddenimports=[],
    excludes=['tkinter', 'unittest', 'pydoc_data', 'test', 'lib2to3', 'setuptools', 'pip', 'PyInstaller'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='KaleidoSerialBridge',
    console=False,
    target_arch='arm64',
    codesign_identity=identity,
    entitlements_file=os.path.join(SPECPATH, 'entitlements.plist') if identity else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name='KaleidoSerialBridge')
app = BUNDLE(
    coll,
    name=f'{APP_NAME}.app',
    icon=os.path.join(SPECPATH, 'AppIcon.icns'),
    bundle_identifier=BUNDLE_ID,
    version=__version__,
    info_plist={
        'CFBundleDisplayName': APP_NAME,
        'CFBundleShortVersionString': __version__,
        'CFBundleVersion': __version__,
        'LSUIElement': True,                 # menu bar only: no Dock icon, no main window
        'LSMinimumSystemVersion': '13.0',
        'LSApplicationCategoryType': 'public.app-category.utilities',
        'NSHighResolutionCapable': True,
        'NSHumanReadableCopyright': 'MIT License. Not affiliated with Kaleido or the Artisan project.',
        # The app does not use Bluetooth itself. It asks macOS (system_profiler) whether the roaster is connected;
        # should macOS want consent for that, this is the reason it shows.
        'NSBluetoothAlwaysUsageDescription': 'Kaleido Serial Bridge asks macOS whether the roaster is connected, to show its status. It does not use Bluetooth itself.',
    },
)
