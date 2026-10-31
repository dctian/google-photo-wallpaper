"""Minimum release runtime patch levels reviewed on 2026-10-31."""
import struct
import sys

MINIMUM_PATCH = {(3,12):16, (3,13):18, (3,14):10, (3,15):2}


def supported_runtime(version):
    return (tuple(version[:2]) in MINIMUM_PATCH and
            version[2] >= MINIMUM_PATCH[tuple(version[:2])] and
            (len(version) < 4 or version[3] == 'final'))


def require_release_runtime():
    if (sys.implementation.name != 'cpython' or sys.platform != 'win32' or
            struct.calcsize('P') != 8 or not supported_runtime(sys.version_info)):
        raise SystemExit('Release builds require x64 Windows and patched CPython: '
                         '3.12.16+, 3.13.18+, 3.14.10+, or 3.15.2+ (final releases). '
                         'Use the Windows installer CI workflow; older runtimes must not be distributed.')
    print('Release runtime baseline passed: Python '+sys.version.split()[0])


if __name__=='__main__':
    require_release_runtime()
