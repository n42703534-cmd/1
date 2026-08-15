"""Generate all Pathfinder comparison figures: Mode 1 + Mode 4."""
import csv, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

OUT = r'C:\Users\帅美婷sweet baby\Desktop\network'

def load(path):
    ets, cts = [], []
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            et, ct = float(r['exit time(s)']), float(r['congestion time total(s)'])
            if et > 0:
                ets.append(et); cts.append(ct)
    return np.array(ets), np.array(cts)

# ── Data sources ──────────────────────────────────────────
datasets = {
    'mode1': {
        'IA': (rf'{OUT}\pathfinder\original\龙阳路im 路径 _occupants.csv', '#E74C3C', '--'),
        'QA': (rf'{OUT}\pathfinder\original\龙阳路any _occupants.csv', '#2980B9', '-'),
    },
    'mode4': {
        'IA': (rf'{OUT}\..\高负荷\龙阳路improved高负荷 _occupants.csv', '#E74C3C', '--'),
        'QA': (rf'{OUT}\..\高负荷\龙阳路AA高负荷 _occupants.csv', '#2980B9', '-'),
    },
}

for mode_tag, config in datasets.items():
    title_tag = 'Mode 1 (2,187 pax)' if mode_tag == 'mode1' else 'Mode 4 (17,905 pax)'
    xlim = 450 if mode_tag == 'mode1' else 1700

    data = {}
    for algo, (path, color, ls) in config.items():
        data[algo] = load(path)
        print(f'  {mode_tag} {algo}: {len(data[algo][0])} occupants')

    et_ia, ct_ia = data['IA']
    et_qa, ct_qa = data['QA']

    # ── Figure A: Cumulative Evacuation Curve ──────────────
    fig, ax = plt.subplots(figsize=(8, 5))
    for et, label, color, ls in [
        (et_ia, 'Improved A*', '#E74C3C', '--'),
        (et_qa, 'Adaptive Queue-Aware A*', '#2980B9', '-'),
    ]:
        s = np.sort(et)
        ax.plot(s, np.arange(1,len(s)+1)/len(s)*100, color=color, linestyle=ls, linewidth=2, label=label)
    ax.set_xlabel('Evacuation Time (s)', fontsize=12)
    ax.set_ylabel('Cumulative Evacuated (%)', fontsize=12)
    ax.set_title(f'{title_tag} — Cumulative Evacuation Curve', fontsize=13)
    ax.legend(fontsize=11); ax.set_xlim(0, xlim); ax.set_ylim(0,105); ax.grid(True, alpha=0.3)
    fig.savefig(os.path.join(OUT, f'fig_evac_curve_{mode_tag}.png'), dpi=200); plt.close()

    # ── Figure B: Overlaid Congestion Histogram ────────────
    fig, ax = plt.subplots(figsize=(8, 5))
    bmax = max(ct_ia.max(), ct_qa.max())
    bins = np.linspace(0, bmax, 50)
    ax.hist(ct_ia, bins=bins, color='#E74C3C', alpha=0.4, edgecolor='white', label='Improved A*')
    ax.hist(ct_qa, bins=bins, color='#2980B9', alpha=0.4, edgecolor='white', label='Adaptive QA A*')
    ax.axvline(x=60, color='red', linestyle=':', linewidth=1.5, label='Severe (>60s)')
    ax.set_xlabel('Congestion Time (s)', fontsize=12)
    ax.set_ylabel('Number of Occupants', fontsize=12)
    ax.set_title(f'{title_tag} — Congestion Time Distribution', fontsize=13)
    ax.legend(fontsize=11); ax.grid(True, alpha=0.2)
    fig.savefig(os.path.join(OUT, f'fig_congestion_{mode_tag}.png'), dpi=200); plt.close()

    # ── Figure C: Side-by-side congestion histogram ────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    def plot_hist(ax, ct, label, color):
        ax.hist(ct, bins=bins, color=color, alpha=0.7, edgecolor='white')
        ax.axvline(x=np.mean(ct), color='black', linestyle='--', linewidth=1.5, label=f'Mean={np.mean(ct):.1f}s')
        sev = np.mean(ct>60)*100
        ax.axvline(x=60, color='red', linestyle=':', linewidth=1, label=f'Severe(>60s)={sev:.1f}%')
        ax.set_xlabel('Congestion Time (s)', fontsize=11)
        ax.set_ylabel('Occupants', fontsize=11)
        ax.set_title(f'{label}\nMean={np.mean(ct):.1f}s Med={np.median(ct):.1f}s P90={np.percentile(ct,90):.1f}s Severe={sev:.1f}%', fontsize=10)
        ax.legend(fontsize=9); ax.grid(True, alpha=0.2)
    plot_hist(ax1, ct_ia, 'Improved A*', '#E74C3C')
    plot_hist(ax2, ct_qa, 'Adaptive QA A*', '#2980B9')
    fig.suptitle(f'{title_tag} — Congestion Time Distribution', fontsize=13, y=1.02)
    plt.tight_layout()
    fig.savefig(os.path.join(OUT, f'fig_congestion_side_{mode_tag}.png'), dpi=200); plt.close()

    # ── Stats ──────────────────────────────────────────────
    print(f'\n=== {title_tag} Stats ===')
    for label, et, ct in [('Improved A*', et_ia, ct_ia), ('Adaptive QA A*', et_qa, ct_qa)]:
        print(f'  {label}: Evac: mean={np.mean(et):.1f}s med={np.median(et):.1f}s '
              f'P50={np.percentile(et,50):.1f}s P90={np.percentile(et,90):.1f}s P100={np.max(et):.1f}s  |  '
              f'Cong: mean={np.mean(ct):.1f}s med={np.median(ct):.1f}s '
              f'Severe(>60s)={np.mean(ct>60)*100:.1f}% Mild(<30s)={np.mean(ct<30)*100:.1f}%')

print('\nDone. Generated:')
for f in sorted(os.listdir(OUT)):
    if f.startswith('fig_') and f.endswith('.png'):
        print(f'  {OUT}\\{f}')
