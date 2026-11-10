#!/usr/bin/env python3
"""Instrument glink for the 6.1 msm8998-mainline tree (build-b61g).

Adds, on top of the b61f signals:

  /sys/kernel/debug/<glink-dev>/nudge
        write anything -> issue one extra mbox_send_message(NULL) on the very
        channel the driver holds, and log the return plus current tx avail.
        This is the decisive experiment: if a manual mailbox kick makes the
        modem answer a QMI request that it otherwise ignores, the problem is
        interrupt delivery, not the modem's rx path.

  fifo-full is now logged on *every* pass through the wait loop (ratelimited),
  not only the first one, so "modem stopped reading" is visible even after the
  READ_NOTIF flag was already set.

C newline escapes use the @NL@ placeholder, substituted with chr(92)+'n'.
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


# ---- 0. headers -------------------------------------------------------------
sub_once(
    r'#include <linux/mailbox_client\.h>\n',
    '#include <linux/mailbox_client.h>\n'
    '#include <linux/debugfs.h>\n'
    '#include <linux/fs.h>\n',
    'headers')

# ---- 1. probe: channel, fifo sizes, features, debugfs nudge file ------------
sub_once(
    r'\t\treturn ERR_CAST\(glink->mbox_chan\);\n\t\}\n\n\tirq = of_irq_get',
    '\t\treturn ERR_CAST(glink->mbox_chan);\n'
    '\t}\n'
    '\n'
    '\tpr_info("GLINKDIAG61 probe chan=%px txlen=%zu rxlen=%zu feat=0x%x@NL@",\n'
    '\t\tglink->mbox_chan, glink->tx_pipe->length, glink->rx_pipe->length,\n'
    '\t\tglink->features);\n'
    '\n'
    '\t{\n'
    '\t\tstruct dentry *__d = debugfs_create_dir(dev_name(dev), NULL);\n'
    '\t\tdebugfs_create_file("nudge", 0200, __d, glink,\n'
    '\t\t\t\t    &qcom_glink_nudge_fops);\n'
    '\t}\n'
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

# ---- 5. fifo pressure: log every wait, then the READ_NOTIF nudge ------------
sub_once(
    r'(\t\tif \(!glink->sent_read_notify\) \{\n)'
    r'(\t\t\tglink->sent_read_notify = true;\n)'
    r'(\t\t\tqcom_glink_send_read_notify\(glink\);\n)',
    '\t\tpr_info_ratelimited("GLINKDIAG61 fifo-full avail=%zu need=%u notify=%d@NL@",\n'
    '\t\t\t\t    qcom_glink_tx_avail(glink), tlen,\n'
    '\t\t\t\t    glink->sent_read_notify);\n'
    r'\1\2\3',
    'fifo_full')

# ---- 6. nudge implementation, inserted before the probe --------------------
NUDGE = '''static ssize_t qcom_glink_nudge_write(struct file *filp,
				      const char __user *ubuf,
				      size_t count, loff_t *ppos)
{
	struct qcom_glink *glink = filp->private_data;
	int ret;

	if (!glink->mbox_chan)
		return -ENODEV;

	ret = mbox_send_message(glink->mbox_chan, NULL);
	mbox_client_txdone(glink->mbox_chan, 0);

	pr_info("GLINKDIAG61 nudge chan=%px ret=%d txavail=%zu@NL@",
		glink->mbox_chan, ret, qcom_glink_tx_avail(glink));

	return count;
}

static const struct file_operations qcom_glink_nudge_fops = {
	.write = qcom_glink_nudge_write,
	.open = simple_open,
};

'''

sub_once(
    r'(struct qcom_glink \*qcom_glink_native_probe\()',
    NUDGE + r'\1',
    'nudge_impl')

src = src.replace('@NL@', chr(92) + 'n')

open(NATIVE, 'w', encoding='utf-8', newline='\n').write(src)
print('patched:', NATIVE)

# ---- 7. QRTR: disable TX flow control --------------------------------------
# The 2018 modem firmware never sends QRTR_TYPE_RESUME_TX, so the stock
# high-watermark (QRTR_TX_FLOW_HIGH = 10) stalls every (node,port) flow after
# a handful of packets - the sender then sleeps forever in qrtr_tx_wait(),
# which is exactly the "AP->modem dies after the first few packets" symptom
# (glink tx fifo is empty the whole time).  The glink fifo already provides
# back-pressure, so skip the credit wait.
QRTR = os.path.join(ROOT, 'net/qrtr/af_qrtr.c')
q = open(QRTR, encoding='utf-8').read()

anchor = (
    '\t/* Never set confirm_rx on non-data packets */\n'
    '\tif (type != QRTR_TYPE_DATA)\n'
    '\t\treturn 0;\n'
)
inject = (
    '\t/* Never set confirm_rx on non-data packets */\n'
    '\tif (type != QRTR_TYPE_DATA)\n'
    '\t\treturn 0;\n'
    '\n'
    '\t/* QRTRFLOW: peer never sends RESUME_TX, do not wait for credit */\n'
    '\tpr_info_ratelimited("QRTRFLOW skip dest=%d:%d type=%d@NL@",\n'
    '\t\t\t    dest_node, dest_port, type);\n'
    '\treturn 0;\n'
)
if q.count(anchor) != 1:
    raise SystemExit('qrtr anchor count=%d' % q.count(anchor))
q = q.replace(anchor, inject)
q = q.replace('@NL@', chr(92) + 'n')
open(QRTR, 'w', encoding='utf-8', newline='\n').write(q)
print('patched:', QRTR)
