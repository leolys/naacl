import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle, Polygon

plt.rcParams['font.size'] = 8

XL, XR, W = 1.1, 5.3, 0.30

left_nodes = [
    ('Batch C\n18 ordinary-correct', 21.5, 39.5, '#4a5666'),
    ('27B rerun\n20 ordinary-correct', 0.0, 20.0, '#4a5666'),
]
right_nodes = [
    ('Correct submission 15', 26.0, 41.0, '#3a4858'),
    ('Recorded abstention 12', 13.0, 25.0, '#76818d'),
    ('Engineering failure 10', 2.0, 12.0, '#99a28f'),
    ('Call limit 1', 0.0, 1.0, '#babfc5'),
]
flows = [
    (0, 39.5, 31.5, 0, 41.0, 33.0, 8),
    (0, 31.5, 24.5, 1, 25.0, 18.0, 7),
    (0, 24.5, 21.5, 2, 12.0, 9.0, 3),
    (1, 20.0, 13.0, 0, 33.0, 26.0, 7),
    (1, 13.0, 8.0, 1, 18.0, 13.0, 5),
    (1, 8.0, 1.0, 2, 9.0, 2.0, 7),
    (1, 1.0, 0.0, 3, 1.0, 0.0, 1),
]

fig, ax = plt.subplots(figsize=(3.9, 2.5))

for name, y0, y1, c in left_nodes:
    ax.add_patch(Rectangle((XL - W / 2, y0), W, y1 - y0, color=c))
    ax.text(XL - W / 2 - 0.12, (y0 + y1) / 2, name, fontsize=7.2,
            ha='right', va='center', linespacing=1.25)
for name, y0, y1, c in right_nodes:
    ax.add_patch(Rectangle((XR - W / 2, y0), W, y1 - y0, color=c))
    ax.text(XR + W / 2 + 0.12, (y0 + y1) / 2, name, fontsize=7.2,
            ha='left', va='center', linespacing=1.25)

for si, s0, s1, di, d0, d1, n in flows:
    color = right_nodes[di][3]
    ts = np.linspace(0, 1, 60)
    xa, xb = XL + W / 2, XR - W / 2
    xs = xa + (xb - xa) * ts
    top = (1 - ts) ** 3 * s1 + 3 * (1 - ts) ** 2 * ts * (s1 + d1) / 2 \
        + 3 * (1 - ts) * ts ** 2 * (s1 + d1) / 2 + ts ** 3 * d1
    bot = (1 - ts) ** 3 * s0 + 3 * (1 - ts) ** 2 * ts * (s0 + d0) / 2 \
        + 3 * (1 - ts) * ts ** 2 * (s0 + d0) / 2 + ts ** 3 * d0
    ax.add_patch(Polygon(list(zip(xs, top)) + list(zip(xs[::-1], bot[::-1])),
                         closed=True, color=color, linewidth=0))
    ax.text(0.5 * (xa + xb), 0.5 * (s1 + d1 + s0 + d0) / 2 + 0.05,
            str(n), fontsize=6.4, ha='center', va='center')

ax.text(3.2, -3.3, 'Defense-arm wrong submissions: 0 of 96 units',
        fontsize=7.4, ha='center', va='center')

ax.set_xlim(-0.6, 7.0)
ax.set_ylim(-4.3, 43.0)
ax.set_xticks([])
ax.set_yticks([])
for sp in ax.spines.values():
    sp.set_visible(False)

fig.savefig('fig_conversions.pdf', bbox_inches='tight')
print('saved')
