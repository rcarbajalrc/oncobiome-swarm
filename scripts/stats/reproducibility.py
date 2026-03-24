"""
Sprint 3 — Análisis estadístico de reproducibilidad.

Ejecutar cuando n=3 por experimento:
    python scripts/stats/reproducibility.py

Produce:
  - Tabla media ± SD por condición
  - Test de Wilcoxon entre pares de condiciones
  - Cohen's d entre LLM vs rule engine
  - Figura de variabilidad entre runs (violin plot)
  - CSV de exportación para tabla de resultados del paper
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).parent.parent.parent
RUNS    = PROJECT / "runs"
sys.path.insert(0, str(PROJECT))


def load_experiment_data(experiment: str) -> list[dict]:
    """Carga metadata de todas las runs de un experimento."""
    exp_dir = RUNS / experiment
    if not exp_dir.exists():
        return []
    data = []
    for run_dir in sorted(exp_dir.iterdir()):
        mf = run_dir / "metadata.json"
        if mf.exists():
            data.append(json.loads(mf.read_text()))
    return data


def descriptive_stats(values: list[float]) -> dict:
    """Media, SD, CV, min, max."""
    import statistics as st
    if not values:
        return {}
    n = len(values)
    mean = st.mean(values)
    sd   = st.stdev(values) if n > 1 else 0.0
    return {
        "n":    n,
        "mean": round(mean, 2),
        "sd":   round(sd, 2),
        "cv":   round(sd/mean*100, 1) if mean else 0,
        "min":  min(values),
        "max":  max(values),
    }


def wilcoxon_test(x: list[float], y: list[float]) -> dict:
    """
    Wilcoxon rank-sum (Mann-Whitney U) entre dos grupos independientes.
    Para n pequeño (n=3) calcula U exacto.
    """
    if len(x) < 2 or len(y) < 2:
        return {"note": "n insuficiente para test estadístico"}

    try:
        from scipy.stats import mannwhitneyu
        stat, p = mannwhitneyu(x, y, alternative='two-sided')
        return {"U": round(float(stat), 2), "p": round(float(p), 4),
                "significant": p < 0.05}
    except ImportError:
        # Implementación manual para n=3 sin scipy
        nx, ny = len(x), len(y)
        u = sum(1 for xi in x for yi in y if xi < yi) + \
            0.5 * sum(1 for xi in x for yi in y if xi == yi)
        return {"U": round(u, 2), "p": "requiere scipy",
                "note": "pip install scipy --break-system-packages"}


def cohens_d(x: list[float], y: list[float]) -> float:
    """Cohen's d = (mean_x - mean_y) / pooled_SD."""
    if len(x) < 2 or len(y) < 2:
        return float('nan')
    import statistics as st
    mx, my = st.mean(x), st.mean(y)
    sx, sy = st.stdev(x), st.stdev(y)
    nx, ny = len(x), len(y)
    pooled = ((nx-1)*sx**2 + (ny-1)*sy**2) / (nx+ny-2)
    pooled_sd = pooled ** 0.5
    if pooled_sd == 0:
        return float('nan')
    return round((mx - my) / pooled_sd, 3)


def interpret_d(d: float) -> str:
    ad = abs(d)
    if ad < 0.2:  return "trivial"
    if ad < 0.5:  return "small"
    if ad < 0.8:  return "medium"
    return "large"


def run_analysis() -> None:
    experiments = ["cap80_baseline", "immune_boost", "combination_therapy"]
    DPC = 2.167  # días por ciclo

    print("=" * 65)
    print("OncoBiome Swarm — Sprint 3: Análisis de Reproducibilidad")
    print("=" * 65)

    all_collapses = {}
    all_tumors    = {}

    for exp in experiments:
        data = load_experiment_data(exp)
        if not data:
            print(f"\n⚠  Sin datos para {exp}")
            continue

        collapses = [d["immune_collapse_cycle"] for d in data
                     if d.get("immune_collapse_cycle") is not None]
        tumors    = [d["tumor_final"] for d in data
                     if d.get("tumor_final") is not None]
        costs     = [d["cost_usd"] for d in data
                     if d.get("cost_usd") is not None]

        all_collapses[exp] = collapses
        all_tumors[exp]    = tumors

        cs = descriptive_stats(collapses)
        ts = descriptive_stats(tumors)

        print(f"\n── {exp} (n={cs.get('n',0)}) ──────────────────────────────")
        if cs:
            d_mean = round(cs['mean'] * DPC, 1)
            d_sd   = round(cs['sd'] * DPC, 1)
            print(f"  Colapso inmune:  {cs['mean']} ± {cs['sd']} ciclos"
                  f"  ({d_mean} ± {d_sd} días)")
            print(f"  CV:              {cs['cv']}%  "
                  + ("✓ aceptable" if cs['cv'] < 20 else "⚠ alta variabilidad"))
        if ts:
            print(f"  Tumor final:     {ts['mean']} ± {ts['sd']} células")
        if costs:
            print(f"  Coste acumulado: ${sum(costs):.2f}  "
                  f"(${sum(costs)/len(costs):.2f}/run)")

        # Runs individuales
        print("  Runs individuales:")
        for d in data:
            c = d.get('immune_collapse_cycle', '?')
            t = d.get('tumor_final', '?')
            cd = round(c * DPC, 1) if isinstance(c, (int, float)) else '?'
            idx = d.get('run_index', '?')
            print(f"    Run {idx}: collapse=c{c}({cd}d)  tumor={t}")

    # ── Comparaciones entre condiciones LLM ──────────────────────────────
    if len(all_collapses) >= 2:
        print("\n── Comparaciones estadísticas (colapso inmune) ──────────────")
        pairs = [
            ("cap80_baseline",     "immune_boost",       "Baseline vs Immune Boost"),
            ("immune_boost",       "combination_therapy","Immune Boost vs Combination"),
            ("cap80_baseline",     "combination_therapy","Baseline vs Combination"),
        ]
        for e1, e2, label in pairs:
            x = all_collapses.get(e1, [])
            y = all_collapses.get(e2, [])
            if len(x) >= 2 and len(y) >= 2:
                mwu = wilcoxon_test(x, y)
                d   = cohens_d(x, y)
                print(f"  {label}:")
                print(f"    Mann-Whitney U={mwu.get('U')}  p={mwu.get('p')}  "
                      f"Cohen's d={d} ({interpret_d(d)})")

    # ── Export CSV ────────────────────────────────────────────────────────
    out = PROJECT / "results" / "sprint3_stats.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w") as f:
        f.write("experiment,n,collapse_mean,collapse_sd,collapse_days_mean,"
                "collapse_days_sd,cv_pct,tumor_mean,tumor_sd\n")
        for exp in experiments:
            data = load_experiment_data(exp)
            collapses = [d["immune_collapse_cycle"] for d in data
                         if d.get("immune_collapse_cycle") is not None]
            tumors    = [d["tumor_final"] for d in data
                         if d.get("tumor_final") is not None]
            cs = descriptive_stats(collapses)
            ts = descriptive_stats(tumors)
            if cs:
                f.write(f"{exp},{cs['n']},{cs['mean']},{cs['sd']},"
                        f"{round(cs['mean']*DPC,1)},{round(cs['sd']*DPC,1)},"
                        f"{cs['cv']},{ts.get('mean','')},{ts.get('sd','')}\n")
    print(f"\n  ✓ CSV exportado: {out.relative_to(PROJECT)}")

    # ── Violin plot si matplotlib disponible ─────────────────────────────
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5), facecolor='white')
        fig.suptitle('OncoBiome Swarm — Sprint 3: Reproducibilidad (n=3)',
                     fontsize=11, fontweight='bold')

        labels  = ['Baseline', 'Immune\nBoost', 'Combination']
        colors  = ['#C62828', '#E65100', '#7B1FA2']
        c_data  = [all_collapses.get(e, []) for e in experiments]
        t_data  = [all_tumors.get(e, []) for e in experiments]

        for ax, data_list, ylabel, title in [
            (ax1, c_data, 'Immune Collapse (cycles)', 'Immune Collapse Timing'),
            (ax2, t_data, 'Tumor cells (c52)',        'Tumor Burden at c52'),
        ]:
            ax.set_facecolor('#F7F9FC')
            ax.set_title(title, fontsize=10, fontweight='bold')
            ax.set_ylabel(ylabel, fontsize=9)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(True, color='#E0E0E0', linewidth=0.7)

            for i, (d, label, color) in enumerate(zip(data_list, labels, colors)):
                if not d: continue
                x_jitter = [i + 0.05*(j - len(d)/2) for j in range(len(d))]
                ax.scatter(x_jitter, d, color=color, s=80, zorder=5,
                           edgecolors='white', linewidth=1.2)
                mean_v = sum(d)/len(d)
                ax.hlines(mean_v, i-0.25, i+0.25, colors=color,
                          linewidth=2.5, zorder=4, label=f'{label}: {mean_v:.1f}')
                if len(d) > 1:
                    import statistics as st
                    sd_v = st.stdev(d)
                    ax.vlines(i, mean_v-sd_v, mean_v+sd_v, colors=color,
                              linewidth=1.5, alpha=0.6, zorder=3)

            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, fontsize=9)
            ax.set_ylim(bottom=0)

        out_fig = PROJECT / "results" / "sprint3_reproducibility.png"
        fig.savefig(out_fig, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        print(f"  ✓ Figura: {out_fig.relative_to(PROJECT)}")
    except ImportError:
        print("  (matplotlib no disponible para figura)")

    print("\n" + "="*65)
    print("Análisis completado.")


if __name__ == "__main__":
    run_analysis()
