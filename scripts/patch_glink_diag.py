#!/usr/bin/env python3
"""Add GLINKDIAG printks to drivers/rpmsg/qcom_glink_native.c.

Two things are invisible from userspace on this kernel (CONFIG_KPROBES/FTRACE off):
  * whether qcom_glink_native_probe() actually obtained a mailbox channel
  * what mbox_send_message() returns for every tx

If probe prints iserr=0 the channel exists and the APCS write happens; if tx
prints ret=-22 the channel is NULL and mbox_send_message bailed out early.
"""
import os
import sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
path = os.path.join(root, 'drivers/rpmsg/qcom_glink_native.c')
src = open(path).read()

old_probe = "\tglink->mbox_chan = mbox_request_channel(&glink->mbox_client, 0);\n"
new_probe = (
    old_probe
    + "\tpr_info(\"GLINKDIAG probe chan=%px iserr=%d\\n\",\n"
    + "\t\tglink->mbox_chan, IS_ERR(glink->mbox_chan));\n"
)
if src.count(old_probe) != 1:
    raise SystemExit('probe anchor count=%d' % src.count(old_probe))
src = src.replace(old_probe, new_probe)

# The same two lines appear twice (qcom_glink_tx and the READ_NOTIF path);
# only instrument the tx path, i.e. the first occurrence.
old_tx = (
    "\tmbox_send_message(glink->mbox_chan, NULL);\n"
    "\tmbox_client_txdone(glink->mbox_chan, 0);\n"
)
new_tx = (
    "\t{\n"
    "\t\tint __r = mbox_send_message(glink->mbox_chan, NULL);\n"
    "\t\tpr_info_ratelimited(\"GLINKDIAG tx chan=%px ret=%d\\n\",\n"
    "\t\t\tglink->mbox_chan, __r);\n"
    "\t}\n"
    "\tmbox_client_txdone(glink->mbox_chan, 0);\n"
)
if src.count(old_tx) != 2:
    raise SystemExit('tx anchor count=%d' % src.count(old_tx))
src = src.replace(old_tx, new_tx, 1)

open(path, 'w').write(src)
print('GLINKDIAG patched: %s' % path)
