#!/usr/bin/env python3
"""Instrument glink for the 6.1 msm8998-mainline tree (build-b61f).

Five signals, all tagged GLINKDIAG61:

  probe      - mbox channel + fifo lengths + negotiated feature set
  ver-req    - remote sent VERSION (modem is talking to us)
  ver-ack    - remote ACKed our VERSION  <- the decisive one: if this never
               prints, the modem never completed the glink handshake and every
               later tx is one-way by definition
  tx         - mbox_send_message() return for each packet
  fifo-full  - tx fifo exhausted, READ_NOTIF nudge fired

Note: the C newline escape is written as the placeholder @NL@ and substituted
with chr(92)+'n' at the end, so this file stays escape-safe no matter how it
is transported.
"""
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
NATIVE = os.path.join(ROOT, 'drivers/rpmsg/qcom_glink_native.c')

src = open(NATIVE, encoding='utf-8').read()


def sub_once(pattern, repl, label):
    global src
    new, n = re.subn(pattern, repl, src, count=1, flags=re.S)
    if n != 1:
        raise SystemExit('%s: matched %d times' % (label, n))
    src = new


# ---- 1. probe: channel, fifo sizes, features -------------------------------
sub_once(
    r'\t\treturn ERR_CAST\(glink->mbox_chan\);\n\t\}\n\n\tirq = of_irq_get',
    '\t\treturn ERR_CAST(glink->mbox_chan);\n'
    '\t}\n'
    '\n'
    '\tpr_info("GLINKDIAG61 probe chan=%px txlen=%zu rxlen=%zu feat=0x%x@NL@",\n'
    '\t\tglink->mbox_chan, glink->tx_pipe->length, glink->rx_pipe->length,\n'
    '\t\tglink->features);\n'
    '\n'
    '\tirq = of_irq_get',
    'probe')

# ---- 2. remote VERSION request ---------------------------------------------
sub_once(
    r'(static void qcom_glink_receive_version\(struct qcom_glink \*glink,\s*\n'
    r'\s*u32 version,\s*\n\s*u32 features\)\s*\n\{\n)',
    r'\1'
    '\tpr_info("GLINKDIAG61 ver-req ver=%u feat=0x%x@NL@", version, features);\n',
    'receive_version')

# ---- 3. remote VERSION ACK -------------------------------------------------
sub_once(
    r'(static void qcom_glink_receive_version_ack\(struct qcom_glink \*glink,\s*\n'
    r'\s*u32 version,\s*\n\s*u32 features\)\s*\n\{\n)',
    r'\1'
    '\tpr_info("GLINKDIAG61 ver-ack ver=%u feat=0x%x local_feat=0x%x@NL@",\n'
    '\t\tversion, features, glink->features);\n',
    'receive_version_ack')

# ---- 4. tx path: mbox_send_message() return --------------------------------
sub_once(
    r'\tqcom_glink_tx_write\(glink, hdr, hlen, data, dlen\);\n\n'
    r'\tmbox_send_message\(glink->mbox_chan, NULL\);\n'
    r'\tmbox_client_txdone\(glink->mbox_chan, 0\);\n',
    '\tqcom_glink_tx_write(glink, hdr, hlen, data, dlen);\n'
    '\n'
    '\t{\n'
    '\t\tint __r = mbox_send_message(glink->mbox_chan, NULL);\n'
    '\t\tpr_info_ratelimited("GLINKDIAG61 tx chan=%px ret=%d tlen=%u@NL@",\n'
    '\t\t\tglink->mbox_chan, __r, tlen);\n'
    '\t}\n'
    '\tmbox_client_txdone(glink->mbox_chan, 0);\n',
    'tx')

# ---- 5. tx fifo exhausted -> READ_NOTIF ------------------------------------
sub_once(
    r'(\t\tif \(!glink->sent_read_notify\) \{\n'
    r'\t\t\tglink->sent_read_notify = true;\n)'
    r'(\t\t\tqcom_glink_send_read_notify\(glink\);\n)',
    r'\1'
    '\t\t\tpr_info_ratelimited("GLINKDIAG61 fifo-full avail=%zu need=%u@NL@",\n'
    '\t\t\t\tqcom_glink_tx_avail(glink), tlen);\n'
    r'\2',
    'read_notify')

src = src.replace('@NL@', chr(92) + 'n')

open(NATIVE, 'w', encoding='utf-8', newline='\n').write(src)
print('patched:', NATIVE)
