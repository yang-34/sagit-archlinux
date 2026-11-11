#!/usr/bin/env python3
"""Make diag-router usable for modem F3 capture.

Two fixes:

1) router/diag_cntl.c - crash on SET_ALL_MSG_MASK (0x7d/0x05)
   peripheral_broadcast_msg_mask(NULL) is called by that handler, and
   diag_cntl_send_msg_mask() dereferences `range` in the ALL_ENABLED branch:

       #0 diag_cmd_get_msg_mask
       #1 diag_cntl_send_msg_mask
       #2 peripheral_broadcast_msg_mask
       #3 handle_extended_message_configuration

   Substitute a local full range plus one all-ones mask word.

2) router/peripheral.c + peripheral.h + common_cmds.c - forward 0x7d upstream
   The router answers DIAG_CMD_EXTENDED_MESSAGE_CONFIGURATION locally and never
   tells the modem, so enabling messages has no effect on the modem and no F3
   stream appears.  Add peripheral_broadcast_raw() and call it for every 0x7d
   request before the local handling.
"""
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else 'router'


def patch(path, old, new, label):
    src = open(path, encoding='utf-8').read()
    if new in src:
        print('already patched:', label)
        return
    if old not in src:
        raise SystemExit('%s: anchor not found (%s)' % (path, label))
    open(path, 'w', encoding='utf-8').write(src.replace(old, new, 1))
    print('patched:', label)


# ---- 1. NULL range ---------------------------------------------------------
patch(
    ROOT + '/diag_cntl.c',
    """	} else if (status == DIAG_CTRL_MASK_ALL_ENABLED) {
		diag_cmd_get_msg_mask(range, &mask);
		num_items = 1;
	}""",
    """	} else if (status == DIAG_CTRL_MASK_ALL_ENABLED) {
		/* range may be NULL here: the 0x7d/0x05 handler calls
		 * peripheral_broadcast_msg_mask(NULL).  Use a local full range and a
		 * single all-ones mask word instead of dereferencing NULL. */
		static struct diag_ssid_range_t all_range = { 0, 0xffff };
		range = &all_range;
		num_items = 1;
		mask = malloc(sizeof(*mask));
		if (mask)
			*mask = 0xffffffff;
	}""",
    'diag_cntl.c ALL_ENABLED range')

# ---- 2a. add peripheral_broadcast_raw --------------------------------------
RAW_FN = """
void peripheral_broadcast_raw(const void *ptr, size_t len)
{
	struct peripheral *peripheral;
	struct list_head *item;

	list_for_each(item, &peripherals) {
		peripheral = container_of(item, struct peripheral, node);

		peripheral_send(peripheral, ptr, len);
	}
}
"""

patch(
    ROOT + '/peripheral.c',
    """void peripheral_broadcast_msg_mask(struct diag_ssid_range_t *range)""",
    RAW_FN.strip('\n') + """

void peripheral_broadcast_msg_mask(struct diag_ssid_range_t *range)""",
    'peripheral.c broadcast_raw')

patch(
    ROOT + '/peripheral.h',
    'void peripheral_broadcast_msg_mask(struct diag_ssid_range_t *range);',
    'void peripheral_broadcast_msg_mask(struct diag_ssid_range_t *range);\n'
    'void peripheral_broadcast_raw(const void *ptr, size_t len);',
    'peripheral.h prototype')

# ---- 2b. forward 0x7d ------------------------------------------------------
patch(
    ROOT + '/common_cmds.c',
    """static int handle_extended_message_configuration(struct diag_client *client,
						 const void *buf, size_t len)
{""",
    """static int handle_extended_message_configuration(struct diag_client *client,
						 const void *buf, size_t len)
{
	/* Also hand the request to the peripherals: the modem only starts
	 * streaming F3 messages after it sees this command itself. */
	peripheral_broadcast_raw(buf, len);
""",
    'common_cmds.c forward 0x7d')
