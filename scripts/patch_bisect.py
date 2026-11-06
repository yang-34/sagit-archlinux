#!/usr/bin/env python3
"""build-47: NON-cumulative bitmask gates for GPU bring-up bisection.

adreno.debug_stage (int, default 0 = full path) is a bitmask (no >= semantics):
  bit0 (1)   : adreno_probe entry            -> return -ENODEV
  bit1 (2)   : adreno_bind entry             -> return -ENODEV
  bit2 (4)   : adreno_load_gpu entry         -> return NULL
  bit3 (8)   : after adreno_load_fw          -> return NULL (no power up)
  bit4 (16)  : after pm_runtime_get_sync     -> put + return NULL (powered, no hw init)
  bit5 (32)  : a5xx_hw_init entry            -> return 0 (no register access)
  bit6 (64)  : before adreno_hw_init         -> return 0 (after first register block)
  bit7 (128) : before ringbuffer setup       -> return 0 (after ucode load)
  bit8 (256) : before a5xx_power_init        -> return 0 (after ME init)
  bit9 (512) : before a5xx_zap_shader_init   -> return 0

Set per boot: /etc/modprobe.d/msm.conf -> options msm debug_stage=N
Tolerant: missing anchors are reported, build continues.
"""
import os
import re
import sys

K = sys.argv[1] if len(sys.argv) > 1 else "kernel"
HDR = "drivers/gpu/drm/msm/adreno/adreno_gpu.h"
DEV = "drivers/gpu/drm/msm/adreno/adreno_device.c"
A5 = "drivers/gpu/drm/msm/adreno/a5xx_gpu.c"


def read(rel):
    with open(os.path.join(K, rel), encoding="utf-8") as f:
        return f.read()


def write(rel, src):
    with open(os.path.join(K, rel), "w", encoding="utf-8") as f:
        f.write(src)


def gate(bit, label, ret):
    return ('\tif (adreno_debug_stage & (1 << %d)) { pr_err("BISECT: %s\\n"); return %s; }\n'
            % (bit, label, ret))


def insert_after_brace(src, pattern, block):
    m = re.search(pattern, src)
    if not m:
        return None
    brace = src.find("{", m.end())
    if brace < 0:
        return None
    eol = src.find("\n", brace)
    if eol < 0:
        return None
    return src[:eol + 1] + block + src[eol + 1:]


def insert_before(src, pattern, block):
    m = re.search(pattern, src)
    if not m:
        return None
    line_start = src.rfind("\n", 0, m.start()) + 1
    return src[:line_start] + block + src[line_start:]


def apply(src, label, fn, pattern, block):
    if label in src:
        return src
    out = fn(src, pattern, block)
    if out is None:
        print("MISS    %s" % label)
        return src
    print("OK      %s" % label)
    return out


def main():
    hdr = read(HDR)
    if "extern int adreno_debug_stage;" not in hdr:
        idx = hdr.find("struct adreno_gpu {")
        if idx >= 0:
            hdr = hdr[:idx] + "extern int adreno_debug_stage;\n\n" + hdr[idx:]
            write(HDR, hdr)

    dev = read(DEV)
    if "module_param_named(debug_stage" not in dev:
        incs = list(re.finditer(r"#include[^\n]*\n", dev))
        pos = incs[-1].end() if incs else 0
        dev = (dev[:pos]
               + '\nint adreno_debug_stage;\n'
                 'module_param_named(debug_stage, adreno_debug_stage, int, 0644);\n'
                 'MODULE_PARM_DESC(debug_stage, "GPU bring-up bisect bitmask (0=full)");\n'
               + dev[pos:])

    dev = apply(dev, "BISECT: bit0", insert_after_brace, r"static int adreno_probe\s*\(",
                gate(0, "bit0 skip adreno_probe", "-ENODEV"))
    dev = apply(dev, "BISECT: bit1", insert_after_brace, r"static int adreno_bind\s*\(",
                gate(1, "bit1 skip adreno_bind", "-ENODEV"))
    dev = apply(dev, "BISECT: bit2", insert_after_brace, r"struct msm_gpu \*adreno_load_gpu\s*\(",
                gate(2, "bit2 skip adreno_load_gpu", "NULL"))
    dev = apply(dev, "BISECT: bit3", insert_before, r"\n\s*pm_runtime_set_active\(&pdev->dev\);",
                gate(3, "bit3 after fw load, before power", "NULL"))
    dev = apply(dev, "BISECT: bit4", insert_before, r"\n\s*mutex_lock\(&dev->struct_mutex\);",
                '\tif (adreno_debug_stage & (1 << 4)) { pr_err("BISECT: bit4 powered, skip hw_init\\n");'
                ' pm_runtime_put_sync(&pdev->dev); return NULL; }\n')
    write(DEV, dev)

    a5 = read(A5)
    a5 = apply(a5, "BISECT: bit5", insert_after_brace, r"static int a5xx_hw_init\s*\(",
               gate(5, "bit5 skip a5xx_hw_init", "0"))
    a5 = apply(a5, "BISECT: bit6", insert_before, r"\n\tret = adreno_hw_init\(gpu\);",
               gate(6, "bit6 before adreno_hw_init", "0"))
    a5 = apply(a5, "BISECT: bit7", insert_before, r"\n\tgpu_write64\(gpu, REG_A5XX_CP_RB_BASE,",
               gate(7, "bit7 before ringbuffer setup", "0"))
    a5 = apply(a5, "BISECT: bit8", insert_before, r"\n\tret = a5xx_power_init\(gpu\);",
               gate(8, "bit8 before a5xx_power_init", "0"))
    a5 = apply(a5, "BISECT: bit9", insert_before, r"\n\tret = a5xx_zap_shader_init\(gpu\);",
               gate(9, "bit9 before zap shader init", "0"))

    if "BISECT: bit10" not in a5:
        old = "\t\ta5xx_gpmu_ucode_init(gpu);\n"
        if a5.count(old) == 1:
            a5 = a5.replace(old,
                            '\t\tif (adreno_debug_stage & (1 << 10)) {\n'
                            '\t\t\tpr_err("BISECT: bit10 skip gpmu ucode init\\n");\n'
                            '\t\t} else {\n'
                            '\t\t\ta5xx_gpmu_ucode_init(gpu);\n'
                            '\t\t}\n')
            print("OK      BISECT: bit10")
        else:
            print("MISS    BISECT: bit10")
    if "BISECT: bit11" not in a5:
        m = re.search(r"static struct msm_gem_address_space \*\n"
                      r"(a5xx_create_private_address_space\(struct msm_gpu \*gpu\))\n\{\n",
                      a5)
        if m:
            a5 = (a5[:m.end()]
                  + '\tif (adreno_debug_stage & (1 << 11)) {\n'
                    '\t\tpr_err("BISECT: bit11 disable per-process aspace\\n");\n'
                    '\t\treturn ERR_PTR(-ENODEV);\n'
                    '\t}\n\n'
                  + a5[m.end():])
            print("OK      BISECT: bit11")
        else:
            print("MISS    BISECT: bit11")
    write(A5, a5)

    checks = {
        "param": "module_param_named(debug_stage" in read(DEV),
        "bits0-4": all(("BISECT: bit%d" % i) in read(DEV) for i in range(5)),
        "bits5-9": all(("BISECT: bit%d" % i) in read(A5) for i in range(5, 10)),
        "bit10": "BISECT: bit10" in read(A5),
        "bit11": "BISECT: bit11" in read(A5),
        "extern": "extern int adreno_debug_stage;" in read(HDR),
    }
    for name, ok in checks.items():
        print("%-10s %s" % (name, "OK" if ok else "MISS"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
