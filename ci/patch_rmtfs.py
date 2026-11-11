#!/usr/bin/env python3
"""Teach rmtfs about the two OEM EFS images the sagit modem asks for.

The modem requests

    /boot/modem_fsg_oem_1
    /boot/modem_fsg_oem_2

and upstream rmtfs rejects both ("request for unknown partition"), because the
table is compile-time and only covers fs1/fs2/fsc/fsg + the OnePlus/Oppo OEM
entries.  Alias them to the golden EFS partition (fsg); rmtfs runs with -r, and
write access goes to its shadow buffer.

This is the gate OPPO's sdm660 write-up describes: the modem only moves on to
the WLAN user PD once the EFS stage completes.
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else 'storage.c'

ANCHOR = """	/* Some OxygenOS firmware versions request this alternative path */
	{ "/oppo/oem_partion", "oem_stanvbk", "oem_stanvbk" },
"""
ADD = """	/* Xiaomi sagit: the modem asks for OEM EFS backups that do not exist as
	 * partitions on this device; serve them from the golden copy (fsg). */
	{ "/boot/modem_fsg_oem_1", "modem_fsg_oem_1", "fsg" },
	{ "/boot/modem_fsg_oem_2", "modem_fsg_oem_2", "fsg" },
"""

src = open(PATH, encoding='utf-8').read()
if 'modem_fsg_oem_1' in src:
    print('already patched')
elif ANCHOR not in src:
    raise SystemExit('%s: partition table anchor not found' % PATH)
else:
    open(PATH, 'w', encoding='utf-8').write(src.replace(ANCHOR, ANCHOR + ADD, 1))
    print('patched', PATH)
