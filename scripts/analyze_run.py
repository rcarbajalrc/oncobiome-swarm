"""scripts/analyze_run.py — análisis post-run del decision logger CSV.

Lee logs/decisions.csv y genera estadísticas por run_id:
- Distribución de acciones por tipo de agente
- Ciclo del primer kill (tumor muerto por inmune)
- Ciclo de primera señalización VEGF (angiogénesis)
- Ciclo de primer agotamiento CD8+ (exhaustion)
- Agentes más activos (mayor diversidad de acciones)
- Evolución de confianza media por ciclo

USO:
    python3 scripts/analyze_run.py                    # última run
    python3 scripts/analyze_run.py --run-id 20260323  # run específica
    python3 scripts/analyze_run.py --csv path/to.csv  # CSV personalizado
"""
import sys
import csv
import argparse
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).parent.parent


def load_csv(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        print(f"CSV no encontrado: {csv_path}")
        sys.exit(1)
    with open(csv_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def filter_run(rows: list[dict], run_id: str | None) -> list[dict]:
    if not run_id:
        # Última run: el run_id más reciente
        run_ids = sorted({r["run_id"] for r in rows}, reverse=True)
        if not run_ids:
            print("CSV vacío.")
            sys.exit(1)
        run_id = run_ids[0]
    filtered = [r for r in rows if r["run_id"] == run_id]
    if not filtered:
        print(f"run_id '{run_id}' no encontrado.")
        sys.exit(1)
    return filtered, run_id


def analyze(rows: list[dict], run_id: str) -> None:
    print(f"\n{'='*60}")
    print(f"ANÁLISIS POST-RUN: {run_id}")
    print(f"Total decisiones: {len(rows)}")
    cycles = sorted({int(r['cycle']) for r in rows})
    print(f"Ciclos: {min(cycles)} → {max(cycles)} ({len(cycles)} ciclos)")
    print(f"{'='*60}\n")

    # ── 1. Distribución de acciones por tipo de agente ──────────────────────
    print("── Distribución de acciones por tipo de agente ──")
    by_type: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_type[r["agent_type"]][r["action"]] += 1

    for agent_type, actions in sorted(by_type.items()):
        total = sum(actions.values())
        print(f"\n  {agent_type} ({total} decisiones):")
        for action, count in sorted(actions.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            bar = "█" * int(pct / 5)
            print(f"    {action:<12} {count:>5}  {pct:>5.1f}%  {bar}")

    # ── 2. Eventos clave — ciclos de primera ocurrencia ─────────────────────
    print("\n── Eventos clave (ciclo de primera ocurrencia) ──")

    first_die = next(
        (int(r["cycle"]) for r in rows if r["action"] == "DIE"),
        None
    )
    first_vegf = next(
        (int(r["cycle"]) for r in rows
         if r["action"] == "SIGNAL" and "VEGF" in r.get("signal_type", "")),
        None
    )
    first_il6 = next(
        (int(r["cycle"]) for r in rows
         if r["action"] == "SIGNAL" and "IL-6" in r.get("signal_type", "")),
        None
    )
    first_exhausted = next(
        (int(r["cycle"]) for r in rows
         if r["agent_type"] == "ImmuneCell" and r["reasoning"] == "exhausted"),
        None
    )
    first_proliferate = next(
        (int(r["cycle"]) for r in rows if r["action"] == "PROLIFERATE"),
        None
    )

    events = [
        ("Primera proliferación", first_proliferate),
        ("Primera señal IL-6", first_il6),
        ("Primera señal VEGF", first_vegf),
        ("Primera muerte tumoral (DIE)", first_die),
        ("Primer agotamiento CD8+", first_exhausted),
    ]
    for name, cycle in events:
        val = f"ciclo {cycle}" if cycle is not None else "no ocurrió"
        print(f"  {name:<35} {val}")

    # ── 3. Confianza media por tipo de agente ────────────────────────────────
    print("\n── Confianza media por tipo de agente ──")
    conf_by_type: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        try:
            conf_by_type[r["agent_type"]].append(float(r["confidence"]))
        except (ValueError, KeyError):
            pass
    for agent_type, confs in sorted(conf_by_type.items()):
        avg = sum(confs) / len(confs)
        print(f"  {agent_type:<20} media={avg:.3f}  n={len(confs)}")

    # ── 4. Ciclos con mayor actividad tumoral (PROLIFERATE) ──────────────────
    print("\n── Top 5 ciclos con más proliferación tumoral ──")
    prolif_by_cycle: dict[int, int] = defaultdict(int)
    for r in rows:
        if r["action"] == "PROLIFERATE" and r["agent_type"] == "TumorCell":
            prolif_by_cycle[int(r["cycle"])] += 1
    top_cycles = sorted(prolif_by_cycle.items(), key=lambda x: -x[1])[:5]
    if top_cycles:
        for cycle, count in top_cycles:
            print(f"  Ciclo {cycle:>3}: {count} proliferaciones")
    else:
        print("  Sin proliferaciones registradas")

    # ── 5. Resumen de presión inmune por ciclo ────────────────────────────────
    print("\n── Actividad inmune: MIGRATE hacia tumor vs QUIESCE ──")
    engage_by_cycle: dict[int, int] = defaultdict(int)
    quiesce_by_cycle: dict[int, int] = defaultdict(int)
    for r in rows:
        if r["agent_type"] == "ImmuneCell":
            c = int(r["cycle"])
            if r["action"] == "MIGRATE" and "tumor" in r.get("reasoning", "").lower():
                engage_by_cycle[c] += 1
            elif r["action"] == "QUIESCE":
                quiesce_by_cycle[c] += 1

    total_engage = sum(engage_by_cycle.values())
    total_quiesce = sum(quiesce_by_cycle.values())
    total_immune = total_engage + total_quiesce
    if total_immune > 0:
        print(f"  Engage tumor: {total_engage} ({total_engage/total_immune*100:.1f}%)")
        print(f"  Quiesce:      {total_quiesce} ({total_quiesce/total_immune*100:.1f}%)")
    else:
        print("  Sin actividad inmune registrada")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Análisis post-run OncoBiome")
    parser.add_argument("--run-id", type=str, default=None, help="ID de run específica")
    parser.add_argument("--csv", type=str, default=None, help="Path al CSV")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else _ROOT / "logs" / "decisions.csv"
    rows = load_csv(csv_path)
    rows, run_id = filter_run(rows, args.run_id)
    analyze(rows, run_id)


if __name__ == "__main__":
    main()
