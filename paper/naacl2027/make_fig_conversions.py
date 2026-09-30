import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.size'] = 8

fig, ax = plt.subplots(figsize=(3.4, 2.0))

COLS = {'Abst.': '#8f959b', 'Eng. fail': '#b7bcc0', 'Call lim.': '#d3d6d8'}
rows = [('Batch C (10)', 1, [('Abst.', 7), ('Eng. fail', 3)]),
        ('Rerun (13)', 0, [('Abst.', 5), ('Eng. fail', 7), ('Call lim.', 1)])]
H = 0.5

for name, y, segs in rows:
    left = 0.0
    for s, v in segs:
        c = COLS[s]
        ax.barh(y, v, left=left, height=H, color=c)
        if v >= 3:
            ax.text(left + v / 2, y, f'{s} {v}', fontsize=7,
                    ha='center', va='center')
        else:
            ax.text(left + v / 2, y - H / 2 - 0.14, f'{s} {v}',
                    fontsize=6, ha='center', va='center')
        left += v

ax.set_xlim(0, 13.6)
ax.set_ylim(-0.9, 1.7)
ax.set_yticks([0, 1])
ax.set_yticklabels(['Rerun (13)', 'Batch C (10)'], fontsize=7)
ax.set_xticks([])
for sp in ax.spines.values():
    sp.set_visible(False)
ax.text(6.8, -0.62, '23 conversions: 0 corrections, 0 wrong submissions',
        fontsize=7, ha='center', va='center')

fig.savefig('fig_conversions.pdf', bbox_inches='tight')
print('saved')
