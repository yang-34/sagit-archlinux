import os
import sys

root = sys.argv[1] if len(sys.argv) > 1 else "kernel"
path = os.path.join(root, "drivers/clk/qcom/gcc-msm8998.c")
with open(path) as f:
    src = f.read()

for name in ("gcc_bimc_gfx_clk", "gcc_gpu_bimc_gfx_clk", "gcc_gpu_cfg_ahb_clk"):
    idx = src.index("static struct clk_branch %s = {" % name)
    end = src.index("};", idx)
    seg = src[idx:end].replace(".halt_check = BRANCH_HALT,",
                              ".halt_check = BRANCH_HALT_SKIP,")
    src = src[:idx] + seg + src[end:]

with open(path, "w") as f:
    f.write(src)
print("patched", path)
