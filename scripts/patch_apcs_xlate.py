#!/usr/bin/env python3
"""build-b89c: force an explicit of_xlate on the APCS IPC mailbox and log it.

Observed on b89b: APCSDIAG printed idx=0 for every send, i.e. chan->con_priv
was NULL, i.e. of_mbox_index_xlate() picked chans[0] instead of chans[15].
The DT is correct (<&apcs_glb 15>, #mbox-cells=1), so either args_count came
back 0 or the default xlate was never installed.

This patch:
  * installs an explicit xlate that honours args[0] (same semantics as
    of_mbox_index_xlate, but we can see it working)
  * logs args_count / ind / num_chans on the first few translations
"""
import os
import sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
path = os.path.join(root, 'drivers/mailbox/qcom-apcs-ipc-mailbox.c')
src = open(path).read()

# 1) add the xlate helper right before qcom_apcs_ipc_send_data
anchor_send = "static int qcom_apcs_ipc_send_data(struct mbox_chan *chan, void *data)\n"
helper = """static struct mbox_chan *qcom_apcs_ipc_xlate_dbg(struct mbox_controller *mbox,
					    const struct of_phandle_args *spec)
{
	u32 ind = 0;
	static int __n;

	if (spec->args_count)
		ind = spec->args[0];

	if (__n < 8) {
		pr_info("APCSX args_count=%d ind=%u num_chans=%d\\n",
			spec->args_count, ind, mbox->num_chans);
		__n++;
	}

	if (ind >= mbox->num_chans)
		return ERR_PTR(-EINVAL);

	return &mbox->chans[ind];
}

"""
if src.count(anchor_send) != 1:
    raise SystemExit('send_data anchor count=%d' % src.count(anchor_send))
src = src.replace(anchor_send, helper + anchor_send)

# 2) install it before registering the controller
anchor_reg = "\tret = devm_mbox_controller_register(&pdev->dev, &apcs->mbox);\n"
if src.count(anchor_reg) != 1:
    raise SystemExit('register anchor count=%d' % src.count(anchor_reg))
src = src.replace(anchor_reg, "\tapcs->mbox.of_xlate = qcom_apcs_ipc_xlate_dbg;\n" + anchor_reg)

open(path, 'w').write(src)
print('patched explicit xlate:', path)
