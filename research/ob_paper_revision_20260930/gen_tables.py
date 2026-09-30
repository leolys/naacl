"""Emit LaTeX rows for the revision-experiment tables from scores.json."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
scores = json.loads((HERE / 'results' / 'scores.json').read_text())

seeds = scores['seeds']
n = 140


def pct(x):
    return f"{100.0 * x / n:.1f}\\%"


lines = []
lines.append('% seed replication table')
lines.append('\\begin{table}[t]')
lines.append('\\centering')
lines.append('\\begin{tabular}{lccc}')
lines.append('\\toprule')
lines.append('Configuration & Requests & Target (mean$\\pm$sd) & $p$ vs.\\ Direct \\\\')
lines.append('\\midrule')
p_mean = scores['plain'].get('mean_target')
p_sd = scores['plain'].get('stdev_target')
v_mean = scores['v5'].get('mean_target')
v_sd = scores['v5'].get('stdev_target')
lines.append(f"Direct (1 request) & 140 & {p_mean:.1f}$\\pm${p_sd:.1f} & --- \\\\")
pooled_a = sum(scores['paired'][v]['target_to_wrong'] for v in seeds)
pooled_b = sum(scores['paired'][v]['wrong_to_target'] for v in seeds)
nd = pooled_a + pooled_b
p_val = 1.0
if nd:
    k = min(pooled_a, pooled_b)
    p_val = min(1.0, 2 * sum(__import__('math').comb(nd, i) for i in range(0, k + 1)) * 0.5 ** nd)
lines.append(f"Self-consistency (3 samples) & 420 & "
             f"{scores['sc3'].get('target', 0)} & --- \\\\")
lines.append(f"\\ours{{}} V5 (3 requests) & 420 & {v_mean:.1f}$\\pm${v_sd:.1f} & {p_val:.4f} \\\\")
lines.append(f"Tabular answering (2 requests) & 280 & "
             f"{scores['tab'].get('target', 0)} & --- \\\\")
lines.append('\\bottomrule')
lines.append('\\end{tabular}')
lines.append('\\caption{...}')
lines.append('\\label{tab:seeds-baselines}')
lines.append('\\end{table}')
print('\n'.join(lines))
print()
print('% clean-chart control: Direct on clean charts =', scores['clean'].get('target', 0),
      '/', n, f"({pct(scores['clean'].get('target', 0))})")
for v in seeds:
    pr = scores['paired'][v]
    print(f"% seed {v}: Direct {scores['plain'][v]['target']}, V5 {scores['v5'][v]['target']}, "
          f"net {pr['net']}, p {pr['mcnemar_p']:.4f}, CI {pr['diff_ci95']}")
