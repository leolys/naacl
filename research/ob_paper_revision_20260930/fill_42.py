"""Render the revision-experiment numbers from scores.json into LaTeX for 4.2."""
import json, math, sys
from pathlib import Path

here = Path(__file__).resolve().parent
s = json.loads((here / 'results' / 'scores.json').read_text())
N = 140
p1 = s['plain'][s['seeds'][0]] if s['seeds'] else None
p2 = s['plain'][s['seeds'][1]] if len(s['seeds']) > 1 else None
p3 = s['plain'][s['seeds'][2]] if len(s['seeds']) > 2 else None
v1 = s['v5'][s['seeds'][0]] if s['seeds'] and s['v5'].get(s['seeds'][0]) else None
v2 = s['v5'][s['seeds'][1]] if len(s['seeds']) > 1 and s['v5'].get(s['seeds'][1]) else None
v3 = s['v5'][s['seeds'][2]] if len(s['seeds']) > 2 and s['v5'].get(s['seeds'][2]) else None

def pct(x): return f"{100*x/N:.1f}"

out = []
out.append("%% seeds observed: " + ",".join(s['seeds']))
for name, d in (('plain', p1), ('plain', p2), ('plain', p3), ('v5', v1), ('v5', v2), ('v5', v3)):
    if d: out.append(f"%% {name}: target={d['target']} rate={pct(d['target']/N)}")
for v, pr in s['paired'].items():
    out.append(f"%% seed {v}: net {pr['net']} (a={pr['target_to_wrong']} b={pr['wrong_to_target']}) p={pr['mcnemar_p']:.4g} ci=[{pr['diff_ci95'][0]:+.3f},{pr['diff_ci95'][1]:+.3f}] kinds={pr['kinds']}")
out.append(f"%% sc3: {s['sc3']}")
for k, pr in s['paired_extra'].items():
    out.append(f"%% extra {k}: net {pr['net']} (a={pr['target_to_wrong']} b={pr['wrong_to_target']}) p={pr['mcnemar_p']:.4g} ci=[{pr['diff_ci95'][0]:+.3f},{pr['diff_ci95'][1]:+.3f}] kinds={pr['kinds']}")
out.append(f"%% tab: {s['tab']}")
out.append(f"%% clean: {s['clean']}")
mean_p = s['plain'].get('mean_target'); sd_p = s['plain'].get('stdev_target')
mean_v = s['v5'].get('mean_target'); sd_v = s['v5'].get('stdev_target')
if mean_p is not None: out.append(f"%% plain mean {mean_p:.2f} sd {sd_p:.2f} | v5 mean {mean_v:.2f} sd {sd_v:.2f}")
print("\n".join(out))
