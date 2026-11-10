#!/usr/bin/env python3
"""Instrument glink for the 6.1 msm8998-mainline tree (build-b61).

Two probes, same shape as the 5.15 build-b89a so the results are comparable:
  * qcom_glink_native_probe(): which mbox channel did we actually get
  * qcom_glink_tx():            mbox_send_message() return value

6.1 additionally has a READ_NOTIF path that nudges the remote when the TX
FIFO is short of space; log when it fires instead of silently spinning.
"""
import sys
import os

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
NATIVE = os.path.join(ROOT, 'drivers/rpmsg/qcom_glink_native.c')

src = open(NATIVE, encoding='utf-8').read()

# ---- 1. probe: report the channel we acquired -------------------------------
probe_old = (
    "\t\treturn ERR_CAST(glink->mbox_chan);\n"
    "\t}\n"
    "\n"
    "\tirq = of_irq_get(dev->of_node, 0);\n"
)
probe_new = (
    "\t\treturn ERR_CAST(glink->mbox_chan);\n"
    "\t}\n"
    "\n"
    "\tpr_info(\"GLINKDIAG61 probe chan=%px txlen=%zu rxlen=%zu\\n\",\n"
    "\t\tglink->mbox_chan, glink->tx_pipe->length, glink->rx_pipe->length);\n"
    "\n"
    "\tirq = of_irq_get(dev->of_node, 0);\n"
)
if src.count(probe_old) != 1:
    raise SystemExit('probe anchor count=%d' % src.count(probe_old))
src = src.replace(probe_old, probe_new)

# ---- 2. tx path: report mbox_send_message() return --------------------------
# Only the main tx path writes "hdr, hlen, data, dlen" right before it.
tx_old = (
    "\tqcom_glink_tx_write(glink, hdr, hlen, data, dlen);\n"
    "\n"
    "\tmbox_send_message(glink->mbox_chan, NULL);\n"
    "\tmbox_client_txdone(glink->mbox_chan, 0);\n"
)
tx_new = (
    "\tqcom_glink_tx_write(glink, hdr, hlen, data, dlen);\n"
    "\n"
    "\t{\n"
    "\t\tint __r = mbox_send_message(glink->mbox_chan, NULL);\n"
    "\t\tpr_info_ratelimited(\"GLINKDIAG61 tx chan=%px ret=%d tlen=%u\\n\",\n"
    "\t\t\tglink->mbox_chan, __r, tlen);\n"
    "\t}\n"
    "\tmbox_client_txdone(glink->mbox_chan, 0);\n"
)
if src.count(tx_old) != 1:
    raise SystemExit('tx anchor count=%d' % src.count(tx_old))
src = src.replace(tx_old, tx_new)

# ---- 3. READ_NOTIF: does the nudge path ever run? ---------------------------
notify_old = (
    "\t\tif (!glink->sent_read_notify) {\n"
    "\t\t\tglink->sent_read_notify = true;\n"
    "\t\t\tqcom_glink_send_read_notify(glink);\n"
    "\t\t}\n"
)
notify_new = (
    "\t\tif (!glink->sent_read_notify) {\n"
    "\t\t\tglink->sent_read_notify = true;\n"
    "\t\t\tpr_info_ratelimited(\"GLINKDIAG61 fifo-full avail=%zu need=%u -> READ_NOTIF\\n\",\n"
    "\t\t\t\tqcom_glink_tx_avail(glink), tlen);\n"
    "\t\t\tqcom_glink_send_read_notify(glink);\n"
    "\t\t}\n"
)
if src.count(notify_old) != 1:
    raise SystemExit('notify anchor count=%d' % src.count(notify_old))
src = src.replace(notify_old, notify_new)

open(NATIVE, 'w', encoding='utf-8', newline='\n').write(src)
print('patched:', NATIVE)
