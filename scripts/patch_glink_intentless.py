#!/usr/bin/env python3
"""build-b89b: two changes, both aimed at the "modem never reads our FIFO" wall.

1) qcom_glink_smem.c
   Pass intentless=true for the modem (remote_pid == 1) only.
   Rationale: if the Xiaomi modem firmware speaks intentless glink, the
   intent-based OPEN/ACK handshake never completes, the channel stays half
   open (rx works, tx does not), and the modem never consumes our TX FIFO.
   ADSP (pid 2) and SLPI (pid 3) are left on the old path so their
   already-working channels cannot regress.

2) qcom-apcs-ipc-mailbox.c
   Read the IPC register back right after writing it, so dmesg tells us
   whether the APCS write actually landed (rb=0x00008000 for bit 15)
   or the register reads back zero.
"""
import os
import re
import sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'

# ---- 1. intentless for modem only -----------------------------------------
glink_path = os.path.join(root, 'drivers/rpmsg/qcom_glink_smem.c')
src = open(glink_path).read()

pat = re.compile(
    r'(qcom_glink_native_probe\(dev,\s*GLINK_FEATURE_INTENT_REUSE,\s*'
    r'&rx_pipe->native,\s*&tx_pipe->native,\s*)false(\);)'
)
if len(pat.findall(src)) != 1:
    raise SystemExit('glink probe anchor count=%d' % len(pat.findall(src)))
src = pat.sub(r'\1remote_pid == 1\2', src)
open(glink_path, 'w').write(src)
print('patched intentless (modem only):', glink_path)

# ---- 2. APCS write readback ----------------------------------------------
apcs_path = os.path.join(root, 'drivers/mailbox/qcom-apcs-ipc-mailbox.c')
src = open(apcs_path).read()

old = """	unsigned long idx = (unsigned long)chan->con_priv;

	return regmap_write(apcs->regmap, apcs->offset, BIT(idx));
"""
new = """	unsigned long idx = (unsigned long)chan->con_priv;
	int ret = regmap_write(apcs->regmap, apcs->offset, BIT(idx));
	{
		static int __n;
		if (__n < 8) {
			unsigned int __v = 0;
			regmap_read(apcs->regmap, apcs->offset, &__v);
			dev_info(apcs->mbox.dev,
				 "APCSDIAG off=%lu idx=%lu ret=%d rb=0x%08x\\n",
				 apcs->offset, idx, ret, __v);
			__n++;
		}
	}
	return ret;
"""
if src.count(old) != 1:
    raise SystemExit('apcs send_data anchor count=%d' % src.count(old))
src = src.replace(old, new)
open(apcs_path, 'w').write(src)
print('patched APCS readback:', apcs_path)
