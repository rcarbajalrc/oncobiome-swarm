"""
run_manager.py — Gestión de runs archivadas para reproducibilidad estadística.

Cada run se archiva en runs/<experiment>/<timestamp>/
con token_usage.json, opus_history.json, population_history.json y metadata.json.

Uso:
    python scripts/run_manager.py archive --experiment cap80_baseline
    python scripts/run_manager.py list
    python scripts/run_manager.py stats --experiment cap80_baseline
    python scripts/run_manager.py clean --experiment cap80_baseline
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).parent.parent
LOGS    = PROJECT / "logs"
STATE   = PROJECT / "state"
RUNS    = PROJECT / "runs"
RUNS.mkdir(exist_ok=True)


# ─── Archivado ────────────────────────────────────────────────────────────────

def archive(experiment: str, note: str = "") -> Path:
    """Archiva la run actual en runs/<experiment>/<timestamp>/"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = RUNS / experiment / ts
    dest.mkdir(parents=True, exist_ok=True)

    # Copiar logs
    for fname in ["token_usage.json", "opus_history.json"]:
        src = LOGS / fname
        if src.exists():
            shutil.copy2(src, dest / fname)

    # Extraer population_history desde live_state.json
    live = STATE / "live_state.json"
    if live.exists():
        with open(live) as f:
            state = json.load(f)
        pop_history = state.get("history", [])
        (dest / "population_history.json").write_text(
            json.dumps(pop_history, indent=2)
        )

    # metadata.json
    meta = {
        "experiment": experiment,
        "timestamp": ts,
        "note": note,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
    # Añadir métricas clave si hay datos
    token_file = dest / "token_usage.json"
    if token_file.exists():
        with open(token_file) as f:
            token_data = json.load(f)
        if token_data:
            total_input  = sum(c.get("input", 0) for c in token_data)
            total_output = sum(c.get("output", 0) for c in token_data)
            total_cycles = len(token_data)
            haiku_cost   = (total_input * 0.80 + total_output * 4.00) / 1_000_000
            # Opus cycles tienen ~20k input extra
            opus_calls   = sum(1 for c in token_data if c.get("calls", 0) >= 4)
            opus_cost    = opus_calls * (20000 * 15 + 600 * 75) / 1_000_000
            meta["cycles"]     = total_cycles
            meta["input_tokens"]  = total_input
            meta["output_tokens"] = total_output
            meta["cost_usd"]   = round(haiku_cost + opus_cost, 4)

    pop_file = dest / "population_history.json"
    if pop_file.exists():
        with open(pop_file) as f:
            pop = json.load(f)
        if pop:
            # Ciclo de colapso inmune: primer ciclo con ImmuneCell = 0
            immune_key = "ImmuneCell"
            collapse = None
            for entry in pop:
                if entry.get(immune_key, 1) == 0:
                    collapse = entry.get("cycle", None)
                    break
            meta["immune_collapse_cycle"] = collapse
            meta["immune_collapse_days"]  = round(collapse * 2.167, 1) if collapse else None
            # Tumor final
            if pop:
                last = pop[-1]
                meta["tumor_final"] = last.get("TumorCell", None)

    (dest / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"✓ Archivado: {dest.relative_to(PROJECT)}")
    print(f"  Ciclos: {meta.get('cycles', '?')}  "
          f"Colapso: c{meta.get('immune_collapse_cycle', '?')}  "
          f"Tumor: {meta.get('tumor_final', '?')}  "
          f"Coste: ${meta.get('cost_usd', '?')}")
    return dest


# ─── Listar ───────────────────────────────────────────────────────────────────

def list_runs(experiment: str | None = None) -> None:
    experiments = sorted(RUNS.iterdir()) if RUNS.exists() else []
    if not experiments:
        print("No hay runs archivadas.")
        return

    for exp_dir in experiments:
        if experiment and exp_dir.name != experiment:
            continue
        runs = sorted(exp_dir.iterdir())
        print(f"\n── {exp_dir.name} ({len(runs)} runs) ──")
        for run_dir in runs:
            meta_file = run_dir / "metadata.json"
            if meta_file.exists():
                m = json.loads(meta_file.read_text())
                collapse = m.get("immune_collapse_cycle")
                days     = m.get("immune_collapse_days")
                tumor    = m.get("tumor_final")
                cost     = m.get("cost_usd")
                print(f"  {run_dir.name}  "
                      f"c{collapse}({days}d)  tumor={tumor}  ${cost}")


# ─── Estadísticas n=3 ─────────────────────────────────────────────────────────

def stats(experiment: str) -> None:
    exp_dir = RUNS / experiment
    if not exp_dir.exists():
        print(f"No hay runs para: {experiment}")
        return

    runs = sorted(exp_dir.iterdir())
    if len(runs) < 2:
        print(f"Solo {len(runs)} run(s) — necesita ≥2 para estadística.")
        return

    collapses = []
    tumors    = []
    costs     = []

    for run_dir in runs:
        m_file = run_dir / "metadata.json"
        if not m_file.exists():
            continue
        m = json.loads(m_file.read_text())
        c = m.get("immune_collapse_cycle")
        t = m.get("tumor_final")
        cost = m.get("cost_usd")
        if c is not None: collapses.append(c)
        if t is not None: tumors.append(t)
        if cost is not None: costs.append(cost)

    if not collapses:
        print("Sin datos de colapso inmune.")
        return

    import statistics as st

    n = len(collapses)
    c_mean = st.mean(collapses)
    c_sd   = st.stdev(collapses) if n > 1 else 0
    c_days_mean = round(c_mean * 2.167, 1)
    c_days_sd   = round(c_sd * 2.167, 1)

    t_mean = st.mean(tumors) if tumors else None
    t_sd   = st.stdev(tumors) if len(tumors) > 1 else 0

    print(f"\n{'='*50}")
    print(f"Estadísticas: {experiment}  (n={n})")
    print(f"{'='*50}")
    print(f"Colapso inmune:  {c_mean:.1f} ± {c_sd:.1f} ciclos")
    print(f"                 {c_days_mean} ± {c_days_sd} días biológicos")
    if t_mean is not None:
        print(f"Tumor final:     {t_mean:.1f} ± {t_sd:.1f} células")
    print(f"Coste total:     ${sum(costs):.2f}")
    print(f"Coste por run:   ${sum(costs)/n:.2f}")
    print()

    # Detectar outliers si n >= 3
    if n >= 3:
        cv = (c_sd / c_mean * 100) if c_mean > 0 else 0
        print(f"Coeficiente de variación: {cv:.1f}%")
        if cv > 20:
            print("⚠️  Alta variabilidad (CV>20%) — considerar n=5")
        else:
            print("✓  Variabilidad aceptable para publicación")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OncoBiome Run Manager")
    sub = parser.add_subparsers(dest="cmd")

    p_archive = sub.add_parser("archive", help="Archivar run actual")
    p_archive.add_argument("--experiment", required=True)
    p_archive.add_argument("--note", default="")

    p_list = sub.add_parser("list", help="Listar runs archivadas")
    p_list.add_argument("--experiment", default=None)

    p_stats = sub.add_parser("stats", help="Estadísticas de un experimento")
    p_stats.add_argument("--experiment", required=True)

    args = parser.parse_args()

    if args.cmd == "archive":
        archive(args.experiment, args.note)
    elif args.cmd == "list":
        list_runs(args.experiment)
    elif args.cmd == "stats":
        stats(args.experiment)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
