#!/usr/bin/env python3
"""build-43: CKPT checkpoints (repeat ~200ms) + adreno_bind early -ENODEV."""
import re
import sys

TARGETS = [
    ("drivers/gpu/drm/msm/adreno/adreno_device.c", r"static int adreno_bind\s*\(", "adreno_bind"),
    ("drivers/gpu/drm/msm/adreno/adreno_device.c", r"static int adreno_probe\s*\(", "adreno_probe"),
    ("drivers/gpu/drm/msm/adreno/adreno_gpu.c", r"int adreno_gpu_init\s*\(", "adreno_gpu_init"),
    ("drivers/gpu/drm/msm/msm_gpu.c", r"int msm_gpu_init\s*\(", "msm_gpu_init"),
    ("drivers/gpu/drm/msm/msm_gpu.c", r"int msm_gpu_hw_init\s*\(", "msm_gpu_hw_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_hw_init\s*\(", "a5xx_hw_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static.*a5xx_me_init\s*\(", "a5xx_me_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_zap_shader_resume\s*\(", "a5xx_zap_resume"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static.*a5xx_reset\s*\(", "a5xx_reset"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static.*a5xx_cp_init\s*\(", "a5xx_cp_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static.*a5xx_pfp_init\s*\(", "a5xx_pfp_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static.*a5xx_gpmu_init\s*\(", "a5xx_gpmu_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gmu.c", r"int a5xx_gmu_init\s*\(", "a5xx_gmu_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"int a5xx_power_init\s*\(", "a5xx_power_init"),
]

STOP_AFTER = {"adreno_bind": "\treturn -ENODEV;\n"}


def add_include(src):
    if "linux/delay.h" in src:
        return src
    m = re.search(r"#include <linux/[^\n]*\n", src)
    if not m:
        return src
    return src[:m.end()] + "#include <linux/delay.h>\n" + src[m.end():]


def ckpt_block(label):
    return ('\t{ int __ck; for (__ck = 0; __ck < 40; __ck++) {'
            ' pr_err("CKPT: %s\\n"); mdelay(5); } }\n' % label)


def patch(path, sig, label):
    try:
        src = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return "MISS"
    if "CKPT: " + label in src:
        return "SKIP"
    m = re.search(sig, src)
    if not m:
        return "MISS"
    brace = src.find("{", m.end())
    if brace < 0:
        return "MISS"
    eol = src.find("\n", brace)
    if eol < 0:
        return "MISS"
    block = ckpt_block(label) + STOP_AFTER.get(label, "")
    src = src[:eol + 1] + block + src[eol + 1:]
    src = add_include(src)
    open(path, "w", encoding="utf-8").write(src)
    return "OK"


def main():
    for path, sig, label in TARGETS:
        print("%-6s %-20s %s" % (patch(path, sig, label), label, path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
