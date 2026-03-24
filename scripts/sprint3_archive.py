"""
Sprint 3 — Reproducibilidad estadística.

Este script:
1. Archiva runs históricas ya conocidas (runs R1 de cada experimento)
2. Proporciona infraestructura para archivar futuras runs automáticamente

Uso después de cada run LLM:
    python scripts/sprint3_archive.py --experiment cap80_baseline --run 2
    python scripts/sprint3_archive.py --list-stats cap80_baseline

NOTA sobre runs R1 históricas:
    Las R1 de baseline/immune_boost/combination_therapy se ejecutaron en Sprints 1-2
    con cap=150 (default settings.py) porque el MCP run_simulation no soportaba
    --experiment. Son internamente consistentes para el diseño factorial 2x3.
    Las R2-R4 de cap80_baseline usan cap=80 explícito via .env.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

PROJECT = Path(__file__).parent.parent
LOGS    = PROJECT / "logs"
STATE   = PROJECT / "state"
RUNS    = PROJECT / "runs"
RUNS.mkdir(exist_ok=True)

DPC = 2.167  # días por ciclo (PANC-1 52h doubling time)


# ── Datos de runs R1 (Sprint 2) — reconstruidos de transcripts verificados ───
# IMPORTANTE: immune_collapse_cycle = ciclo real del colapso según los logs MCP.
# cap80_baseline R1: corrió con cap=150 (default); colapso c29.
# immune_boost R1: cap=150; colapso c27.
# combination_therapy R1: cap=150; colapso c20 (primer ciclo con ImmuneCell=0).
HISTORICAL_RUNS = {
    "cap80_baseline_r1": {
        "experiment":            "cap80_baseline",
        "cycles":                77,
        "immune_collapse_cycle": 29,     # verificado: c29 = primer ciclo ImmuneCell=0
        "tumor_final":           146,
        "cost_usd":              1.85,
        "cap":                   150,    # usó cap=150 (default — MCP sin --experiment)
        "note": (
            "R1 original Sprint 2 — seed calibrado PANC-1 KRAS G12D. "
            "Ejecutada con cap=150 (default settings.py); MCP no soportaba --experiment. "
            "Usada como baseline_llm_cap150 en el diseño factorial."
        ),
    },
    "immune_boost_r1": {
        "experiment":            "immune_boost",
        "cycles":                52,
        "immune_collapse_cycle": 27,     # verificado: c27 = primer ciclo ImmuneCell=0
        "tumor_final":           142,
        "cost_usd":              1.45,
        "cap":                   150,
        "note": "R1 original Sprint 2 — 12 CD8+ + 6 macrophages, cap=150.",
    },
    "combination_therapy_r1": {
        "experiment":            "combination_therapy",
        "cycles":                52,
        "immune_collapse_cycle": 20,     # verificado: c20 = primer ciclo ImmuneCell=0
        "tumor_final":           142,
        "cost_usd":              1.76,
        "cap":                   150,
        "note": (
            "R1 original Sprint 2 — 10 CD8+ + 5 macro + 6 phyto, cap=150. "
            "Colapso c20 = hallazgo de la paradoja inmunológica."
        ),
    },
}


def archive_historical(run_key: str) -> None:
    """Archiva una run histórica (R1) con los datos conocidos."""
    data = HISTORICAL_RUNS[run_key]
    exp  = data["experiment"]
    ts   = "20260323T000000Z"
    dest = RUNS / exp / ts
    dest.mkdir(parents=True, exist_ok=True)

    collapse = data["immune_collapse_cycle"]
    meta = {
        "experiment":            exp,
        "timestamp":             ts,
        "note":                  data["note"],
        "run_index":             1,
        "cycles":                data["cycles"],
        "immune_collapse_cycle": collapse,
        "immune_collapse_days":  round(collapse * DPC, 1),
        "tumor_final":           data["tumor_final"],
        "cost_usd":              data["cost_usd"],
        "cap":                   data.get("cap", 150),
        "type":                  "historical",
    }
    (dest / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"  ✓ {run_key} → runs/{exp}/{ts}/  (colapso c{collapse}, {collapse*DPC:.1f}d)")


def archive_current(experiment: str, run_index: int, note: str = "") -> None:
    """Archiva la run actual desde logs/ y state/."""
    ts   = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = RUNS / experiment / ts
    dest.mkdir(parents=True, exist_ok=True)

    for fname in ["token_usage.json", "opus_history.json"]:
        src = LOGS / fname
        if src.exists():
            shutil.copy2(src, dest / fname)

    pop = []
    live = STATE / "live_state.json"
    if live.exists():
        with open(live) as f:
            state = json.load(f)
        pop = state.get("history", [])
    (dest / "population_history.json").write_text(json.dumps(pop, indent=2))

    collapse = None
    for i, entry in enumerate(pop, 1):
        if entry.get("ImmuneCell", 1) == 0:
            collapse = i
            break

    cost = 0.0
    token_file = dest / "token_usage.json"
    if token_file.exists():
        with open(token_file) as f:
            td = json.load(f)
        ti = sum(c.get("input", 0) for c in td)
        to = sum(c.get("output", 0) for c in td)
        opus_cycles = sum(1 for c in td if c.get("calls", 0) >= 4)
        cost = round(
            (ti * 0.80 + to * 4.00) / 1_000_000
            + opus_cycles * (20_000 * 15 + 600 * 75) / 1_000_000,
            4,
        )

    meta = {
        "experiment":            experiment,
        "timestamp":             ts,
        "note":                  note,
        "run_index":             run_index,
        "cycles":                len(pop),
        "immune_collapse_cycle": collapse,
        "immune_collapse_days":  round(collapse * DPC, 1) if collapse else None,
        "tumor_final":           pop[-1].get("TumorCell") if pop else None,
        "cost_usd":              cost,
        "type":                  "live",
    }
    (dest / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"  ✓ Archivada → runs/{experiment}/{ts}/")
    print(f"    colapso: c{collapse} ({collapse*DPC:.1f}d)  tumor: {meta['tumor_final']}  coste: ${cost}")


def print_stats(experiment: str) -> None:
    """Imprime estadísticas de reproducibilidad para un experimento."""
    import statistics as st

    exp_dir = RUNS / experiment
    if not exp_dir.exists():
        print(f"Sin runs archivadas para {experiment}")
        return

    collapses, tumors, costs = [], [], []
    print(f"\n{'─'*55}")
    print(f"Experimento: {experiment}")
    print(f"{'─'*55}")

    for i, run_dir in enumerate(sorted(exp_dir.iterdir()), 1):
        meta_file = run_dir / "metadata.json"
        if not meta_file.exists():
            continue
        meta = json.loads(meta_file.read_text())
        c = meta.get("immune_collapse_cycle")
        t = meta.get("tumor_final")
        cost = meta.get("cost_usd", 0)
        cap = meta.get("cap", "?")
        rtype = meta.get("type", "live")
        if c:
            collapses.append(c)
        if t:
            tumors.append(t)
        costs.append(cost)
        print(
            f"  R{i}: c{c} ({c*DPC:.1f}d) | tumor={t} | cap={cap} "
            f"| ${cost:.2f} | {rtype}"
        )

    if len(collapses) >= 2:
        m, s = st.mean(collapses), st.stdev(collapses)
        cv = s / m * 100
        flag = "✓ EXCELENTE" if cv < 15 else "✓ ACEPTABLE" if cv < 20 else "⚠ MARGINAL"
        print(f"\n  n={len(collapses)}")
        print(f"  Colapso: {m:.1f} ± {s:.1f} ciclos = {m*DPC:.1f} ± {s*DPC:.1f} días")
        print(f"  CV: {cv:.1f}%  {flag}")
        print(f"  Coste total: ${sum(costs):.2f}")
    elif len(collapses) == 1:
        print(f"\n  n=1 — sin estadísticas (necesita ≥2 runs)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sprint 3 run archive manager")
    sub = parser.add_subparsers(dest="cmd")

    arc = sub.add_parser("archive", help="Archiva la run actual")
    arc.add_argument("--experiment", required=True)
    arc.add_argument("--run", type=int, required=True)
    arc.add_argument("--note", default="")

    hist = sub.add_parser("archive-historical", help="Archiva runs R1 históricas")
    hist.add_argument("--all", action="store_true")
    hist.add_argument("--run", choices=list(HISTORICAL_RUNS.keys()))

    stats = sub.add_parser("stats", help="Imprime estadísticas de reproducibilidad")
    stats.add_argument("experiment")

    args = parser.parse_args()

    if args.cmd == "archive":
        archive_current(args.experiment, args.run, args.note)
    elif args.cmd == "archive-historical":
        if args.all:
            print("Archivando todas las runs históricas R1...")
            for key in HISTORICAL_RUNS:
                archive_historical(key)
        elif args.run:
            archive_historical(args.run)
        else:
            print("Usa --all o --run <key>")
    elif args.cmd == "stats":
        print_stats(args.experiment)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
