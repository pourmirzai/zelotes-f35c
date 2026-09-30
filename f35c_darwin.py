"""macOS backend for the F-35C tool: IOHIDManager via ctypes.

EXPERIMENTAL — written from the IOHIDManager API, not yet tested on
real hardware (no Mac available during development). Report issues.
"""
import ctypes
import ctypes.util
import select  # noqa: F401  (linux side imports it)
import sys
import time

IOHID_LIB = 'IOHIDLib'
FRAMEWORK = '/System/Library/Frameworks/IOKit.framework/IOKit'

kIOHIDOptionsTypeNone = 0
kIOHIDReportTypeOutput = 1
kIOHIDReportTypeInput = 0

VENDOR = 0x320F
PIDS = (0x2261, 0x222E)
REPORT_ID = 4

CFRunLoopRunInMode = None


def _load():
    global CFRunLoopRunInMode
    iokit = ctypes.CDLL(FRAMEWORK)
    cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cf.CFRunLoopRunInMode.restype = ctypes.c_int32
    cf.CFRunLoopRunInMode.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_bool]
    CFRunLoopRunInMode = cf.CFRunLoopRunInMode
    for fn in ('CFStringCreateWithCString', 'CFDictionarySetValue',
               'CFNumberCreate', 'CFRelease', 'CFRunLoopGetCurrent',
               'CFArrayGetCount', 'CFArrayGetValueAtIndex'):
        getattr(cf, fn)
    api = {
        'IOHIDManagerCreate': ([ctypes.c_void_p, ctypes.c_uint32], ctypes.c_void_p),
        'IOHIDManagerSetDeviceMatching': ([ctypes.c_void_p, ctypes.c_void_p], None),
        'IOHIDManagerOpen': ([ctypes.c_void_p, ctypes.c_uint32], ctypes.c_int),
        'IOHIDManagerCopyDevices': ([ctypes.c_void_p], ctypes.c_void_p),
        'IOHIDDeviceOpen': ([ctypes.c_void_p, ctypes.c_uint32], ctypes.c_int),
        'IOHIDDeviceClose': ([ctypes.c_void_p], ctypes.c_int),
        'IOHIDDeviceSetReport': ([ctypes.c_void_p, ctypes.c_int, ctypes.c_int32,
                                  ctypes.c_char_p, ctypes.c_size_t], ctypes.c_int),
        'IOHIDDeviceGetReport': ([ctypes.c_void_p, ctypes.c_int, ctypes.c_int32,
                                  ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t)],
                                 ctypes.c_int),
        'IOHIDDeviceGetProperty': ([ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p),
    }
    for name, (argtypes, restype) in api.items():
        f = getattr(iokit, name)
        f.restype = restype
        f.argtypes = argtypes
    return iokit, cf


class MacHID:
    def __init__(self):
        self.iokit, self.cf = _load()
        self.dev = None
        iokit, cf = self.iokit, self.cf
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]

        def cstr(s):
            return ctypes.c_void_p(cf.CFStringCreateWithCString(None, s.encode(), 0))

        def match(key, val):
            d = ctypes.c_void_p(cf.CFDictionaryCreateMutable(None, 0, None, None))
            n = ctypes.c_void_p(cf.CFNumberCreate(None, 3, ctypes.byref(ctypes.c_int32(val))))
            cf.CFDictionarySetValue(d, cstr(key), n)
            return d

        mgr = ctypes.c_void_p(iokit.IOHIDManagerCreate(None, kIOHIDOptionsTypeNone))
        found = None
        for pid in PIDS:
            d = match('VendorID', VENDOR) if False else None
            # combine vendor+product in one dict
            dd = ctypes.c_void_p(cf.CFDictionaryCreateMutable(None, 0, None, None))
            nv = ctypes.c_void_p(cf.CFNumberCreate(None, 3, ctypes.byref(ctypes.c_int32(VENDOR))))
            npd = ctypes.c_void_p(cf.CFNumberCreate(None, 3, ctypes.byref(ctypes.c_int32(pid))))
            cf.CFDictionarySetValue(dd, cstr('VendorID'), nv)
            cf.CFDictionarySetValue(dd, cstr('ProductID'), npd)
            iokit.IOHIDManagerSetDeviceMatching(mgr, dd)
            if iokit.IOHIDManagerOpen(mgr, kIOHIDOptionsTypeNone) != 0:
                continue
            devs = ctypes.c_void_p(iokit.IOHIDManagerCopyDevices(mgr))
            if not devs:
                continue
            cnt = cf.CFArrayGetCount(devs)
            for i in range(cnt):
                cand = ctypes.c_void_p(cf.CFArrayGetValueAtIndex(devs, i))
                # skip non-interface-1 collections: prefer devices exposing
                # the vendor usage page 0xFF1C usage 0x92
                if cand:
                    found = cand
                    break
            if found:
                break
        if not found:
            raise RuntimeError('F-35C not found via IOHIDManager')
        if iokit.IOHIDDeviceOpen(found, kIOHIDOptionsTypeNone) != 0:
            raise RuntimeError('IOHIDDeviceOpen failed (permissions? allow in System Settings)')
        self.dev = found

    def write(self, data: bytes):
        n = self.iokit.IOHIDDeviceSetReport(self.dev, kIOHIDReportTypeOutput,
                                            REPORT_ID, data, len(data))
        if n != 0:
            raise RuntimeError(f'SetReport failed: {n}')

    def read_echo(self, wait=0.35):
        # the device echoes packets; a GetReport works as a lightweight check
        buf = ctypes.create_string_buffer(64)
        ln = ctypes.c_size_t(64)
        n = self.iokit.IOHIDDeviceGetReport(self.dev, kIOHIDReportTypeInput,
                                            REPORT_ID, buf, ctypes.byref(ln))
        if n == 0:
            return bytes(buf.raw[:ln.value])
        return None

    def close(self):
        if self.dev:
            self.iokit.IOHIDDeviceClose(self.dev)
