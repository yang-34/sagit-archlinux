#!/usr/bin/env python3
"""Fix diag-router crashing on SET_ALL_MSG_MASK (0x7d/0x05).

peripheral_broadcast_msg_mask(NULL) is called by the 0x7d/0x05 handler, and
diag_cntl_send_msg_mask() then dereferences `range` in the ALL_ENABLED branch
(`diag_cmd_get_msg_mask(range, &mask)` and later `pkt->range = *range;`).
With range == NULL the router segfaults inside diag_cmd_get_msg_mask:

    #0 diag_cmd_get_msg_mask
    #1 diag_cntl_send_msg_mask
    #2 peripheral_broadcast_msg_mask
    #3 handle_extended_message_configuration

The fix substitutes a local full-range plus a 32-bit all-ones mask, which is
the documented "all messages enabled" encoding.
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else 'router/diag_cntl.c'

OLD = """	} else if (status == DIAG_CTRL_MASK_ALL_ENABLED) {
		diag_cmd_get_msg_mask(range, &mask);
		num_items = 1;
	}"""

NEW = """	} else if (status == DIAG_CTRL_MASK_ALL_ENABLED) {
		/* range may be NULL here: the 0x7d/0x05 handler calls
		 * peripheral_broadcast_msg_mask(NULL).  Use a local full range and a
		 * single all-ones mask word instead of dereferencing NULL. */
		static struct diag_ssid_range_t all_range = { 0, 0xffff };
		range = &all_range;
		num_items = 1;
		mask = malloc(sizeof(*mask));
		if (mask)
			*mask = 0xffffffff;
	}"""

src = open(PATH, encoding='utf-8').read()
if OLD not in src:
    raise SystemExit('%s: ALL_ENABLED branch not found' % PATH)

src = src.replace(OLD, NEW, 1)
open(PATH, 'w', encoding='utf-8').write(src)
print('patched', PATH)
