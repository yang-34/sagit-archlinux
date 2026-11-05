#!/usr/bin/env python3
"""Insert pr_err checkpoints at the top of GPU init functions (build-42)."""
import re
import sys

TARGETS = [
    ("drivers/gpu/drm/msm/adreno/adreno_device.c", r"static int adreno_bind\s*\(", "adreno_bind"),
    ("drivers/gpu/drm/msm/adreno/adreno_device.c", r"static int adreno_probe\s*\(", "adreno_probe"),
    ("drivers/gpu/drm/msm/adreno/adreno_gpu.c", r"int adreno_gpu_init\s*\(", "adreno_gpu_init"),
    ("drivers/gpu/drm/msm/adreno/adreno_gpu.c", r"int adreno_load_gpu\s*\(", "adreno_load_gpu"),
    ("drivers/gpu/drm/msm/adreno/adreno_gpu.c", r"static int adreno_start\s*\(", "adreno_start"),
    ("drivers/gpu/drm/msm/msm_gpu.c", r"int msm_gpu_init\s*\(", "msm_gpu_init"),
    ("drivers/gpu/drm/msm/msm_gpu.c", r"int msm_gpu_hw_init\s*\(", "msm_gpu_hw_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_hw_init\s*\(", "a5xx_hw_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_me_init\s*\(", "a5xx_me_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_pfp_init\s*\(", "a5xx_pfp_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_cp_init\s*\(", "a5xx_cp_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"int a5xx_power_init\s*\(", "a5xx_power_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_zap_shader_resume\s*\(", "a5xx_zap_resume"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_gpmu_init\s*\(", "a5xx_gpmu_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"void a5xx_gpmu_ucode_init\s*\(", "a5xx_gpmu_ucode"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gpu.c", r"static int a5xx_reset\s*\(", "a5xx_reset"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gmu.c", r"int a5xx_gmu_init\s*\(", "a5xx_gmu_init"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gmu.c", r"static int a5xx_gmu_start\s*\(", "a5xx_gmu_start"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gmu.c", r"int a5xx_gmu_reset\s*\(", "a5xx_gmu_reset"),
    ("drivers/gpu/drm/msm/adreno/a5xx_gmu.c", r"a5xx_gmu_power_enable\s*\(", "a5xx_gmu_power_enable"),
]

MARK = "CKPT: "


def insert_after_brace(path, sig, label):
    try:
        src = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return "MISS"
    m = re.search(sig, src)
    if not m:
        return "MISS"
    brace = src.find("{", m.end())
    if brace < 0:
        return "MISS"
    eol = src.find("\n", brace)
    if eol < 0:
        return "MISS"
    stmt = '\n\tpr_err("CKPT: %s\\n");' % label
    if MARK + label in src[eol:eol + 200]:
        return "SKIP"
    src = src[:eol + 1] + stmt.lstrip("\n") + "\n" + src[eol + 1:]
    open(path, "w", encoding="utf-8").write(src)
    return "OK"


def main():
    for path, sig, label in TARGETS:
        print("%-8s %-22s %s" % (insert_after_brace(path, sig, label), label, path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
