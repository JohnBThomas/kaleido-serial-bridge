#!/usr/bin/env python3
"""Draws the app icon and writes packaging/AppIcon.icns. Needs PyObjC and macOS's iconutil.

The drawing is the project's own: a bridge between two dots. No system symbol is used, since
Apple's SF Symbols may not appear in app icons.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from AppKit import NSBezierPath, NSBitmapImageFileTypePNG, NSBitmapImageRep, NSColor, NSDeviceRGBColorSpace, NSGradient, NSGraphicsContext
from Foundation import NSMakePoint, NSMakeRect


def draw(size: int) -> bytes:
    bitmap = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(bitmap))
    unit = size / 1024.0
    # background: a rounded square with the margins macOS icons have
    inset = 100 * unit
    square = NSMakeRect(inset, inset, size - 2 * inset, size - 2 * inset)
    background = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(square, 185 * unit, 185 * unit)
    NSGradient.alloc().initWithStartingColor_endingColor_(
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.45, 0.27, 0.15, 1.0),
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.20, 0.11, 0.06, 1.0)).drawInBezierPath_angle_(background, -90.0)
    NSColor.whiteColor().set()
    # the deck
    deck = NSBezierPath.bezierPath()
    deck.setLineWidth_(46 * unit)
    deck.setLineCapStyle_(1)
    deck.moveToPoint_(NSMakePoint(222 * unit, 430 * unit))
    deck.lineToPoint_(NSMakePoint(802 * unit, 430 * unit))
    deck.stroke()
    # the arch
    arch = NSBezierPath.bezierPath()
    arch.setLineWidth_(46 * unit)
    arch.setLineCapStyle_(1)
    arch.moveToPoint_(NSMakePoint(300 * unit, 430 * unit))
    arch.curveToPoint_controlPoint1_controlPoint2_(NSMakePoint(724 * unit, 430 * unit), NSMakePoint(390 * unit, 740 * unit), NSMakePoint(634 * unit, 740 * unit))
    arch.stroke()
    # the hangers
    for x, top in ((400, 575), (512, 640), (624, 575)):
        hanger = NSBezierPath.bezierPath()
        hanger.setLineWidth_(30 * unit)
        hanger.setLineCapStyle_(1)
        hanger.moveToPoint_(NSMakePoint(x * unit, 430 * unit))
        hanger.lineToPoint_(NSMakePoint(x * unit, top * unit))
        hanger.stroke()
    # the two ends it connects
    for x in (222, 802):
        NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect((x - 58) * unit, (430 - 58) * unit, 116 * unit, 116 * unit)).fill()
    NSGraphicsContext.restoreGraphicsState()
    return bytes(bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}))


def main() -> int:
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AppIcon.icns')
    with tempfile.TemporaryDirectory() as temporary:
        iconset = os.path.join(temporary, 'AppIcon.iconset')
        os.mkdir(iconset)
        for points in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f'icon_{points}x{points}{"@2x" if scale == 2 else ""}.png'
                with open(os.path.join(iconset, name), 'wb') as f:
                    f.write(draw(points * scale))
        subprocess.run(['/usr/bin/iconutil', '-c', 'icns', iconset, '-o', target], check=True)
    print(target)
    return 0


if __name__ == '__main__':
    sys.exit(main())
