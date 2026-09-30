import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.path import Path

plt.rcParams['font.size'] = 6.2

fig, ax = plt.subplots(figsize=(3.5, 1.82))
ax.set_xlim(0, 13.1)
ax.set_ylim(0, 6.8)

boxes = [
    (0.30, 3.30, 2.80, 2.40, '#5b6472',
     'Agent\njudgment:\n$O\\wedge B$\n$\\Rightarrow C_q(a)$'),
    (3.38, 3.30, 3.00, 2.40, '#66707e',
     'Competing\nchains ($K$):\nfrozen pool,\nsame chart'),
    (6.66, 3.30, 3.20, 3.00, '#717b88',
     'Applicability\nverifier ($L$):\nchecks O, rule,\nderivation\nvs. in-chart\nevidence'),
    (10.14, 3.30, 2.80, 2.40, '#7c8590',
     'Terminal\nstatus: Keep,\nRevise,\nUnresolved'),
    (2.40, 0.50, 4.80, 2.60, '#5b6472',
     'Persistent rule\nstate $M_t^B$:\nrevision, evidence,\nscope; written only\nby verification'),
]
for x, y, w, h, c, inner in boxes:
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle='round,pad=0.02,rounding_size=0.16',
                                mutation_scale=1, fc=c, linewidth=1.4))
    ax.text(x + w / 2, y + h / 2, inner, fontsize=6.2,
            ha='center', va='center', linespacing=1.12)

def arrow(p0, p1):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle='-|>',
                                 mutation_scale=6.5, linewidth=1.0,
                                 color='#8b93a0', shrinkA=0, shrinkB=0))

for a, b in [(3.10, 3.38), (6.38, 6.66), (9.86, 10.14)]:
    arrow((a, 4.40), (b, 4.40))
arrow((11.54, 3.30), (7.20, 1.90))
loop = Path([(2.40, 1.90), (1.50, 1.90), (1.50, 3.30)],
            [Path.MOVETO, Path.LINETO, Path.LINETO])
ax.add_patch(FancyArrowPatch(path=loop, arrowstyle='-|>',
                             mutation_scale=6.5, linewidth=1.0,
                             color='#8b93a0'))
ax.text(9.70, 2.15, 'validated revisions', fontsize=6.2,
        ha='center', va='center')
ax.text(1.45, 0.52, 'later steps: read\nscope-matched rules\n$\\rightarrow$ re-derive',
        fontsize=6.2, ha='center', va='center', linespacing=1.2)

ax.set_xticks([])
ax.set_yticks([])
for sp in ax.spines.values():
    sp.set_visible(False)

fig.savefig('fig_overview.pdf', bbox_inches='tight')
print('saved')
