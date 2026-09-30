import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['font.size'] = 9
x = np.arange(1, 7)
y = np.array([12.0, 11.2, 12.8, 13.1, 14.6, 15.3])

fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.4))

axes[0].plot(x, y, marker='o', linewidth=1.2)
axes[0].set_ylim(10, 20)
axes[0].set_xlim(0.6, 6.4)
axes[0].set_xticks(range(1, 7))
axes[0].set_yticks([10, 15, 20])
axes[0].set_title('(a) Faithful axis order: values increase upward.\n'
                  'Rule $B_0$ ("higher position, larger value") holds;\n'
                  '$O\\wedge B_0\\rightarrow C_q$: the curve grows.',
                  fontsize=9, loc='left')
axes[0].set_ylabel('Printed ticks: 10, 15, 20')

axes[1].plot(x, y, marker='o', linewidth=1.2)
axes[1].set_ylim(20, 10)
axes[1].set_xlim(0.6, 6.4)
axes[1].set_xticks(range(1, 7))
axes[1].set_yticks([20, 15, 10])
axes[1].set_title('(b) Same pixels, printed tick order reversed: values increase downward.\n'
                  '$B_0$ refuted by scale order; revised $B_1$ ("higher position, smaller value");\n'
                  'the same upward curve now reads as decline.',
                  fontsize=9, loc='left')

fig.subplots_adjust(wspace=0.3)
fig.savefig('fig_misleading_pair.pdf', bbox_inches='tight')
print('saved')
