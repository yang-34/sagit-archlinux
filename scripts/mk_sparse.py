#!/usr/bin/env python3
"""Convert a raw ext4 image to Android sparse image (zero-run compression)."""
import os
import struct
import sys

BLK = 4096
MAX_BLK = 1024  # 4 MB per chunk
SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2


def main(src, dst):
    size = os.path.getsize(src)
    total_blks = (size + BLK - 1) // BLK
    body_path = dst + ".body"
    total_chunks = 0

    with open(src, "rb") as fi, open(body_path, "wb") as fo:
        remaining = size
        while remaining > 0:
            n = min(MAX_BLK * BLK, remaining)
            data = fi.read(n)
            if not data:
                break
            remaining -= len(data)
            nblk = (len(data) + BLK - 1) // BLK
            if data.count(0) == len(data):
                fo.write(struct.pack("<HHII", CHUNK_FILL, 0, nblk, 12 + 4))
                fo.write(struct.pack("<I", 0))
            else:
                if len(data) % BLK:
                    data += b"\x00" * (BLK - len(data) % BLK)
                fo.write(struct.pack("<HHII", CHUNK_RAW, 0, nblk, 12 + len(data)))
                fo.write(data)
            total_chunks += 1
            if total_chunks % 2000 == 0:
                print("chunks:", total_chunks, flush=True)

    with open(dst, "wb") as fd:
        fd.write(struct.pack("<IHHHHIIII", SPARSE_MAGIC, 1, 0, 28, 12,
                             BLK, total_blks, total_chunks, 0))
        with open(body_path, "rb") as fb:
            while True:
                buf = fb.read(1 << 20)
                if not buf:
                    break
                fd.write(buf)
    os.remove(body_path)
    print("blocks:", total_blks, "chunks:", total_chunks,
          "out:", os.path.getsize(dst))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
