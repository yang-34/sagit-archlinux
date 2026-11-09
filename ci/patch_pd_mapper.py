"""Local dry-run of the CI patch step in gh-build/.github/workflows/wifi-services.yml.

Usage: py -3 patch_pd_mapper.py <pd-mapper.c>

Validates that every regex still matches the pinned pd-mapper source before the
workflow is pushed. The authoritative copy is the inline python3 heredoc in the
workflow; keep the two in sync.
"""
import re
import sys

p = sys.argv[1]
s = open(p).read()

ins1 = ("\n\tfprintf(stderr, \"[PD-MAPPER] get_domain_list name='%s'\\n\", req.name);")
s, n1 = re.subn(r"req\.name\[sizeof\(req\.name\)-1\] = '\\0';",
                lambda m: m.group(0) + ins1, s, count=1)

ins2 = ("fprintf(stderr, \"[PD-MAPPER] reply %u domain(s)\\n\", resp.domain_list_len);\n\t")
s, n2 = re.subn(r"if \(resp\.domain_list_len\)\n\s*resp\.domain_list_valid = 1;",
                lambda m: ins2 + m.group(0), s, count=1)

pfr_fn = r'''
static void handle_pfr(int sock, const struct qrtr_packet *pkt)
{
	struct servreg_loc_pfr_resp resp = {};
	struct servreg_loc_pfr_req req = {};
	DEFINE_QRTR_PACKET(resp_buf, 64);
	unsigned int txn;
	ssize_t len;
	int ret;

	ret = qmi_decode_message(&req, &txn, pkt, QMI_REQUEST,
				 SERVREG_LOC_PFR, servreg_loc_pfr_req_ei);
	if (ret < 0) {
		fprintf(stderr, "[PD-MAPPER] PFR decode failed %d\n", ret);
		return;
	}
	req.service[sizeof(req.service) - 1] = '\0';
	req.reason[sizeof(req.reason) - 1] = '\0';
	fprintf(stderr, "[PD-MAPPER] PFR service='%s' reason='%s'\n",
		req.service, req.reason);

	resp.result.result = QMI_RESULT_SUCCESS;
	resp.result.error = QMI_ERR_NONE;
	len = qmi_encode_message(&resp_buf, QMI_RESPONSE, SERVREG_LOC_PFR,
				 txn, &resp, servreg_loc_pfr_resp_ei);
	if (len < 0) {
		fprintf(stderr, "[PD-MAPPER] PFR encode failed %d\n", (int)len);
		return;
	}

	ret = qrtr_sendto(sock, pkt->node, pkt->port,
			  resp_buf.data, resp_buf.data_len);
	if (ret < 0)
		fprintf(stderr, "[PD-MAPPER] PFR send failed %d\n", ret);
}

'''
s, n3 = re.subn(r"static void handle_get_domain_list\(",
                lambda m: pfr_fn.lstrip('\n') + m.group(0), s, count=1)

ins3 = ("fprintf(stderr, \"[PD-MAPPER] qmi msg_id=0x%02x\\n\", msg_id);\n\n\t\t\t")
s, n4 = re.subn(r"switch \(msg_id\) \{", lambda m: ins3 + m.group(0), s, count=1)

s, n5 = re.subn(r'case SERVREG_LOC_PFR:\n(\s*)printf\("\[PD-MAPPER\] pfr\\n"\);',
                'case SERVREG_LOC_PFR:\n\\1handle_pfr(fd, &pkt);', s, count=1)

s, n6 = re.subn(r"(\n\tret = pd_load_maps\(\);)",
                "\n\tsetvbuf(stdout, NULL, _IONBF, 0);\\1", s, count=1)

print('hits', (n1, n2, n3, n4, n5, n6))
if (n1, n2, n3, n4, n5, n6) != (1, 1, 1, 1, 1, 1):
    sys.exit(1)
open(p, 'w').write(s)
print('patched ok')
