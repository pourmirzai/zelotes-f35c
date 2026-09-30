# zelotes-f35c

Configure the Zelotes F-35C gaming mouse (Telink TLSR8271 + TLSR8373)
from Linux — no Windows driver needed. The vendor protocol was fully
reverse-engineered from the official Windows app (Wine + strace).

Working today (verified on hardware):
- 5 DPI stages + active profile switching (LED confirms)
- Light effects: breathing / rainbow / breathing-2 / static / wave /
  react-to-click / off
- Light color (RGB; the red channel renders ~half brightness on the LED)

macOS: the same 33-byte report-ID-4 packets via IOHIDManager
(`f35c_darwin.py`, experimental — untested on real hardware; the
binary may need `xattr -cr f35c` to pass Gatekeeper). Linux is the
reference platform.

## Install (one time, needs sudo)

```bash
sudo cp 99-zelotes-f35c.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

Then unplug/replug the receiver. If permission errors persist, a one-shot
`sudo chmod 666 /dev/hidraw*` also works (resets on replug).

## Use

```bash
python3 f35c.py info                # find device, check link
python3 f35c.py set-stage 2 1600    # set DPI of stage 1..5
python3 f35c.py set-profile 3       # switch active profile (LED updates)
python3 f35c.py set-mode 4          # light effect (0..6, see --help)
python3 f35c.py set-color 255 64 0  # light color
python3 f35c.py raw 04aa00aa...     # experiments
```

Dependencies: Python 3 stdlib only.

**Close the official Windows app (Wine) before using this tool** — a
running app rewrites the mouse config from its own cache.

## Supported devices

| USB ID | description |
|---|---|
| `320f:2261` | F-35C wireless receiver (2.4 GHz dongle) |
| `320f:222e` | F-35C wired mode |

Channel: HID interface 1, report ID 4 (usage page `0xFF1C`, usage
`0x92`), 33-byte packets; the device echoes every packet.

## Protocol notes

- Config pages: 24-byte chunks at blob offsets `0x00,0x18,0x30,0x48`
  written as a transaction (cmd `06`); a changed page carries flags
  `byte[2]=0x04`. DPI values are 16-bit little-endian (X,Y).
- Stage slots: page `0x00` bytes 23-26 (stage 1 + active profile byte
  at 20), page `0x18` bytes 9-12/18-21/27-30 (stages 2-4), page `0x30`
  bytes 12-15 (stage 5).
- Light: page-00 variant with RGB at packet bytes 14-16 and mode at
  byte 9, wrapped in `04dc03` ... `04001a06` apply ritual.
- Keepalives: `04aa00aa…02`, `0420001a06…02`.
- `capture_wine.log` holds the ground-truth packet capture; the full
  36 MB strace is kept out of git.

### Not yet mapped

Light motion-speed slider, brightness byte (exists — a 0 there turns
the LED off), report rate, button remap, macros, per-mode color table
(pages `0x60`/`0x78`). The capture recipe is in the repo history/README
of the research workspace; contributions welcome.

## Legal

This project is not affiliated with Zelotes or Telink. Use at your own
risk; configuration writes are verified by read-back where possible.
