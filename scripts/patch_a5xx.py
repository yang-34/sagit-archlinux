import os
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "kernel"
path = os.path.join(root, "drivers/gpu/drm/msm/adreno/a5xx_gpu.c")
with open(path) as f:
    src = f.read()

needle = "gpu_write(gpu, REG_A5XX_RBBM_SECVID_TRUST_CNTL, 0x0);"
replacement = "/* build-38 diagnostic: SECVID_TRUST_CNTL write skipped */"

if needle not in src:
    raise SystemExit("needle not found in %s" % path)

src = src.replace(needle, replacement, 1)
with open(path, "w") as f:
    f.write(src)
print("patched", path)
