#!/usr/bin/env python3
"""Zelotes F-35C mouse configuration tool (Linux).

Devices: wireless receiver 320f:2261, wired mode 320f:222e.
Channel: HID interface 1, report ID 4, 33-byte packets; device echoes.

Protocol (reverse-engineered from the official Windows app via
Wine + strace; captures in this directory):

  packet = [04][seq][flags][cmd 06][0x18][cfg_offset][24-byte page][00 01 02]
  A commit = the four pages (blob offsets 0x00, 0x18, 0x30, 0x48) sent
  in order, ~0.35 s apart. A page whose content CHANGED must carry
  flags byte[2] = 0x04 (unchanged pages keep their captured flags).

Verified slots (hex-index = byte-offset * 2):
  active profile: page 0x00 byte 20 (0-4)
  stage 1 DPI:    page 0x00 bytes 23-26  (X,Y as 16-bit LE)
  stage 2 DPI:    page 0x18 bytes 9-12
  stage 3 DPI:    page 0x18 bytes 18-21
  stage 4 DPI:    page 0x18 bytes 27-30
  stage 5 DPI:    page 0x30 bytes 12-15

All five stages and profile switching verified on hardware
(2026-09-30, LED readout). Not yet mapped: RGB/lighting, report rate,
button remap, macros.
"""
import argparse
import glob
import os
import select
import sys
import time

__version__ = '0.2.1'

PIDS = (0x2261, 0x222E)

PAGE00 = '0474040618000000000504010000ff720000000201010100e803e803ff00000102'
PAGE18 = '04cf040618180000000807080700ff000100280a280a0000ff0100800c800cff02'
PAGE30 = '04b807061830000000ff0100a00fa00fffff00010058025802ff00ff0100580202'
PAGE48 = '04210806084800005802ff00ff010066ffff00010058025802ff00ff0100580202'

STAGE_SLOT = {
    1: ('PAGE00', 46, 8),
    2: ('PAGE18', 18, 8),
    3: ('PAGE18', 36, 8),
    4: ('PAGE18', 54, 8),
    5: ('PAGE30', 24, 8),
}
PROFILE_SLOT = ('PAGE00', 40, 2)
FLAGS_INDEX = 4

# Light (all verified on hardware): page-00 write built from the app's
# template, RGB at packet bytes 14-16 (the red channel renders at ~50%
# on the LED - compensate by using higher R values), mode at byte 9
# (0=breathing,1=rainbow,2=breathing2,3=static,4=wave,5=react,6=off),
# preceded by 04dc03 and followed by the apply commit 04001a06.
LIGHT_PKT = '04fc030618000000000004000000ff000000000201010100e803e803ff00000102'
LIGHT_OPEN = '04dc03' + '00' * 13
LIGHT_COMMIT = '04001a06' + '00' * 27 + '02'
LIGHT_MODES = {0: 'breathing', 1: 'rainbow', 2: 'breathing-2', 3: 'static',
               4: 'wave', 5: 'react-to-click', 6: 'off'}


def le16pair(v):
    b = f'{v & 0xff:02x}{(v >> 8) & 0xff:02x}'
    return b * 2


class F35CError(Exception):
    pass


def find_device():
    for pid in PIDS:
        for hr in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
            try:
                uev = open(hr + '/device/uevent').read()
            except OSError:
                continue
            if f'0003:0000320F:{pid:08X}' in uev and 'input1' in uev:
                return '/dev/' + os.path.basename(hr)
    return None


class F35C:
    def __init__(self, path=None):
        path = path or find_device()
        if not path:
            raise F35CError('F-35C not found (320f:2261 dongle / 320f:222e wired)')
        try:
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            raise F35CError(f'no permission for {path} (udev rule + replug, or sudo)')
        self.path = path
        self.pages = dict(PAGE00=PAGE00, PAGE18=PAGE18, PAGE30=PAGE30, PAGE48=PAGE48)

    def close(self):
        os.close(self.fd)

    def send(self, hexstr, wait=0.35):
        os.write(self.fd, bytes.fromhex(hexstr))
        end = time.time() + wait
        echo = None
        while time.time() < end:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                echo = os.read(self.fd, 64)
        return echo

    def _patch(self, page, idx, ln, value):
        p = self.pages[page]
        self.pages[page] = p[:idx] + value + p[idx + ln:]
        p = self.pages[page]
        self.pages[page] = p[:FLAGS_INDEX] + '04' + p[FLAGS_INDEX + 2:]

    def commit(self):
        for key in ('PAGE00', 'PAGE18', 'PAGE30', 'PAGE48'):
            self.send(self.pages[key])

    def set_stage(self, stage, dpi):
        if not 100 <= dpi <= 26000:
            raise F35CError('DPI out of range 100..26000')
        page, idx, ln = STAGE_SLOT[stage]
        self._patch(page, idx, ln, le16pair(dpi))
        self.commit()

    def _light(self, rgb=None, mode=None):
        b = bytearray(bytes.fromhex(LIGHT_PKT))
        if rgb:
            b[14:17] = bytes(rgb)
        if mode is not None:
            b[9] = mode
        self.send(LIGHT_OPEN)
        self.send(b.hex())
        self.send(LIGHT_COMMIT)

    def set_color(self, r, g, b):
        self._light(rgb=(r, g, b))

    def set_light_mode(self, mode):
        if mode not in LIGHT_MODES:
            raise F35CError('mode must be 0..6')
        self._light(mode=mode)

    def set_profile(self, n):
        page, idx, ln = PROFILE_SLOT
        self._patch(page, idx, ln, f'{n - 1:02x}')
        self.commit()


def main():
    ap = argparse.ArgumentParser(description=f'Zelotes F-35C configuration tool v{__version__}')
    ap.add_argument('--version', action='version', version=__version__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('info', help='show device path and check echo')
    p = sub.add_parser('set-stage', help='set DPI of stage 1..5')
    p.add_argument('stage', type=int, choices=range(1, 6))
    p.add_argument('dpi', type=int)
    p = sub.add_parser('set-profile', help='switch active profile 1..5')
    p.add_argument('n', type=int, choices=range(1, 6))
    p = sub.add_parser('set-color', help='set light color R G B (red renders ~half brightness on LED)')
    p.add_argument('r', type=int)
    p.add_argument('g', type=int)
    p.add_argument('b', type=int)
    p = sub.add_parser('set-mode', help='light effect: 0 breath,1 rainbow,2 breath2,3 static,4 wave,5 react,6 off')
    p.add_argument('mode', type=int, choices=range(7))
    p = sub.add_parser('raw', help='send a raw 33-byte packet (hex)')
    p.add_argument('hex')
    args = ap.parse_args()

    dev = F35C()
    try:
        if args.cmd == 'info':
            print(f'device: {dev.path}')
            echo = dev.send('04aa00aa' + '00' * 28 + '02')
            print('link:', 'responding (echo)' if echo else 'no echo')
        elif args.cmd == 'set-stage':
            dev.set_stage(args.stage, args.dpi)
            print(f'stage {args.stage} DPI -> {args.dpi}')
        elif args.cmd == 'set-profile':
            dev.set_profile(args.n)
            print(f'active profile -> {args.n} (LED updates immediately)')
        elif args.cmd == 'set-color':
            dev.set_color(args.r, args.g, args.b)
            print(f'light color -> {args.r},{args.g},{args.b}')
        elif args.cmd == 'set-mode':
            dev.set_light_mode(args.mode)
            print(f'light mode -> {args.mode} ({LIGHT_MODES[args.mode]})')
        elif args.cmd == 'raw':
            echo = dev.send(args.hex)
            print('echo:', echo.hex() if echo else None)
    finally:
        dev.close()


if __name__ == '__main__':
    main()
