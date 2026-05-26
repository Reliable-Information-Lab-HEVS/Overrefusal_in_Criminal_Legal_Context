import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

# Refusal counts: rows = topics, cols = (None, Lawyer, Supreme, Jailbreak)
data = {
    "Llama 3.1 8B": [[17,20,36,46],[1,11,15,73],[12,20,19,31],[15,24,31,44],[28,37,31,81]],
    "Gemma 4 E4B":  [[14,22,45,19],[14,37,43,8],[19,27,35,10],[20,21,38,16],[38,43,56,40]],
    "Apertus 8B":   [[10,22,25,15],[4,34,29,19],[4,16,12,6],[15,31,23,22],[23,40,33,33]],
    "Qwen 3 8B":    [[6,6,3,5],[1,12,10,3],[4,4,4,4],[2,5,2,7],[8,8,7,11]],
}
topics  = ["Violence","Sexual","Harmful","Unethical","Illegal"]
prefixes = ["None","Lawyer","Supreme","Jailbreak"]
models = list(data.keys())

fig, axes = plt.subplots(1, 4, figsize=(13, 3.2), sharey=True)
vmax = 60   # color saturates above this
norm = Normalize(vmin=0, vmax=vmax)
cmap = "Reds"

for ax, m in zip(axes, models):
    arr = np.array(data[m])
    im = ax.imshow(arr, cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(len(prefixes)))
    ax.set_xticklabels(prefixes, rotation=30, ha="right", fontsize=13)
    ax.set_yticks(range(len(topics)))
    ax.set_yticklabels(topics, fontsize=12)
    ax.set_title(m, fontsize=14)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            v = arr[i,j]
            color = "white" if v > vmax * 0.6 else "black"
            ax.text(j, i, str(v), ha="center", va="center",
                    color=color, fontsize=13)

cbar = fig.colorbar(im, ax=axes, shrink=0.85, pad=0.02)
cbar.set_label("Refusals (out of 200)", fontsize=14)
cbar.ax.tick_params(labelsize=13)

# Override top tick label to indicate saturation
ticks = list(cbar.get_ticks())
cbar.set_ticks(ticks)
labels = [f"$\\geq${int(vmax)}" if t >= vmax else f"{int(t)}" for t in ticks]
cbar.set_ticklabels(labels)

#plt.suptitle("Refusal counts on English OR-Bench prompts", fontsize=10, y=1.02)
plt.savefig("heatmap_english.pdf", bbox_inches="tight")
plt.savefig("heatmap_english.png", bbox_inches="tight", dpi=200)
print("Saved heatmap_english.pdf and .png")