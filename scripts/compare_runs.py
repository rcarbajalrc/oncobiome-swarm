"""scripts/compare_runs.py — comparación automática entre múltiples runs.

Lee todos los CSVs de decisions en logs/ y genera comparativas:
- Curvas de colapso inmune superpuestas
- Velocidad de crecimiento tumoral por experimento
- Ciclo de primer kill, primer VEGF, extinción inmune
- Tabla comparativa de métricas clave

USO:
    python3 scripts/compare_runs.py                    # todos los CSVs en logs/
    python3 scripts/compare_runs.py --metric immune    # solo curvas inmunes
    python3 scripts/compare_runs.py --opus             # historial Opus
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_LOGS = _ROOT / "logs"
_OPUS_LOG = _ROOT / "logs" / "opus_history.json"

# Doubling time PANC-1 calibrado: 52h = 2.17 días biológicos por ciclo
# Referencia: PMC4655885 (ATCC)
DOUBLING_TIME_H = 52
BIOLOGICAL_DAYS_PER_CYCLE = DOUBLING_TIME_H / 24  # 2.17 días/ciclo


def load_all_runs(csv_path: Path | None = None) -> dict[str, list[dict]]:
    """Carga todos los CSVs disponibles. Agrupa por run_id."""
    files = [csv_path] if csv_path else list(_LOGS.glob("decisions*.csv")) + [_LOGS / "decisions.csv"]
    files = [f for f in files if f.exists()]

    if not files:
        print("No se encontraron archivos decisions.csv en logs/")
        return {}

    all_rows: dict[str, list[dict]] = defaultdict(list)
    for f in files:
        with open(f) as fh:
            for row in csv.DictReader(fh):
                all_rows[row["run_id"]].append(row)

    print(f"Cargadas {len(all_rows)} runs de {len(files)} archivo(s)")
    return dict(all_rows)


def extract_metrics(rows: list[dict]) -> dict:
    """Extrae métricas clave de una run.

    CORRECCIÓN: pop_by_cycle cuenta agent_id únicos por ciclo y tipo,
    no filas CSV. Esto evita doble conteo cuando un agente tiene
    múltiples decisiones por ciclo o cuando hay runs concatenadas.
    """
    if not rows:
        return {}

    cycles = sorted({int(r["cycle"]) for r in rows})
    max_cycle = max(cycles)

    # FIX: contar agent_id únicos por ciclo y tipo (no filas)
    agents_by_cycle: dict[int, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for r in rows:
        c = int(r["cycle"])
        agents_by_cycle[c][r["agent_type"]].add(r["agent_id"])

    # Convertir a conteos
    pop_by_cycle: dict[int, dict[str, int]] = {
        c: {atype: len(ids) for atype, ids in types.items()}
        for c, types in agents_by_cycle.items()
    }

    # Primer kill tumoral (DIE)
    first_tumor_die = next(
        (int(r["cycle"]) for r in rows
         if r["action"] == "DIE" and r["agent_type"] == "TumorCell"),
        None
    )

    # Primer VEGF
    first_vegf = next(
        (int(r["cycle"]) for r in rows
         if r["action"] == "SIGNAL" and "VEGF" in r.get("signal_type", "")),
        None
    )

    # Ciclo extinción inmune (último ciclo con ImmuneCell presente)
    immune_cycles = [c for c, pop in pop_by_cycle.items() if pop.get("ImmuneCell", 0) > 0]
    immune_extinction = max(immune_cycles) if immune_cycles else None
    immune_peak = max((pop.get("ImmuneCell", 0) for pop in pop_by_cycle.values()), default=0)

    # Colapso inmune: primer ciclo donde ImmuneCell < 2 después del pico
    immune_collapse = None
    if immune_peak >= 3:
        for c in sorted(cycles):
            if pop_by_cycle.get(c, {}).get("ImmuneCell", 0) < 2 and c > 5:
                immune_collapse = c
                break

    # Tumor máximo (agentes únicos en el ciclo con más TumorCells)
    tumor_peak = max(
        (pop.get("TumorCell", 0) for pop in pop_by_cycle.values()),
        default=0
    )

    # Ciclo en que el tumor superó 80 agentes únicos
    tumor_cap80_cycle = next(
        (c for c in sorted(cycles) if pop_by_cycle.get(c, {}).get("TumorCell", 0) >= 80),
        None
    )

    # Velocidad media de crecimiento tumoral (ciclos 1-10)
    early_cycles = [c for c in sorted(cycles) if 1 <= c <= 10]
    if len(early_cycles) >= 2:
        t_start = pop_by_cycle.get(early_cycles[0], {}).get("TumorCell", 0)
        t_end = pop_by_cycle.get(early_cycles[-1], {}).get("TumorCell", 0)
        growth_rate = (t_end - t_start) / len(early_cycles)
    else:
        growth_rate = 0

    def to_bio_days(cycle):
        return round(cycle * BIOLOGICAL_DAYS_PER_CYCLE, 1) if cycle is not None else None

    return {
        "max_cycle": max_cycle,
        "tumor_peak": tumor_peak,
        "immune_peak": immune_peak,
        "immune_collapse_cycle": immune_collapse,
        "immune_collapse_days": to_bio_days(immune_collapse),
        "immune_extinction_cycle": immune_extinction,
        "immune_extinction_days": to_bio_days(immune_extinction),
        "tumor_cap80_cycle": tumor_cap80_cycle,
        "tumor_cap80_days": to_bio_days(tumor_cap80_cycle),
        "first_tumor_die_cycle": first_tumor_die,
        "first_vegf_cycle": first_vegf,
        "growth_rate_early": round(growth_rate, 2),
        "pop_by_cycle": pop_by_cycle,
    }


def print_comparison_table(runs_metrics: dict[str, dict]) -> None:
    if not runs_metrics:
        print("Sin datos para comparar.")
        return

    print(f"\n{'='*80}")
    print("COMPARACIÓN DE RUNS — OncoBiome KRAS G12D")
    print(f"Escala biológica: 1 ciclo = {BIOLOGICAL_DAYS_PER_CYCLE:.1f} días ({DOUBLING_TIME_H}h doubling time PANC-1)")
    print(f"{'='*80}\n")

    headers = ["Run ID", "Ciclos", "Tumor max", "Colapso inmune", "Extinción inmune",
               "Cap80 (días)", "Crecim/ciclo"]
    col_w = [22, 7, 10, 18, 18, 13, 13]

    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, col_w))
    print(header_line)
    print("-" * len(header_line))

    for run_id, m in sorted(runs_metrics.items()):
        collapse = (f"c{m['immune_collapse_cycle']} ({m['immune_collapse_days']}d)"
                    if m.get('immune_collapse_cycle') else "no colapsó")
        extinction = (f"c{m['immune_extinction_cycle']} ({m['immune_extinction_days']}d)"
                      if m.get('immune_extinction_cycle') else "sobrevivió")
        cap80 = (f"{m['tumor_cap80_days']}d"
                 if m.get('tumor_cap80_days') else "no alcanzó")

        row = [
            run_id[:22],
            str(m.get("max_cycle", "?")),
            str(m.get("tumor_peak", "?")),
            collapse,
            extinction,
            cap80,
            str(m.get("growth_rate_early", "?")),
        ]
        print("  ".join(v.ljust(w) for v, w in zip(row, col_w)))

    print()


def print_immune_curves(runs_metrics: dict[str, dict]) -> None:
    print(f"\n{'='*80}")
    print("CURVAS DE INMUNIDAD (ImmuneCell únicos por ciclo)")
    print(f"{'='*80}\n")

    all_cycles = set()
    for m in runs_metrics.values():
        all_cycles.update(m.get("pop_by_cycle", {}).keys())

    if not all_cycles:
        print("Sin datos de población.")
        return

    max_c = min(max(all_cycles), 77)
    checkpoints = list(range(0, max_c + 1, 5))

    # Mostrar solo las últimas 6 runs para legibilidad
    run_ids = sorted(runs_metrics.keys())[-6:]
    header = f"{'Ciclo':<8}" + "".join(f"{rid[:14]:<18}" for rid in run_ids)
    print(header)
    print("-" * len(header))

    for c in checkpoints:
        row = f"{c:<8}"
        for run_id in run_ids:
            pop = runs_metrics[run_id].get("pop_by_cycle", {}).get(c, {})
            immune = pop.get("ImmuneCell", 0)
            bar = "▓" * min(immune, 10) + ("·" * (10 - min(immune, 10)))
            row += f"{bar} {immune:<7}"
        print(row)
    print()


def print_opus_history() -> None:
    if not _OPUS_LOG.exists():
        print("\nNo hay historial Opus guardado.")
        return
    try:
        history = json.loads(_OPUS_LOG.read_text())
    except Exception as e:
        print(f"\nError: {e}")
        return

    print(f"\n{'='*80}")
    print(f"HISTORIAL OPUS ({len(history)} análisis)")
    print(f"{'='*80}")
    for entry in history:
        print(f"\n── Ciclo {entry['cycle']} ──")
        print(entry.get("analysis", "[sin análisis]"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default=None)
    parser.add_argument("--metric", choices=["immune", "tumor", "all"], default="all")
    parser.add_argument("--opus", action="store_true")
    args = parser.parse_args()

    if args.opus:
        print_opus_history()
        return

    csv_path = Path(args.csv) if args.csv else None
    all_runs = load_all_runs(csv_path)

    if not all_runs:
        print("Sin datos. Activa LOG_DECISIONS=true en .env.")
        return

    runs_metrics = {run_id: extract_metrics(rows) for run_id, rows in all_runs.items()}

    if args.metric in ("all", "tumor"):
        print_comparison_table(runs_metrics)
    if args.metric in ("all", "immune"):
        print_immune_curves(runs_metrics)


if __name__ == "__main__":
    main()
