import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['font.size'] = 9
x = np.arange(1, 13)
y = np.array([12.0, 11.3, 12.6, 12.2, 13.1, 13.8,
              13.4, 14.2, 14.0, 14.8, 14.5, 15.4])

fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.4))

for i, ax in enumerate(axes):
    ax.plot(x, y, color='#5e83b3', linewidth=1.3,
            marker='o', markersize=3.2, mew=1.0)
    ax.set_xlim(0.6, 12.4)
    ax.set_xticks(range(1, 13, 2))
    ax.set_xlabel('Week', fontsize=8)
    ax.set_ylabel('Units sold (k)', fontsize=8)
    ax.tick_params(axis='both', labelsize=7)
    ax.grid(axis='y', color='#dfe3e6', linewidth=0.6)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

axes[0].set_ylim(10, 20)
axes[0].set_yticks([10, 15, 20])
axes[0].set_title('(a) Faithful axis order:\n'
                  '$B_0$ holds; the curve grows.',
                  fontsize=9, loc='left')

axes[1].set_ylim(20, 10)
axes[1].set_yticks([20, 15, 10])
axes[1].set_title('(b) Tick order reversed:\n'
                  '$B_0$ refuted; revised $B_1$: decline.',
                  fontsize=9, loc='left')

fig.subplots_adjust(wspace=0.3)
fig.savefig('fig_misleading_pair.pdf', bbox_inches='tight')
print('saved')
