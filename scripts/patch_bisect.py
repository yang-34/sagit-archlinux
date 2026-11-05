#!/usr/bin/env python3
"""build-45: binary bisection of the GPU bring-up path via module param.

adreno.debug_stage (int, default 0 = full path):
  1 -> adreno_probe returns -ENODEV immediately
  2 -> return -ENODEV right before component_add
  3 -> adreno_load_gpu returns 0 without powering the GPU
  4 -> a5xx_hw_init returns 0 without touching registers
Set per boot with: /etc/modprobe.d/msm.conf -> options msm debug_stage=N
"""
import os
import re
import sys

K = sys.argv[1] if len(sys.argv) > 1 else "kernel"

HDR = "drivers/gpu/drm/msm/adreno/adreno_gpu.h"
DEV = "drivers/gpu/drm/msm/adreno/adreno_device.c"
GPU = "drivers/gpu/drm/msm/adreno/adreno_gpu.c"
A5 = "drivers/gpu/drm/msm/adreno/a5xx_gpu.c"


def read(rel):
    with open(os.path.join(K, rel), encoding="utf-8") as f:
        return f.read()


def write(rel, src):
    with open(os.path.join(K, rel), "w", encoding="utf-8") as f:
        f.write(src)


def gate(stage, label, ret="0"):
    return ('\tif (adreno_debug_stage >= %d) { pr_err("BISECT: %s\\n"); return %s; }\n'
            % (stage, label, ret))


def insert_at_func(src, sig, block):
    m = re.search(sig, src)
    if not m:
        return None
    brace = src.find("{", m.end())
    if brace < 0:
        return None
    eol = src.find("\n", brace)
    if eol < 0:
        return None
    return src[:eol + 1] + block + src[eol + 1:]


def main():
    hdr = read(HDR)
    if "extern int adreno_debug_stage;" not in hdr:
        idx = hdr.find("struct adreno_gpu {")
        if idx < 0:
            print("MISS header")
            return 1
        hdr = hdr[:idx] + "extern int adreno_debug_stage;\n\n" + hdr[idx:]
        write(HDR, hdr)

    dev = read(DEV)
    if "module_param_named(debug_stage" not in dev:
        incs = list(re.finditer(r"#include[^\n]*\n", dev))
        pos = incs[-1].end() if incs else 0
        decl = ('\nint adreno_debug_stage;\n'
                'module_param_named(debug_stage, adreno_debug_stage, int, 0644);\n'
                'MODULE_PARM_DESC(debug_stage, "GPU bring-up bisect stage (0=full)");\n')
        dev = dev[:pos] + decl + dev[pos:]
    dev = insert_at_func(dev, r"static int adreno_probe\s*\(",
                         gate(1, "stage1 adreno_probe skip", "-ENODEV")) or dev
    if "BISECT: stage2" not in dev:
        m = re.search(r"\n\treturn component_add\(", dev)
        if m:
            dev = dev[:m.start() + 1] + gate(2, "stage2 skip component_add", "-ENODEV") + dev[m.start() + 1:]
    write(DEV, dev)

    gpu = read(GPU)
    gpu = insert_at_func(gpu, r"int adreno_load_gpu\s*\(",
                         gate(3, "stage3 skip adreno_load_gpu", "0")) or gpu
    write(GPU, gpu)

    a5 = read(A5)
    a5 = insert_at_func(a5, r"static int a5xx_hw_init\s*\(",
                        gate(4, "stage4 skip a5xx_hw_init", "0")) or a5
    write(A5, a5)

    checks = [
        ("param", "module_param_named(debug_stage" in read(DEV)),
        ("stage1", "BISECT: stage1" in read(DEV)),
        ("stage2", "BISECT: stage2" in read(DEV)),
        ("stage3", "BISECT: stage3" in read(GPU)),
        ("stage4", "BISECT: stage4" in read(A5)),
        ("extern", "extern int adreno_debug_stage;" in read(HDR)),
    ]
    for name, ok in checks:
        print("%-8s %s" % (name, "OK" if ok else "MISS"))
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
